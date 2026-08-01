"""Test configuration and fixtures.

Tests run against an in-memory SQLite database by default, so they need no
running Postgres. Override TEST_DATABASE_URL to point at another engine.
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bot.core.config import settings
from bot.models.base import Base

TEST_DATABASE_URL = os.getenv('TEST_DATABASE_URL', 'sqlite+aiosqlite://')

# Values the assertions below are written against. `settings` is a module-level
# singleton that reads the developer's real .env at import time, so without this
# the suite passes or fails depending on whose machine it runs on — exporting
# ADMIN_TG_IDS or ALERT_COOLDOWN_HOURS was enough to turn it red.
_TEST_SETTINGS = {
    'admin_tg_ids': '123456789',
    'default_locale': 'ru',
    'default_threshold_delta': 5,
    'alert_cooldown_hours': 24,
    'provider_error_window_seconds': 300,
    'provider_error_threshold': 5,
}


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Pin the settings the tests assert on, whatever the ambient environment."""
    for name, value in _TEST_SETTINGS.items():
        monkeypatch.setattr(settings, name, value)
    return settings


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    """Neutralise the global per-host throttle so tests never sleep 30s.

    The real interval is exercised by test_throttle.py against its own Throttle
    instances; anything driving the live fetch path here should not pay it.
    """
    from bot.core.providers.throttle import throttle

    monkeypatch.setattr(throttle, 'min_interval_seconds', 0.0)
    throttle._last_request.clear()


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset the module-global health monitor and alert manager between tests.

    Both are process-level singletons; without this a recorded alert or error in
    one test would leak its 24h cooldown or its error window into the next, and
    the suite would pass or fail on ordering.
    """
    from bot.core.alerts import alert_manager
    from bot.core.providers.health import health_monitor

    health_monitor.reset()
    alert_manager.reset()
    alert_manager.enable_alerts()
    yield
    health_monitor.reset()
    alert_manager.reset()
    alert_manager.enable_alerts()


@pytest.fixture(scope='session')
def configured_dispatcher():
    """One Dispatcher with every handler wired, shared across the session.

    The handler routers are module-level singletons: aiogram attaches each to a
    single Dispatcher per process, so the integration tests must share one.
    """
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    from bot.handlers import setup_handlers

    dp = Dispatcher(storage=MemoryStorage())
    setup_handlers(dp)
    return dp


def _make_engine():
    """Create the test engine, keeping in-memory SQLite alive across connections."""
    if TEST_DATABASE_URL.startswith('sqlite') and ':memory:' not in TEST_DATABASE_URL:
        # 'sqlite+aiosqlite://' is an in-memory DB; share one connection so the
        # schema created below is visible to every session in the test.
        return create_async_engine(
            TEST_DATABASE_URL,
            poolclass=StaticPool,
            connect_args={'check_same_thread': False},
        )
    return create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture(scope='function')
async def db_session():
    """Provide a session against a freshly-created schema, torn down after."""
    engine = _make_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    session = async_session()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession):
    """Create a sample user."""
    from bot.models import User

    user = User(tg_user_id=12345, locale='ru')
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_product(db_session: AsyncSession):
    """Create a sample product."""
    from decimal import Decimal

    from bot.models import Product
    from bot.models.enums import ProviderEnum

    product = Product(
        provider=ProviderEnum.WILDBERRIES,
        url='https://www.wildberries.ru/catalog/219279898/detail.aspx',
        title='Test Product',
        currency='RUB',
        last_price=Decimal('1000.00'),
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product
