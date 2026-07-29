"""Tests for the polling scheduler: notification rules and failure handling."""

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bot.core.providers.base import ProductData, Provider, ProviderBlockedError
from bot.core.providers.health import HealthMonitor
from bot.core.scheduler import PriceScheduler
from bot.models import PriceHistory, Product, Tracking, User, base
from bot.models.base import Base
from bot.models.enums import ProviderEnum, ProviderStatus

URL = 'https://www.ozon.ru/product/thing-1/'


class FakeBot:
    """Records what would have been sent to Telegram."""

    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


class FakeProvider(Provider):
    """Returns a price we control, or raises on demand."""

    def __init__(self, price=Decimal('100'), title='Thing', error=None):
        self.price = price
        self.title = title
        self.error = error
        self.calls = 0

    @property
    def provider_type(self):
        return ProviderEnum.OZON

    def supports(self, url):
        return True

    async def normalize(self, url):
        return url

    async def fetch_product(self, url):
        self.calls += 1
        if self.error:
            raise self.error
        return ProductData(title=self.title, price=self.price, currency='RUB', url=url)


class FakeRegistry:
    def __init__(self, provider):
        self._provider = provider

    def get_provider(self, provider_type):
        return self._provider


@pytest_asyncio.fixture
async def wired_db(monkeypatch):
    """Point the global session maker at a fresh in-memory database."""
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(base, 'async_session_maker', maker)

    async with maker() as session:
        user = User(tg_user_id=42, locale='ru')
        product = Product(provider=ProviderEnum.OZON, url=URL, title='Thing', currency='RUB', last_price=Decimal('100'))
        session.add_all([user, product])
        await session.flush()
        session.add(Tracking(user_id=user.id, product_id=product.id))
        await session.commit()
        product_id = product.id

    yield maker, product_id
    await engine.dispose()


@pytest_asyncio.fixture
async def clean_health(monkeypatch):
    """Give each test its own health monitor rather than the global one."""
    monitor = HealthMonitor()
    monkeypatch.setattr('bot.core.scheduler.health_monitor', monitor)
    return monitor


async def test_unchanged_price_notifies_nobody(wired_db, clean_health, isolated_settings):
    _, _ = wired_db
    bot = FakeBot()
    scheduler = PriceScheduler(bot, FakeRegistry(FakeProvider(price=Decimal('100'))))

    await scheduler._check_prices()

    assert bot.sent == []


async def test_price_move_past_the_threshold_notifies(wired_db, clean_health, isolated_settings):
    maker, product_id = wired_db
    bot = FakeBot()
    scheduler = PriceScheduler(bot, FakeRegistry(FakeProvider(price=Decimal('50'))))

    await scheduler._check_prices()

    assert len(bot.sent) == 1
    chat_id, text = bot.sent[0]
    assert chat_id == 42
    assert '50' in text

    async with maker() as session:
        product = await session.get(Product, product_id)
        assert product.last_price == Decimal('50')
        history = (await session.execute(select(PriceHistory))).scalars().all()
        assert len(history) == 1


async def test_price_move_below_the_threshold_is_recorded_but_silent(wired_db, clean_health, isolated_settings):
    maker, product_id = wired_db
    # Default threshold is 5%; 100 -> 98 is a 2% move.
    bot = FakeBot()
    scheduler = PriceScheduler(bot, FakeRegistry(FakeProvider(price=Decimal('98'))))

    await scheduler._check_prices()

    assert bot.sent == []
    async with maker() as session:
        product = await session.get(Product, product_id)
        assert product.last_price == Decimal('98')


async def test_a_zero_starting_price_does_not_divide_by_zero(wired_db, clean_health, isolated_settings):
    maker, product_id = wired_db
    async with maker() as session:
        product = await session.get(Product, product_id)
        product.last_price = Decimal('0')
        await session.commit()

    bot = FakeBot()
    scheduler = PriceScheduler(bot, FakeRegistry(FakeProvider(price=Decimal('123'))))

    await scheduler._check_prices()

    assert len(bot.sent) == 1
    async with maker() as session:
        product = await session.get(Product, product_id)
        assert product.last_price == Decimal('123')


async def test_a_blocked_provider_is_recorded_as_an_error(wired_db, clean_health, isolated_settings):
    bot = FakeBot()
    provider = FakeProvider(error=ProviderBlockedError('anti-bot'))
    scheduler = PriceScheduler(bot, FakeRegistry(provider))

    await scheduler._check_prices()

    assert provider.calls == 1
    assert bot.sent == []
    assert len(clean_health.errors[ProviderEnum.OZON]) == 1


async def test_a_down_provider_is_skipped_for_several_cycles(wired_db, clean_health, isolated_settings):
    bot = FakeBot()
    provider = FakeProvider(error=ProviderBlockedError('anti-bot'))
    scheduler = PriceScheduler(bot, FakeRegistry(provider))

    # Drive it to DOWN.
    for _ in range(isolated_settings.provider_error_threshold):
        await scheduler._check_prices()
    assert clean_health.get_status(ProviderEnum.OZON) is ProviderStatus.DOWN

    calls_when_down = provider.calls

    # The next few cycles must not touch the marketplace at all.
    await scheduler._check_prices()
    await scheduler._check_prices()
    assert provider.calls == calls_when_down

    # After the backoff it is tried once more.
    await scheduler._check_prices()
    await scheduler._check_prices()
    assert provider.calls > calls_when_down


async def test_one_failing_product_does_not_abort_the_cycle(wired_db, clean_health, isolated_settings):
    """A rollback for one product used to expire the shared session and skip the rest."""
    maker, first_id = wired_db
    async with maker() as session:
        user = (await session.execute(select(User))).scalars().first()
        second = Product(
            provider=ProviderEnum.OZON,
            url=URL + '2',
            title='Other',
            currency='RUB',
            last_price=Decimal('200'),
        )
        session.add(second)
        await session.flush()
        session.add(Tracking(user_id=user.id, product_id=second.id))
        await session.commit()
        second_id = second.id

    class FlakyProvider(FakeProvider):
        async def fetch_product(self, url):
            self.calls += 1
            if url.endswith('2'):
                return ProductData(title='Other', price=Decimal('100'), currency='RUB', url=url)
            raise ProviderBlockedError('anti-bot')

    bot = FakeBot()
    scheduler = PriceScheduler(bot, FakeRegistry(FlakyProvider()))

    await scheduler._check_prices()

    # The second product was still polled and written despite the first failing.
    async with maker() as session:
        assert (await session.get(Product, second_id)).last_price == Decimal('100')
        assert (await session.get(Product, first_id)).last_price == Decimal('100')


@pytest.mark.parametrize('bad_title', ['Thing & Co <b>', 'A < B & C'])
async def test_marketplace_titles_are_escaped_in_notifications(wired_db, clean_health, isolated_settings, bad_title):
    maker, product_id = wired_db
    # The notification renders the stored title, which came from a marketplace
    # page when the product was added.
    async with maker() as session:
        product = await session.get(Product, product_id)
        product.title = bad_title
        await session.commit()

    bot = FakeBot()
    scheduler = PriceScheduler(bot, FakeRegistry(FakeProvider(price=Decimal('50'))))

    await scheduler._check_prices()

    assert len(bot.sent) == 1
    _, text = bot.sent[0]
    # Telegram rejects the whole message on an unescaped '<', so the raw title
    # must not reach it.
    assert bad_title not in text
    assert '&amp;' in text
    assert '&lt;' in text
