"""Tests for the Wildberries provider: URL handling and card-payload parsing.

The payload below is the real shape returned by
``/__internal/u-card/cards/v4/detail`` (captured 2026-07-28), trimmed to the
fields the provider reads. Prices arrive in kopecks.
"""

from dataclasses import dataclass
from decimal import Decimal

import pytest

from bot.core.providers.base import PriceNotFoundError
from bot.core.providers.wildberries import WildberriesProvider

CARD_PAYLOAD = {
    'data': {
        'products': [
            {
                'id': 219279898,
                'name': 'Кофе в зернах 250 гр, Суль-де-Минас',
                'brand': 'ETNA COFFEE',
                'sizes': [{'price': {'basic': 105000, 'product': 55800, 'logistics': 0}}],
            }
        ]
    }
}


@dataclass
class FakeResponse:
    """Minimal stand-in for a Playwright Response."""

    url: str
    status: int = 200


@pytest.fixture
def provider():
    return WildberriesProvider()


def test_supports_requires_wb_host_and_article(provider):
    assert provider.supports('https://www.wildberries.ru/catalog/219279898/detail.aspx') is True
    assert provider.supports('https://wildberries.ru/catalog/1/detail.aspx?targetUrl=GP') is True
    # Host looks right but there is no article to fetch.
    assert provider.supports('https://www.wildberries.ru/promotions') is False
    # Look-alike host must not match.
    assert provider.supports('https://wildberries.ru.evil.com/catalog/1/detail.aspx') is False
    assert provider.supports('https://www.ozon.ru/product/x-1/') is False


async def test_normalize_rebuilds_canonical_url(provider):
    messy = 'https://www.wildberries.ru/catalog/219279898/detail.aspx?targetUrl=BP&size=123#reviews'
    assert await provider.normalize(messy) == 'https://www.wildberries.ru/catalog/219279898/detail.aspx'


async def test_normalize_rejects_url_without_article(provider):
    with pytest.raises(PriceNotFoundError):
        await provider.normalize('https://www.wildberries.ru/promotions')


def test_parses_price_and_title_from_card_payload(provider):
    data = provider._parse(CARD_PAYLOAD, '219279898', 'https://www.wildberries.ru/catalog/219279898/detail.aspx')
    assert data.title == 'ETNA COFFEE Кофе в зернах 250 гр, Суль-де-Минас'
    # 55800 kopecks is the 558 ₽ the page displays, not the 1050 ₽ basic price.
    assert data.price == Decimal('558')
    assert data.currency == 'RUB'


def test_empty_product_list_raises(provider):
    with pytest.raises(PriceNotFoundError):
        provider._parse({'data': {'products': []}}, '1', 'https://www.wildberries.ru/catalog/1/detail.aspx')


def test_missing_price_raises(provider):
    payload = {'data': {'products': [{'name': 'x', 'sizes': [{'price': {}}]}]}}
    with pytest.raises(PriceNotFoundError):
        provider._parse(payload, '1', 'https://www.wildberries.ru/catalog/1/detail.aspx')


def test_price_uses_first_variant_that_has_one(provider):
    product = {'sizes': [{'price': {}}, {'price': {'product': 129900}}]}
    assert provider._price(product) == Decimal('1299')


def test_card_response_matches_only_the_exact_article(provider):
    base = 'https://www.wildberries.ru/__internal/u-card/cards/v4/detail?appType=1&curr=rub'
    assert provider._is_card_response(FakeResponse(f'{base}&nm=219279898'), '219279898') is True
    # The page also batches sibling colours into one call; that payload is not
    # this product and must be ignored.
    assert provider._is_card_response(FakeResponse(f'{base}&nm=219279895;219279898'), '219279898') is False
    assert provider._is_card_response(FakeResponse(f'{base}&nm=219279898', status=403), '219279898') is False
    assert provider._is_card_response(FakeResponse('https://www.wildberries.ru/other'), '219279898') is False
