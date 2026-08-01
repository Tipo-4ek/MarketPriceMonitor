"""ProductService.get_or_create_product: creation, reuse and the concurrent race."""

from decimal import Decimal

import pytest

from bot.core.providers.base import ProductData
from bot.core.services.product_service import ProductService
from bot.models import Product
from bot.models.enums import ProviderEnum

URL = 'https://www.wildberries.ru/catalog/219279898/detail.aspx'


class StubProvider:
    provider_type = ProviderEnum.WILDBERRIES

    def supports(self, url):
        return True

    async def normalize(self, url):
        return URL

    async def fetch_product(self, url):
        return ProductData(title='ETNA Кофе', price=Decimal('558'), currency='RUB', url=URL)


class StubRegistry:
    def find_provider(self, url):
        return StubProvider()


@pytest.fixture(autouse=True)
def _stub_registry(monkeypatch):
    monkeypatch.setattr('bot.core.services.product_service.provider_registry', StubRegistry())


async def test_creates_a_product_on_first_sight(db_session):
    product, created = await ProductService.get_or_create_product(db_session, URL)
    await db_session.commit()
    assert created is True
    assert product.last_price == Decimal('558')
    assert product.title == 'ETNA Кофе'


async def test_reuses_an_existing_product(db_session):
    first, _ = await ProductService.get_or_create_product(db_session, URL)
    await db_session.commit()
    second, created = await ProductService.get_or_create_product(db_session, URL)
    assert created is False
    assert second.id == first.id


async def test_a_concurrent_insert_race_returns_the_winners_row(db_session, monkeypatch):
    """The loser of a two-/add race hits the unique constraint and re-selects
    the row the winner committed, instead of surfacing a generic error."""
    from sqlalchemy.exc import IntegrityError

    winner = Product(
        provider=ProviderEnum.WILDBERRIES, url=URL, title='Winner', currency='RUB', last_price=Decimal('558')
    )

    calls = {'find': 0}

    async def _find_after_race(session, normalized_url, provider_type):
        # First call is our own initial SELECT (nothing yet); the second is the
        # re-select after the IntegrityError, when the winner's row exists.
        calls['find'] += 1
        return winner if calls['find'] > 1 else None

    monkeypatch.setattr(ProductService, '_find', staticmethod(_find_after_race))

    async def _boom(*_a, **_k):
        raise IntegrityError('INSERT', {}, Exception('duplicate key'))

    monkeypatch.setattr(db_session, 'flush', _boom)

    product, created = await ProductService.get_or_create_product(db_session, URL)
    assert created is False
    assert product is winner
