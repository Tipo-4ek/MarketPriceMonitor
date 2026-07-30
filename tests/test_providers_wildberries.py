"""Tests for the Wildberries provider: URL handling and each price reader.

The card payload is the real shape returned by
``/__internal/u-card/cards/v4/detail`` (captured 2026-07-28), trimmed to the
fields the readers touch. Prices arrive in kopecks. The title fixture is the real
document title, which is where the third reader gets its price from.
"""

from dataclasses import dataclass
from decimal import Decimal

import pytest

from bot.core.providers.base import PriceNotFoundError
from bot.core.providers.strategies import PageMaterial
from bot.core.providers.wildberries import WildberriesProvider
from bot.core.providers.wildberries_parsers import (
    WILDBERRIES_STRATEGIES,
    card_api,
    dom_price,
    page_title,
)

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

DOC_TITLE = 'Кофе в зернах 250 гр, Суль-де-Минас ETNA COFFEE 219279898 купить за 558 ₽ в интернет‑магазине Wildberries'

URL = 'https://www.wildberries.ru/catalog/219279898/detail.aspx'


@dataclass
class FakeResponse:
    """Minimal stand-in for a Playwright Response."""

    url: str
    status: int = 200


def material(payload=None, widget_text='', title=''):
    return PageMaterial(url=URL, api_payload=payload, widget_text=widget_text, page_title=title)


@pytest.fixture
def provider():
    return WildberriesProvider()


def test_supports_requires_wb_host_and_article(provider):
    assert provider.supports(URL) is True
    assert provider.supports('https://wildberries.ru/catalog/1/detail.aspx?targetUrl=GP') is True
    # Host looks right but there is no article to fetch.
    assert provider.supports('https://www.wildberries.ru/promotions') is False
    # Look-alike host must not match.
    assert provider.supports('https://wildberries.ru.evil.com/catalog/1/detail.aspx') is False
    assert provider.supports('https://www.ozon.ru/product/x-1/') is False


async def test_normalize_rebuilds_canonical_url(provider):
    messy = 'https://www.wildberries.ru/catalog/219279898/detail.aspx?targetUrl=BP&size=123#reviews'
    assert await provider.normalize(messy) == URL


async def test_normalize_rejects_url_without_article(provider):
    with pytest.raises(PriceNotFoundError):
        await provider.normalize('https://www.wildberries.ru/promotions')


def test_provider_starts_with_the_declared_strategy_order(provider):
    assert provider.strategy_order == list(WILDBERRIES_STRATEGIES)


# --- card_api --------------------------------------------------------------


def test_card_api_reads_price_and_title():
    candidate = card_api(material(payload=CARD_PAYLOAD))
    # 55800 kopecks is the 558 ₽ the page displays, not the 1050 ₽ basic price.
    assert candidate.price == Decimal('558')
    assert candidate.title == 'ETNA COFFEE Кофе в зернах 250 гр, Суль-де-Минас'


def test_card_api_without_a_payload_is_simply_unusable():
    # The provider no longer treats a missed interception as a failure.
    assert card_api(material()).usable is False


def test_card_api_with_an_empty_product_list():
    assert card_api(material(payload={'data': {'products': []}})).price is None


def test_card_api_keeps_the_title_even_with_no_price():
    payload = {'data': {'products': [{'name': 'x', 'brand': 'B', 'sizes': [{'price': {}}]}]}}
    candidate = card_api(material(payload=payload))
    assert candidate.price is None
    assert candidate.title == 'B x'


def test_card_api_uses_the_first_priced_variant():
    payload = {'data': {'products': [{'sizes': [{'price': {}}, {'price': {'product': 129900}}]}]}}
    assert card_api(material(payload=payload)).price == Decimal('1299')


# --- dom_price -------------------------------------------------------------


def test_dom_price_takes_the_payable_figure_first():
    assert dom_price(material(widget_text='558 ₽\n1 050 ₽')).price == Decimal('558')


def test_dom_price_without_a_price():
    assert dom_price(material(widget_text='нет в наличии')).price is None


# --- page_title ------------------------------------------------------------


def test_page_title_reads_the_price_wildberries_writes_into_it():
    assert page_title(material(title=DOC_TITLE)).price == Decimal('558')


def test_page_title_ignores_a_title_without_a_price():
    assert page_title(material(title='Wildberries — интернет-магазин')).price is None


# --- the chain as the provider wires it ------------------------------------


async def test_chain_falls_through_to_the_title_when_the_api_was_missed(provider):
    """The whole point: a missed card response is no longer a dead end."""
    result = await provider._chain.run(material(payload=None, widget_text='', title=DOC_TITLE))

    assert result.winner == 'page_title'
    assert result.candidate.price == Decimal('558')


async def test_chain_prefers_the_api_when_it_is_there(provider):
    result = await provider._chain.run(material(payload=CARD_PAYLOAD, title=DOC_TITLE))

    assert result.winner == 'card_api'


# --- response matching ----------------------------------------------------


def test_card_response_matches_only_the_exact_article(provider):
    base = 'https://www.wildberries.ru/__internal/u-card/cards/v4/detail?appType=1&curr=rub'
    assert provider._is_card_response(FakeResponse(f'{base}&nm=219279898'), '219279898') is True
    # The page also batches sibling colours into one call; that payload is not
    # this product and must be ignored.
    assert provider._is_card_response(FakeResponse(f'{base}&nm=219279895;219279898'), '219279898') is False
    assert provider._is_card_response(FakeResponse(f'{base}&nm=219279898', status=403), '219279898') is False
    assert provider._is_card_response(FakeResponse('https://www.wildberries.ru/other'), '219279898') is False
