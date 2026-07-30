"""Wildberries provider: open the page once, then read it three ways.

Wildberries renders prices client-side from an internal JSON endpoint. Calling
that endpoint directly — with curl, or even with ``fetch()`` from the product
page's own context — returns 403, so instead the provider opens the page and
reads the response the page makes on its own behalf.

Missing that response is no longer fatal. It is one of three readers, and the
rendered price block and the document title both carry the price too; the chain
in :mod:`bot.core.providers.wildberries_parsers` falls through to them.
"""

import re
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Error as PlaywrightError

from bot.core.logging import get_logger
from bot.core.providers.base import (
    PriceNotFoundError,
    ProductData,
    Provider,
    ProviderBlockedError,
)
from bot.core.providers.browser import BrowserSession, browser_session
from bot.core.providers.strategies import PageMaterial, StrategyChain
from bot.core.providers.throttle import throttle
from bot.core.providers.wildberries_parsers import WILDBERRIES_STRATEGIES
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)

_CARD_API_PATH = '/u-card/cards/v4/detail'
_ARTICLE_RE = re.compile(r'/catalog/(\d+)/')

_PRICE_SELECTORS = (
    '.price-block__final-price',
    '.price-block',
    '[data-link*="price"]',
)

# How long to give the page to issue its own card request before falling back to
# reading the markup. Short, because there are two other readers behind it.
_CARD_API_TIMEOUT_MS = 20_000


class WildberriesProvider(Provider):
    """Fetch product title and price from a Wildberries product page."""

    def __init__(self, session: BrowserSession | None = None) -> None:
        self._session = session or browser_session
        self._chain = StrategyChain(WILDBERRIES_STRATEGIES)

    @property
    def provider_type(self) -> ProviderEnum:
        return ProviderEnum.WILDBERRIES

    @property
    def strategy_order(self) -> list[str]:
        """Current preference order, exposed for logging and tests."""
        return self._chain.order

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
                material = await self._gather(page, product_url, article)
            except PlaywrightError as exc:
                # Playwright's TimeoutError does not subclass the builtin one, so
                # this catches its Error base. Reaching here means the page never
                # loaded at all, which is a refusal rather than a parse problem.
                raise ProviderBlockedError(f'Wildberries did not serve the page: {exc}') from exc

        result = await self._chain.run(material)
        if result is None:
            raise PriceNotFoundError(f'Opened the Wildberries page for {article} but found no price')

        title = result.candidate.title or f'Wildberries {article}'
        return ProductData(title=title, price=result.candidate.price, currency='RUB', url=product_url)

    # --- page handling ---------------------------------------------------

    async def _gather(self, page, product_url: str, article: str) -> PageMaterial:
        """Load the page and collect everything the readers might need."""
        payload = None
        try:
            async with page.expect_response(
                lambda response: self._is_card_response(response, article),
                timeout=_CARD_API_TIMEOUT_MS,
            ) as response_info:
                await page.goto(product_url, wait_until='domcontentloaded', timeout=60_000)
            payload = await (await response_info.value).json()
        except PlaywrightError:
            # The page loaded but never issued (or was refused) its own card
            # request. Not fatal: the markup and the title still carry the price.
            logger.info('Wildberries card API not seen; falling back to the page', extra={'article': article})
            await page.wait_for_timeout(2_000)
        except Exception as exc:
            logger.info('Could not read the card payload', extra={'article': article, 'error': str(exc)})

        return PageMaterial(
            url=product_url,
            html=await page.content(),
            widget_text=await self._price_text(page),
            page_title=await page.title(),
            api_payload=payload,
        )

    @staticmethod
    async def _price_text(page) -> str:
        for selector in _PRICE_SELECTORS:
            try:
                text = await page.eval_on_selector(selector, 'e => e.innerText')
            except Exception:
                continue
            if text:
                return text
        return ''

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
