"""Tests for the Ozon provider: URL handling and HTML parsing (no network)."""
from decimal import Decimal

import pytest

from bot.core.providers.ozon import OzonProvider

JSON_LD_PAGE = """
<html><head>
<script type="application/ld+json">
{"@type": "Product", "name": "Bambu Lab P1S", "offers": {"@type": "Offer", "price": "84990", "priceCurrency": "RUB"}}
</script>
</head><body><h1 data-widget="webProductHeading">Bambu Lab P1S</h1></body></html>
"""

BLOCKED_PAGE = '<html><body><h1>Доступ ограничен</h1><p>Проверка браузера</p></body></html>'

NO_PRICE_PAGE = '<html><head><meta property="og:title" content="Some Product Name"></head><body></body></html>'


@pytest.fixture
def provider():
    return OzonProvider()


def test_supports_exact_host(provider):
    assert provider.supports('https://www.ozon.ru/product/test-123456/') is True
    assert provider.supports('https://ozon.ru/product/test-123456/') is True
    assert provider.supports('https://m.ozon.ru/product/-1/') is True
    # A look-alike host must not match.
    assert provider.supports('https://ozon.ru.evil.com/product/-1/') is False
    assert provider.supports('https://www.avito.ru/item') is False


@pytest.mark.asyncio
async def test_normalize_strips_query_and_fragment(provider):
    url = 'https://www.ozon.ru/product/nice-123456/?utm_source=x&foo=bar#reviews'
    assert await provider.normalize(url) == 'https://www.ozon.ru/product/nice-123456/'


def test_parse_reads_json_ld(provider):
    data = provider._parse(JSON_LD_PAGE, 'https://www.ozon.ru/product/-123456/')
    assert data.title == 'Bambu Lab P1S'
    assert data.price == Decimal('84990')
    assert data.currency == 'RUB'


def test_parse_raises_on_block_page(provider):
    with pytest.raises(ValueError, match='blocked'):
        provider._parse(BLOCKED_PAGE, 'https://www.ozon.ru/product/-1/')


def test_parse_raises_when_no_price(provider):
    with pytest.raises(ValueError, match='price'):
        provider._parse(NO_PRICE_PAGE, 'https://www.ozon.ru/product/-1/')


def test_price_from_offers_handles_dict_and_list(provider):
    assert provider._price_from_offers({'price': '1499'}) == Decimal('1499')
    assert provider._price_from_offers([{'price': '50'}, {'price': '60'}]) == Decimal('50')
    assert provider._price_from_offers(None) is None
    assert provider._price_from_offers([]) is None
