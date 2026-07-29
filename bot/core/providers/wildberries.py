"""Wildberries provider: intercept the marketplace's own card API response.

A deliberately different strategy from the Ozon provider, and the reason this
repository has two: it shows the provider interface accommodating genuinely
different mechanics rather than the same scraper twice.

Wildberries renders prices client-side from an internal JSON endpoint
(``/__internal/u-card/cards/v4/detail``). Two things were measured:

* Calling that endpoint directly — with curl, or even with ``fetch()`` from the
  product page's own context — returns 403. Its anti-bot check is not satisfied
  by cookies alone.
* The request the page makes itself succeeds. So instead of replaying it, we
  open the product page and read the response as it goes past.

The result is structured data (name, brand, price in kopecks) with no HTML
parsing at all, which is far more stable than scraping rendered markup.
"""

import re
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from bot.core.logging import get_logger
from bot.core.providers.base import (
    PriceNotFoundError,
    ProductData,
    Provider,
    ProviderBlockedError,
)
from bot.core.providers.browser import BrowserSession, browser_session
from bot.core.providers.throttle import throttle
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)

_CARD_API_PATH = '/u-card/cards/v4/detail'
_ARTICLE_RE = re.compile(r'/catalog/(\d+)/')
_KOPECKS = Decimal(100)


class WildberriesProvider(Provider):
    """Fetch product title and price from a Wildberries product page."""

    def __init__(self, session: BrowserSession | None = None) -> None:
        self._session = session or browser_session

    @property
    def provider_type(self) -> ProviderEnum:
        return ProviderEnum.WILDBERRIES

    def supports(self, url: str) -> bool:
        """Match Wildberries hosts exactly and require a catalog article."""
        host = urlparse(url).netloc.lower()
        is_wb_host = host in ('wildberries.ru', 'www.wildberries.ru') or host.endswith('.wildberries.ru')
        return is_wb_host and self._article(url) is not None

    async def normalize(self, url: str) -> str:
        """Rebuild the canonical product URL from its article number."""
        article = self._article(url)
        if article is None:
            raise PriceNotFoundError(f'No Wildberries article number in URL: {url}')
        return f'https://www.wildberries.ru/catalog/{article}/detail.aspx'

    async def fetch_product(self, url: str) -> ProductData:
        article = self._article(url)
        if article is None:
            raise PriceNotFoundError(f'No Wildberries article number in URL: {url}')

        product_url = await self.normalize(url)

        await throttle.wait(self.provider_type)
        async with self._session.page() as page:
            try:
                async with page.expect_response(
                    lambda response: self._is_card_response(response, article),
                    timeout=30_000,
                ) as response_info:
                    await page.goto(product_url, wait_until='domcontentloaded', timeout=60_000)
                response = await response_info.value
                payload = await response.json()
            except TimeoutError as exc:
                # The page loaded but never issued (or was refused) its own card
                # request — that is what a Wildberries block looks like from here.
                raise ProviderBlockedError('Wildberries did not serve its card API (anti-bot)') from exc

        return self._parse(payload, article, product_url)

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _article(url: str) -> str | None:
        match = _ARTICLE_RE.search(urlparse(url).path)
        return match.group(1) if match else None

    @staticmethod
    def _is_card_response(response, article: str) -> bool:
        if _CARD_API_PATH not in response.url or response.status != 200:
            return False
        # The page also asks for sibling colours in one batched call
        # (`nm=1;2;3`); only the single-article response describes this product.
        return parse_qs(urlparse(response.url).query).get('nm') == [article]

    def _parse(self, payload: dict, article: str, url: str) -> ProductData:
        products = (payload.get('data') or {}).get('products') or payload.get('products') or []
        if not products:
            raise PriceNotFoundError(f'Wildberries card API returned no product for {article}')

        product = products[0]
        title = ' '.join(part for part in (product.get('brand'), product.get('name')) if part).strip()
        price = self._price(product)
        if price is None:
            raise PriceNotFoundError(f'No price in the Wildberries card payload for {article}')

        return ProductData(title=title or f'Wildberries {article}', price=price, currency='RUB', url=url)

    @staticmethod
    def _price(product: dict) -> Decimal | None:
        """Take the selling price of the first variant that carries one.

        Prices arrive in kopecks. ``product`` is what the buyer pays; ``basic``
        is the pre-discount figure shown struck through. Multi-size items can
        price variants differently — the first one is what the page opens on.
        """
        for size in product.get('sizes') or []:
            raw = (size.get('price') or {}).get('product')
            if raw:
                return Decimal(raw) / _KOPECKS
        return None
