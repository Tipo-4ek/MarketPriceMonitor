"""Ozon provider: read the price out of the rendered product page.

Extraction order, in the order they were verified against a live page:

1. **JSON-LD** — ``<script type="application/ld+json">`` still carries an
   ``offers.price``. That is the regular price, i.e. what you pay without an
   Ozon-card discount, which is the stable thing to track: the card price
   depends on who is looking.
2. **The price widget** — ``[data-widget="webPrice"]`` as a fallback. Ozon's CSS
   class names are hashed and change between deploys, so the ``data-widget``
   attribute is the only durable anchor; the numbers inside are read as text.

The internal ``entrypoint-api.bx`` JSON endpoint is deliberately not used: it
answers 403 even to a request issued from the product page's own context.
"""

import asyncio
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse, urlunparse

from playwright.async_api import Error as PlaywrightError

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

_OZON_HOSTS = ('ozon.ru', 'www.ozon.ru', 'm.ozon.ru')

# The only durable anchor on the page: Ozon's CSS class names are hashed and
# change between deploys, the data-widget attributes do not.
_PRICE_WIDGET = '[data-widget="webPrice"]'

# A warm profile arrives in a few seconds; a cold one has to sit through the
# challenge first, which is what the longer warm-up budget is for.
_ARRIVE_TIMEOUT_MS = 25_000
_WARMUP_TIMEOUT_MS = 45_000

# Signals that Ozon served a challenge / block page instead of the product.
_BLOCK_MARKERS = (
    'antibot challenge',
    'доступ ограничен',
    'access denied',
    'checking your browser',
    'ddos-guard',
    'captcha',
)

# Digits in a rendered price are separated by thin / non-breaking spaces.
_SPACES = dict.fromkeys(map(ord, '    '), None)

# Per-unit rates that sit inside the price widget alongside the actual price.
_PER_UNIT_RE = re.compile(r'(\bза\b|/\s*(шт|кг|г|л|мл|м)\b|₽\s*/)', re.IGNORECASE)


