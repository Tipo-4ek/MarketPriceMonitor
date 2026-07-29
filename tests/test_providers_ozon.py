"""Tests for the Ozon provider: URL handling and page parsing (no network).

The HTML fixtures below are trimmed from a real ozon.ru product page captured
on 2026-07-28 — including the shape of the anti-bot page, which is what the
provider sees far more often than a product.
"""

from decimal import Decimal

import pytest

from bot.core.providers.base import PriceNotFoundError, ProductData
from bot.core.providers.ozon import OzonProvider

JSON_LD_PAGE = """
<html><head>
<script type="application/ld+json">
{"@context": "http://schema.org", "@type": "Product", "name": "Кофе в зернах Tasty Coffee Натти, 1 кг",
 "sku": "715106535",
 "offers": {"@type": "Offer", "availability": "http://schema.org/InStock",
            "price": "2414", "priceCurrency": "RUB"}}
</script>
</head><body><h1 data-widget="webProductHeading">Кофе в зернах Tasty Coffee Натти, 1 кг</h1></body></html>
"""

# JSON-LD without offers: Ozon serves this for some cards, and the widget is
# then the only source of a price.
NO_OFFERS_PAGE = """
<html><head>
<script type="application/ld+json">
{"@type": "Product", "name": "Товар без offers", "aggregateRating": {"ratingValue": "4.9"}}
</script>
<meta property="og:title" content="Товар без offers">
</head><body></body></html>
"""

BLOCKED_PAGE = '<html><head><title>Antibot Challenge Page</title></head><body>Доступ ограничен</body></html>'

NO_PRICE_PAGE = '<html><head><meta property="og:title" content="Some Product Name"></head><body></body></html>'

# Exactly what [data-widget="webPrice"] innerText looks like: Ozon-card price,
# regular price, struck-through old price.
WIDGET_TEXT = '2 173 ₽\nС банками\n2 414 ₽\n4 557 ₽\nС другими банками\n218 ₽ за 100 гр'


@pytest.fixture
def provider():
    return OzonProvider()


def test_supports_exact_host(provider):
    assert provider.supports('https://www.ozon.ru/product/test-123456/') is True
    assert provider.supports('https://ozon.ru/product/test-123456/') is True
    assert provider.supports('https://m.ozon.ru/product/-1/') is True
    # A look-alike host must not match.
    assert provider.supports('https://ozon.ru.evil.com/product/-1/') is False
    assert provider.supports('https://www.wildberries.ru/catalog/1/detail.aspx') is False


async def test_normalize_strips_query_and_fragment(provider):
    url = 'https://www.ozon.ru/product/nice-123456/?utm_source=x&foo=bar#reviews'
    assert await provider.normalize(url) == 'https://www.ozon.ru/product/nice-123456/'


def test_reads_price_and_title_from_json_ld(provider):
    assert provider._title(JSON_LD_PAGE) == 'Кофе в зернах Tasty Coffee Натти, 1 кг'
    assert provider._price(JSON_LD_PAGE, '') == Decimal('2414')


def test_falls_back_to_widget_when_json_ld_has_no_offers(provider):
    # The widget's second figure is the regular price — the same number JSON-LD
    # reports when it is present, so the two paths agree.
    assert provider._price(NO_OFFERS_PAGE, WIDGET_TEXT) == Decimal('2414')
    assert provider._title(NO_OFFERS_PAGE) == 'Товар без offers'


def test_widget_with_a_single_price_is_used_as_is(provider):
    assert provider._price_from_widget('899 ₽') == Decimal('899')


def test_widget_without_any_price_yields_none(provider):
    assert provider._price_from_widget('нет в наличии') is None


def test_block_reason_names_the_challenge(provider):
    # Arrival is decided by whether the price widget appeared; this only has to
    # explain *why* it did not, for the log and the admin alert.
    reason = provider._block_reason(BLOCKED_PAGE)
    assert 'anti-bot' in reason
    assert 'antibot challenge' in reason


def test_block_reason_falls_back_to_timeout_wording(provider):
    # A page with no challenge marker that still never rendered is a timeout,
    # and must not be reported as a block we recognised.
    reason = provider._block_reason(NO_PRICE_PAGE)
    assert 'timeout' in reason
    assert 'matched' not in reason


def test_page_without_price_yields_nothing(provider):
    assert provider._price(NO_PRICE_PAGE, '') is None


def test_price_from_offers_handles_dict_and_list(provider):
    assert provider._price_from_offers({'price': '1499'}) == Decimal('1499')
    assert provider._price_from_offers([{'price': '50'}, {'price': '60'}]) == Decimal('50')
    assert provider._price_from_offers(None) is None
    assert provider._price_from_offers([]) is None


def test_out_of_stock_zero_price_is_rejected():
    # Ozon serves "price": 0 for unavailable items; letting that through used to
    # divide by zero in the scheduler on the next poll.
    with pytest.raises(PriceNotFoundError):
        ProductData(title='x', price=Decimal(0), currency='RUB', url='https://www.ozon.ru/product/-1/')
