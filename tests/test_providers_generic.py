"""The generic provider: read a price from any page's markup, and refuse unsafe URLs.

The provider is opt-in (``GENERIC_PROVIDER_ENABLED``); the registry tests set the
flag explicitly. Each fetch test uses a distinct host so the shared per-host
throttle never makes one test wait on another's timestamp.
"""

from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from playwright.async_api import Error as PlaywrightError

from bot.core.config import settings
from bot.core.providers import ProviderRegistry
from bot.core.providers.base import PriceNotFoundError, ProviderBlockedError, UnsupportedURLError
from bot.core.providers.generic import GenericProvider
from bot.core.providers.wildberries import WildberriesProvider

SCHEMA_ORG = (
    '<html><head><script type="application/ld+json">'
    '{"@type":"Product","name":"Кофемолка","offers":{"price":"2499.00","priceCurrency":"RUB"}}'
    '</script></head><body></body></html>'
)


class FakePage:
    def __init__(self, *, content='<html></html>', title='', goto_raises=False):
        self._content = content
        self._title = title
        self._goto_raises = goto_raises
        self.url = 'about:blank'
        self.goto_calls: list[str] = []

    async def goto(self, url, **kwargs):
        self.goto_calls.append(url)
        if url == 'about:blank':
            self.url = 'about:blank'
            return
        if self._goto_raises:
            # Raise before advancing self.url, so a failed navigation leaves the
            # page blank rather than showing a previous product.
            raise PlaywrightError('net::ERR_ABORTED')
        self.url = url

    async def content(self):
        return self._content

    async def title(self):
        return self._title


class FakeSession:
    def __init__(self, page):
        self._page = page

    @asynccontextmanager
    async def page(self):
        yield self._page


@pytest.fixture(autouse=True)
def _resolves_public(monkeypatch):
    """Make the SSRF resolve-check see a public address, so the fake hosts below
    are fetchable. Tests that exercise the guard override this with their own."""

    async def fake(host):
        return ['93.184.216.34']

    monkeypatch.setattr('bot.core.providers.url_safety._resolved_ips', fake)


def test_supports_public_http_but_not_unsafe():
    provider = GenericProvider()
    assert provider.supports('https://shop.example/p/1') is True
    assert provider.supports('http://dns-shop.ru/product/x') is True
    assert provider.supports('http://127.0.0.1/admin') is False
    assert provider.supports('http://192.168.0.39:8123/') is False
    assert provider.supports('http://localhost/') is False
    assert provider.supports('ftp://example.com/x') is False
    assert provider.supports('file:///etc/passwd') is False


async def test_reads_schema_org_price_from_any_site():
    provider = GenericProvider(session=FakeSession(FakePage(content=SCHEMA_ORG)))
    data = await provider.fetch_product('https://shop-a.example/p/1')
    assert data.price == Decimal('2499.00')
    assert data.title == 'Кофемолка'
    assert data.currency == 'RUB'
    assert data.url == 'https://shop-a.example/p/1'


async def test_a_page_with_no_markup_is_price_not_found():
    provider = GenericProvider(session=FakeSession(FakePage(content='<html><body>no price here</body></html>')))
    with pytest.raises(PriceNotFoundError):
        await provider.fetch_product('https://shop-b.example/p/2')


async def test_a_failed_navigation_is_blocked_not_a_stale_price():
    stale = FakePage(content=SCHEMA_ORG, goto_raises=True)  # page still shows a previous product
    provider = GenericProvider(session=FakeSession(stale))
    with pytest.raises(ProviderBlockedError):
        await provider.fetch_product('https://shop-c.example/p/3')
    assert stale.goto_calls == ['about:blank', 'https://shop-c.example/p/3']
    assert stale.url == 'about:blank'


async def test_refuses_a_host_that_resolves_to_an_internal_address(monkeypatch):
    # The realistic SSRF: an attacker points a public name at the LAN.
    async def resolves_internal(host):
        return ['192.168.0.39']

    monkeypatch.setattr('bot.core.providers.url_safety._resolved_ips', resolves_internal)
    provider = GenericProvider(session=FakeSession(FakePage(content=SCHEMA_ORG)))
    with pytest.raises(UnsupportedURLError):
        await provider.fetch_product('https://pwn.attacker.test/p')


async def test_refuses_a_redirect_that_lands_on_an_internal_host(monkeypatch):
    # Host resolves public, so the fetch starts, but the page redirects to a LAN
    # address; reading that document must be refused.
    async def resolves(host):
        return ['10.0.0.9'] if host == 'router.attacker.test' else ['93.184.216.34']

    monkeypatch.setattr('bot.core.providers.url_safety._resolved_ips', resolves)

    class RedirectingPage(FakePage):
        async def goto(self, url, **kwargs):
            self.goto_calls.append(url)
            self.url = 'about:blank' if url == 'about:blank' else 'http://router.attacker.test/admin'

    provider = GenericProvider(session=FakeSession(RedirectingPage(content=SCHEMA_ORG)))
    with pytest.raises(UnsupportedURLError):
        await provider.fetch_product('https://front.attacker.test/p')


def test_generic_is_off_by_default(monkeypatch):
    monkeypatch.setattr(settings, 'generic_provider_enabled', False)
    registry = ProviderRegistry()
    assert isinstance(registry.find_provider('https://www.wildberries.ru/catalog/1/detail.aspx'), WildberriesProvider)
    with pytest.raises(UnsupportedURLError):
        registry.find_provider('https://dns-shop.ru/product/abc/')  # no generic -> refused


def test_registry_routes_specific_first_then_generic_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, 'generic_provider_enabled', True)
    registry = ProviderRegistry()
    wb = registry.find_provider('https://www.wildberries.ru/catalog/219279898/detail.aspx')
    other = registry.find_provider('https://dns-shop.ru/product/abc/')
    assert isinstance(wb, WildberriesProvider)
    assert isinstance(other, GenericProvider)


def test_registry_refuses_unsafe_urls_even_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, 'generic_provider_enabled', True)
    registry = ProviderRegistry()
    for bad in (
        'http://169.254.169.254/latest/meta-data/',
        'http://192.168.0.39:8123/',
        'http://localhost:5432/',
    ):
        with pytest.raises(UnsupportedURLError):
            registry.find_provider(bad)


def test_registry_honours_the_deployment_blocklist(monkeypatch):
    monkeypatch.setattr(settings, 'generic_provider_enabled', True)
    monkeypatch.setattr(settings, 'blocked_hosts', 'tipo-nas.ru, 203.0.113.7')
    registry = ProviderRegistry()
    for bad in ('https://tipo-nas.ru/x', 'https://ha.tipo-nas.ru/x', 'http://203.0.113.7/x'):
        with pytest.raises(UnsupportedURLError):
            registry.find_provider(bad)
    assert isinstance(registry.find_provider('https://other.example/p'), GenericProvider)
