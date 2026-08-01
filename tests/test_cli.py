"""market-price-check: the "is it still working?" command and its exit codes."""

from decimal import Decimal

import pytest

from bot.cli import check
from bot.core.providers.base import ProductData, ProviderBlockedError, UnsupportedURLError

URL = 'https://www.wildberries.ru/catalog/219279898/detail.aspx'


class StubProvider:
    provider_type = type('P', (), {'value': 'wildberries'})()

    def __init__(self, *, data=None, error=None):
        self._data = data
        self._error = error

    async def normalize(self, url):
        return url

    async def fetch_product(self, url):
        if self._error:
            raise self._error
        return self._data


class StubRegistry:
    def __init__(self, provider=None, unsupported=False):
        self._provider = provider
        self._unsupported = unsupported

    def find_provider(self, url):
        if self._unsupported:
            raise UnsupportedURLError(url)
        return self._provider


@pytest.fixture(autouse=True)
def _no_browser(monkeypatch):
    """The CLI closes the shared browser in a finally; stub it so no Chrome starts."""

    async def _noop():
        return None

    monkeypatch.setattr('bot.cli.browser_session.close', _noop)


async def test_exit_zero_when_a_price_is_read(monkeypatch, capsys):
    data = ProductData(title='Кофе', price=Decimal('558'), currency='RUB', url=URL)
    monkeypatch.setattr('bot.cli.provider_registry', StubRegistry(StubProvider(data=data)))

    code = await check([URL])

    assert code == 0
    out = capsys.readouterr().out
    assert 'OK' in out
    assert '558' in out


async def test_exit_one_when_the_marketplace_refuses(monkeypatch, capsys):
    monkeypatch.setattr('bot.cli.provider_registry', StubRegistry(StubProvider(error=ProviderBlockedError('anti-bot'))))

    code = await check([URL])

    assert code == 1
    assert 'FAIL' in capsys.readouterr().out


async def test_exit_one_on_an_unsupported_url(monkeypatch, capsys):
    monkeypatch.setattr('bot.cli.provider_registry', StubRegistry(unsupported=True))

    code = await check(['https://example.com/thing'])

    assert code == 1
    assert 'FAIL' in capsys.readouterr().out
