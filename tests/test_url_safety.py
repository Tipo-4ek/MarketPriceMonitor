"""The fetch-safety gate: only ordinary public http(s) URLs, minus the block list."""

import pytest

from bot.core.providers.url_safety import is_blocked_host, is_fetchable, is_safe_url


def _resolves_to(monkeypatch, addresses):
    async def fake(host):
        return list(addresses)

    monkeypatch.setattr('bot.core.providers.url_safety._resolved_ips', fake)


@pytest.mark.parametrize(
    'url',
    [
        'https://www.wildberries.ru/catalog/1/detail.aspx',
        'http://dns-shop.ru/product/x',
        'https://shop.example:8443/p',
        'http://93.184.216.34/p',  # an ordinary public IP literal
    ],
)
def test_safe_urls(url):
    assert is_safe_url(url) is True


@pytest.mark.parametrize(
    'url',
    [
        'http://localhost/',
        'http://localhost:5432/',
        'https://router.local/',
        'https://svc.internal/',
        'http://127.0.0.1/admin',
        'http://192.168.0.39:8123/',  # a LAN service (e.g. Home Assistant)
        'http://10.0.0.5/',
        'http://172.16.4.4/',
        'http://169.254.169.254/latest/meta-data/',  # cloud metadata endpoint
        'http://[::1]/',
        'http://0.0.0.0/',
        'ftp://example.com/x',
        'file:///etc/passwd',
        'javascript:alert(1)',
        'not a url at all',
        '',
    ],
)
def test_unsafe_urls(url):
    assert is_safe_url(url) is False


def test_blocklist_matches_host_and_subdomains():
    blocked = frozenset({'tipo-nas.ru', '203.0.113.7'})
    assert is_blocked_host('https://tipo-nas.ru/x', blocked) is True
    assert is_blocked_host('https://ha.tipo-nas.ru/x', blocked) is True  # subdomain
    assert is_blocked_host('http://203.0.113.7/x', blocked) is True
    assert is_blocked_host('https://not-tipo-nas.ru/x', blocked) is False  # not a subdomain
    assert is_blocked_host('https://other.example/x', blocked) is False
    assert is_blocked_host('https://tipo-nas.ru/x', frozenset()) is False


async def test_is_fetchable_blocks_a_name_that_resolves_internal(monkeypatch):
    _resolves_to(monkeypatch, ['10.0.0.5'])  # the attacker points a public name at the LAN
    assert await is_fetchable('http://shop.attacker.test/', frozenset()) is False


async def test_is_fetchable_blocks_numeric_ip_encodings(monkeypatch):
    # http://2130706433/ decodes to 127.0.0.1; the literal check misses it, DNS does not.
    _resolves_to(monkeypatch, ['127.0.0.1'])
    assert await is_fetchable('http://2130706433/', frozenset()) is False


async def test_is_fetchable_allows_a_public_name(monkeypatch):
    _resolves_to(monkeypatch, ['93.184.216.34'])
    assert await is_fetchable('https://shop.example/p', frozenset()) is True


async def test_is_fetchable_blocks_a_name_resolving_to_a_blocklisted_ip(monkeypatch):
    _resolves_to(monkeypatch, ['203.0.113.7'])  # e.g. a deployment's own public IP
    assert await is_fetchable('https://front.example/', frozenset({'203.0.113.7'})) is False


async def test_is_fetchable_refuses_when_resolution_fails(monkeypatch):
    async def boom(host):
        raise OSError('name resolution failed')

    monkeypatch.setattr('bot.core.providers.url_safety._resolved_ips', boom)
    assert await is_fetchable('https://nope.example/', frozenset()) is False


async def test_is_fetchable_needs_no_dns_for_a_public_literal_ip():
    assert await is_fetchable('http://93.184.216.34/p', frozenset()) is True


async def test_is_fetchable_rejects_a_literal_internal_ip():
    assert await is_fetchable('http://192.168.0.39:8123/', frozenset()) is False
