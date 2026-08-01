"""Fallback provider for any site without one of its own.

A site-specific provider (Wildberries) claims its own hosts and brings its own
transport and readers. This one claims whatever is left — any safe public
http(s) URL — and has no site knowledge at all. It opens the page once and reads
the price out of the markup a shop publishes for search engines (schema.org,
Open Graph, hydration JSON) through the shared generic readers. That works on
most shops; a page that publishes none of it yields no price, which is reported
as such rather than guessed.

Opening arbitrary URLs points a real browser at attacker-controlled input, so it
is opt-in (``GENERIC_PROVIDER_ENABLED``) and every fetch is vetted by
:mod:`bot.core.providers.url_safety` — see the README's security note. Registered
last, so a specific provider always gets first refusal on the hosts it owns.
"""

from urllib.parse import urlparse

from playwright.async_api import Error as PlaywrightError

from bot.core.config import settings
from bot.core.logging import get_logger
from bot.core.providers.base import (
    PriceNotFoundError,
    ProductData,
    Provider,
    ProviderBlockedError,
    UnsupportedURLError,
)
from bot.core.providers.browser import BrowserSession, browser_session
from bot.core.providers.generic_parsers import HTML_STRATEGIES, currency_from_text, title_from_html
from bot.core.providers.strategies import PageMaterial, StrategyChain
from bot.core.providers.throttle import throttle
from bot.core.providers.url_safety import is_fetchable, is_safe_url
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)


class GenericProvider(Provider):
    """Read a price from any public product page through the generic readers."""

    def __init__(self, session: BrowserSession | None = None) -> None:
        self._session = session or browser_session
        self._chain = StrategyChain(HTML_STRATEGIES)

    @property
    def provider_type(self) -> ProviderEnum:
        return ProviderEnum.GENERIC

    def supports(self, url: str) -> bool:
        """Claim any safe public http(s) URL. Registered last, so specific providers win."""
        return is_safe_url(url)

    async def normalize(self, url: str) -> str:
        return url.strip()

    async def fetch_product(self, url: str) -> ProductData:
        # Resolve and vet the host before opening it, so a name cannot stand in
        # for an internal address. Re-checked below against the address the page
        # actually reached, and re-run on every poll rather than trusted once.
        if not await is_fetchable(url, settings.blocked_host_set):
            raise UnsupportedURLError(f'URL is not an allowed fetch target: {url}')

        # Throttle per host, not per provider: this one provider speaks to many
        # sites, and the gap belongs to whichever host is on the other end.
        host = urlparse(url).hostname or url
        await throttle.wait(host)

        async with self._session.page() as page:
            try:
                # Blank first, so a navigation that never commits leaves an empty
                # document rather than the previous product still on the shared page.
                await page.goto('about:blank')
                await page.goto(url, wait_until='domcontentloaded', timeout=60_000)
                # A redirect can land on an internal host; refuse to read that page.
                if not await is_fetchable(page.url, settings.blocked_host_set):
                    raise UnsupportedURLError(f'redirected to a disallowed host: {page.url}')
                html = await page.content()
                page_title = await page.title()
            except PlaywrightError as exc:
                raise ProviderBlockedError(f'The site did not serve the page: {exc}') from exc

        material = PageMaterial(url=url, html=html, page_title=page_title)
        result = await self._chain.run(material)
        if result is None or result.candidate.price is None:
            raise PriceNotFoundError(f'Opened {url} but found no price in its markup')

        title = result.candidate.title or title_from_html(html) or (urlparse(url).hostname or url)
        currency = result.candidate.currency or currency_from_text(html)
        return ProductData(title=title, price=result.candidate.price, currency=currency, url=url)
