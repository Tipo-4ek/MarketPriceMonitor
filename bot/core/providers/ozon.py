"""Ozon marketplace provider built on Playwright.

A single, maintainable browser strategy replaces the previous pile of
bypass variants: launch a Chromium context with realistic fingerprint and
locale, render the product page, and read the price from the page's
JSON-LD block (with regex fallbacks). Anti-bot measures on marketplaces
evolve; this provider reflects a workable approach and exposes a
``headless`` toggle because a headed browser on a residential host is far
less likely to be challenged than a headless one in a datacenter.
"""

import asyncio
import json
import random
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse, urlunparse

from playwright.async_api import async_playwright

from bot.core.config import settings
from bot.core.logging import get_logger
from bot.core.providers.anti_bot.proxy_provider import ProxyProvider
from bot.core.providers.anti_bot.user_agent_pool import UserAgentPool
from bot.core.providers.base import ProductData, Provider
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)

_OZON_HOSTS = ('ozon.ru', 'www.ozon.ru', 'm.ozon.ru')

# Signals that Ozon served a challenge / block page instead of the product.
_BLOCK_MARKERS = ('доступ ограничен', 'access denied', 'checking your browser', 'ddos-guard')

# Minimal anti-automation shim. Kept readable on purpose — no obfuscation.
_STEALTH_INIT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = window.chrome || {runtime: {}};
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : origQuery(parameters);
"""


class OzonProvider(Provider):
    """Fetch product title and price from an Ozon product page."""

    def __init__(self) -> None:
        self.user_agent_pool = UserAgentPool()
        self.proxy_provider = self._init_proxy_provider()

    @staticmethod
    def _init_proxy_provider() -> ProxyProvider | None:
        """Build a proxy pool from configuration, if any is provided."""
        if settings.proxy_file:
            provider = ProxyProvider(proxy_file=settings.proxy_file)
            if provider.has_proxies():
                logger.info('Loaded %d proxies from %s', provider.pool_size(), settings.proxy_file)
                return provider
            logger.warning('Proxy file %s configured but no proxies were loaded', settings.proxy_file)
            return None
        if settings.proxy_url:
            logger.info('Using single configured proxy URL')
            return ProxyProvider(proxy_url=settings.proxy_url)
        logger.info('No proxy configured — Ozon may block requests from unknown IPs')
        return None

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
        html = await self._render(url)
        return self._parse(html, url)

    # --- rendering -------------------------------------------------------

    def _pick_proxy(self) -> dict | None:
        if self.proxy_provider and self.proxy_provider.has_proxies():
            return self.proxy_provider.get_random_proxy()
        return None

    async def _render(self, url: str) -> str:
        """Render the product page and return its HTML."""
        proxy = self._pick_proxy()
        proxy_config = None
        if proxy:
            proxy_config = {'server': proxy['server']}
            if proxy.get('username') and proxy.get('password'):
                proxy_config['username'] = proxy['username']
                proxy_config['password'] = proxy['password']
            logger.info('Using proxy %s', proxy['server'])

        playwright = browser = context = None
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=settings.headless_enabled,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--lang=ru-RU',
                ],
            )
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=self.user_agent_pool.get_random(),
                locale='ru-RU',
                timezone_id='Europe/Moscow',
                proxy=proxy_config,
                extra_http_headers={
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                },
            )
            await context.add_init_script(_STEALTH_INIT)
            page = await context.new_page()

            # Warm up on the homepage so Ozon sets its baseline cookies.
            try:
                await page.goto('https://www.ozon.ru/', wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(random.uniform(1.5, 3.0))
            except Exception as exc:  # noqa: BLE001 - warmup is best-effort
                logger.debug('Homepage warmup failed (continuing): %s', exc)

            logger.info('Fetching Ozon product: %s', url)
            await page.goto(url, wait_until='domcontentloaded', timeout=40000)
            await asyncio.sleep(random.uniform(2.0, 4.0))
            return await page.content()
        finally:
            if context:
                await context.close()
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

    # --- parsing ---------------------------------------------------------

    def _parse(self, html: str, url: str) -> ProductData:
        lowered = html[:5000].lower()
        if any(marker in lowered for marker in _BLOCK_MARKERS):
            raise ValueError('Ozon blocked the request (anti-bot challenge)')

        title = price = None
        json_ld = self._extract_json_ld(html)
        if json_ld:
            title = json_ld.get('name')
            price = self._price_from_offers(json_ld.get('offers'))

        if price is None:
            price = self._price_from_regex(html)
        if not title:
            title = self._title_from_regex(html)

        if price is None:
            raise ValueError('Could not extract price from Ozon page')

        return ProductData(title=title or 'Unknown product', price=price, currency='RUB', url=url)

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
    def _price_from_regex(html: str) -> Decimal | None:
        for pattern in (r'"cardPrice":\s*"?(\d+)"?', r'"price":\s*"?(\d[\d\s]*)\s*₽?"?'):
            match = re.search(pattern, html)
            if match:
                digits = match.group(1).replace(' ', '').replace('\xa0', '')
                try:
                    value = Decimal(digits)
                except (InvalidOperation, ValueError):
                    continue
                if 10 < value < 100_000_000:
                    return value
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
