"""Test configuration and fixtures."""
import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.models.base import Base

# Test database URL
TEST_DATABASE_URL = os.getenv(
    'DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@db:5432/price_tracker_test'
)


@pytest.fixture(scope='session')
def event_loop():
    """Create event loop for tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope='function')
async def db_session():
    """Create a test database session."""
    # Create engine
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    session = async_session()

    try:
        yield session
    finally:
        await session.close()

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

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
        provider=ProviderEnum.OZON,
        url='https://www.ozon.ru/product/-123456/',
        title='Test Product',
        currency='RUB',
        last_price=Decimal('1000.00'),
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


