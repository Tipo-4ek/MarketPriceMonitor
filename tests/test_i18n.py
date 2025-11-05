"""Tests for internationalization."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.i18n import get_text
from bot.core.services.tracking_service import TrackingService
from bot.models import User


def test_get_text_russian():
    """Test getting Russian text."""
    text = get_text('ru', 'welcome')
    assert '👋' in text
    assert 'Добро пожаловать' in text


def test_get_text_english():
    """Test getting English text."""
    text = get_text('en', 'welcome')
    assert '👋' in text
    assert 'Welcome' in text


def test_get_text_with_parameters():
    """Test getting text with parameters."""
    text = get_text('ru', 'product_added', title='Test', price='100', currency='RUB', product_id=1)
    assert 'Test' in text
    assert '100' in text
    assert 'RUB' in text


def test_get_text_fallback():
    """Test fallback to Russian for unsupported locale."""
    text = get_text('fr', 'welcome')
    assert 'Добро пожаловать' in text


@pytest.mark.asyncio
async def test_update_user_locale(db_session: AsyncSession, sample_user: User):
    """Test updating user locale."""
    assert sample_user.locale == 'ru'

    await TrackingService.update_user_locale(db_session, sample_user, 'en')
    await db_session.commit()
    await db_session.refresh(sample_user)

    assert sample_user.locale == 'en'


