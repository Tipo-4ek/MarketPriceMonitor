"""Tests for monitor rules (thresholds)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.services.tracking_service import TrackingService
from bot.models import Product, User


@pytest.mark.asyncio
async def test_custom_threshold(db_session: AsyncSession, sample_user: User, sample_product: Product):
    """Test setting custom threshold for tracking."""
    # Add tracking
    _tracking, _ = await TrackingService.add_tracking(db_session, sample_user, sample_product)
    await db_session.commit()

    # Set custom threshold
    updated_tracking = await TrackingService.update_tracking_threshold(db_session, sample_user, sample_product.id, 10)
    await db_session.commit()

    assert updated_tracking is not None
    assert updated_tracking.custom_threshold_delta == 10


@pytest.mark.asyncio
async def test_update_threshold_nonexistent(db_session: AsyncSession, sample_user: User):
    """Test updating threshold for non-existent tracking."""
    tracking = await TrackingService.update_tracking_threshold(db_session, sample_user, 9999, 10)
    assert tracking is None


@pytest.mark.asyncio
async def test_add_tracking_with_custom_threshold(db_session: AsyncSession, sample_user: User, sample_product: Product):
    """Test adding tracking with custom threshold."""
    tracking, created = await TrackingService.add_tracking(db_session, sample_user, sample_product, custom_threshold=15)
    await db_session.commit()

    assert created is True
    assert tracking.custom_threshold_delta == 15