class OzonProvider(Provider):
    """Fetch product title and price from an Ozon product page."""

    def __init__(self, session: BrowserSession | None = None) -> None:
        self._session = session or browser_session

    @property
    def provider_type(self) -> ProviderEnum:
        return ProviderEnum.OZON

    def supports(self, url: str) -> bool:
        """Match Ozon hosts exactly to avoid ``ozon.ru.evil.com`` bypasses."""
        host = urlparse(url).netloc.lower()
        return host in _OZON_HOSTS or host.endswith('.ozon.ru')

    async def normalize(self, url: str) -> str:
        """Drop query string and fragment for a stable database key."""
        parsed = urlparse(url)
        return urlunparse(parsed._replace(query='', fragment=''))

    async def fetch_product(self, url: str) -> ProductData:
        await throttle.wait(self.provider_type)
        async with self._session.page() as page:
            try:
                arrived = await self._open_product(page, url)
                html = await page.content()
                widget_text = await self._widget_text(page) if arrived else ''
            except PlaywrightError as exc:
                # Navigation timeouts and closed pages are how a block presents
                # itself here. Playwright's TimeoutError does not subclass the
                # builtin one, so this catches its Error base instead.
                raise ProviderBlockedError(f'Ozon did not serve the product page: {exc}') from exc

        if not arrived:
            raise ProviderBlockedError(self._block_reason(html))

        title = self._title(html) or 'Unknown product'
        price = self._price(html, widget_text)
        if price is None:
            raise PriceNotFoundError('Could not read a price from the Ozon page')

        return ProductData(title=title, price=price, currency='RUB', url=url)

    # --- page handling ---------------------------------------------------

    async def _open_product(self, page, url: str) -> bool:
        """Open the product page, warming up through the homepage if challenged.

        A cold browser profile is challenged on its first request and needs a
        while to be let through; a warm one arrives in seconds. Rather than pay
        a homepage visit on every poll, we try the product directly and only
        warm up when that did not work.
        """
        await page.goto(url, wait_until='domcontentloaded', timeout=60_000)
        if await self._await_product(page, timeout_ms=_ARRIVE_TIMEOUT_MS):
            return True

        logger.info('Ozon challenged the request; warming up via the homepage')
        await page.goto('https://www.ozon.ru/', wait_until='domcontentloaded', timeout=60_000)
        await self._await_product(page, selector='a[href*="/product/"]', timeout_ms=_WARMUP_TIMEOUT_MS)
        await asyncio.sleep(2)

        await page.goto(url, wait_until='domcontentloaded', timeout=60_000)
        return await self._await_product(page, timeout_ms=_ARRIVE_TIMEOUT_MS)

    @staticmethod
    async def _await_product(page, selector: str = _PRICE_WIDGET, timeout_ms: int = 20_000) -> bool:
        """Wait for a marker that only the real product page carries.

        Waiting for the product itself, rather than for the challenge title to
        disappear, is the reliable signal: the challenge swaps the title several
        times before it gives up or lets you through.
        """
        try:
            await page.wait_for_selector(selector, timeout=timeout_ms, state='attached')
        except Exception:
            return False
        return True

    @staticmethod
    async def _widget_text(page) -> str:
        try:
            return await page.eval_on_selector(_PRICE_WIDGET, 'e => e.innerText')
        except Exception:
            # The widget is simply absent on some cards; JSON-LD may still
            # carry the price, so this is not a failure on its own.
            return ''

    @staticmethod
    def _block_reason(html: str) -> str:
        """Name the challenge we hit, for the log and the health monitor."""
        lowered = html[:20_000].lower()
        marker = next((m for m in _BLOCK_MARKERS if m in lowered), None)
        if marker:
            return f'Ozon served an anti-bot page (matched {marker!r})'
        return 'Ozon did not render the product page within the timeout'

    # --- parsing ---------------------------------------------------------

    def _price(self, html: str, widget_text: str) -> Decimal | None:
        json_ld = self._extract_json_ld(html)
        if json_ld:
            price = self._price_from_offers(json_ld.get('offers'))
            if price is not None:
                return price
        return self._price_from_widget(widget_text)

    def _title(self, html: str) -> str | None:
        json_ld = self._extract_json_ld(html)
        if json_ld and json_ld.get('name'):
            return str(json_ld['name']).strip()
        return self._title_from_regex(html)

    @staticmethod
    def _extract_json_ld(html: str) -> dict | None:
        match = re.search(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if not match:
            return None
        try:
            data = json.loads(match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _price_from_offers(offers: object) -> Decimal | None:
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if isinstance(offers, dict) and offers.get('price') is not None:
            try:
                return Decimal(str(offers['price']))
            except (InvalidOperation, ValueError):
                return None
        return None

    @staticmethod
    def _price_from_widget(widget_text: str) -> Decimal | None:
        """Pick the regular price out of the widget, or refuse to guess.

        A full widget renders three figures in order — the Ozon-card price, the
        regular price and the struck-through old price — plus, often, a per-unit
        figure like "218 ₽ за 100 гр" that must not be mistaken for the price.

        Only two shapes are read. Three figures: the middle one, which was
        checked against the same page's JSON-LD and matched. One figure: itself.
        Anything else is ambiguous — with two figures there is no telling a
        card-plus-regular pair from a regular-plus-struck-through one, and
        choosing wrong stores a price out by a factor of two and fires a false
        "price changed" alert to everyone tracking the product. Returning
        nothing costs one poll; guessing costs trust.
        """
        prices = []
        for line in widget_text.splitlines():
            # "218 ₽ за 100 гр", "1 200 ₽/шт" — a unit rate, not the price.
            if _PER_UNIT_RE.search(line):
                continue
            for raw in re.findall(r'([\d    ]{2,15})\s*₽', line):
                try:
                    prices.append(Decimal(raw.translate(_SPACES)))
                except (InvalidOperation, ValueError):
                    continue

        if len(prices) == 3:
            return prices[1]
        if len(prices) == 1:
            return prices[0]
        return None

    @staticmethod
    def _title_from_regex(html: str) -> str | None:
        for pattern in (
            r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
            r'<h1[^>]*>(.*?)</h1>',
        ):
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                if len(text) > 3:
                    return text
        return None
