"""Tests for add, list, remove functionality."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.services.product_service import ProductService
from bot.core.services.tracking_service import TrackingService
from bot.models import Product, User


@pytest.mark.asyncio
async def test_add_tracking(db_session: AsyncSession, sample_user: User, sample_product: Product):
    """Test adding a tracking."""
    tracking, created = await TrackingService.add_tracking(db_session, sample_user, sample_product)
    await db_session.commit()

    assert created is True
    assert tracking.user_id == sample_user.id
    assert tracking.product_id == sample_product.id
    assert tracking.custom_threshold_delta is None


@pytest.mark.asyncio
async def test_add_tracking_duplicate(db_session: AsyncSession, sample_user: User, sample_product: Product):
    """Test adding duplicate tracking."""
    # Add first time
    tracking1, created1 = await TrackingService.add_tracking(db_session, sample_user, sample_product)
    await db_session.commit()

    # Add second time
    tracking2, created2 = await TrackingService.add_tracking(db_session, sample_user, sample_product)
    await db_session.commit()

    assert created1 is True
    assert created2 is False
    assert tracking1.id == tracking2.id


@pytest.mark.asyncio
async def test_list_trackings(db_session: AsyncSession, sample_user: User, sample_product: Product):
    """Test listing user trackings."""
    # Add tracking
    await TrackingService.add_tracking(db_session, sample_user, sample_product)
    await db_session.commit()

    # List trackings
    trackings = await TrackingService.get_user_trackings(db_session, sample_user)

    assert len(trackings) == 1
    tracking, product = trackings[0]
    assert product.id == sample_product.id
    assert product.title == sample_product.title


@pytest.mark.asyncio
async def test_remove_tracking(db_session: AsyncSession, sample_user: User, sample_product: Product):
    """Test removing a tracking."""
    # Add tracking
    await TrackingService.add_tracking(db_session, sample_user, sample_product)
    await db_session.commit()

    # Remove tracking
    removed = await TrackingService.remove_tracking(db_session, sample_user, sample_product.id)
    await db_session.commit()

    assert removed is True

    # Verify removed
    trackings = await TrackingService.get_user_trackings(db_session, sample_user)
    assert len(trackings) == 0


@pytest.mark.asyncio
async def test_remove_nonexistent_tracking(db_session: AsyncSession, sample_user: User):
    """Test removing non-existent tracking."""
    removed = await TrackingService.remove_tracking(db_session, sample_user, 9999)
    assert removed is False


