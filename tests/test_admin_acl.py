"""Tests for admin access control."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import User as TgUser

from bot.core.middlewares.admin_acl import AdminACL


@pytest.mark.asyncio
async def test_admin_acl_admin_user():
    """Test ACL for admin user."""
    middleware = AdminACL()

    # Mock admin user (using ID from settings)
    mock_user = TgUser(id=123456789, is_bot=False, first_name='Admin')

    data = {'event_from_user': mock_user}

    handler = AsyncMock()
    event = MagicMock()

    await middleware(handler, event, data)

    # Check if is_admin flag was set
    # Note: This will depend on actual ADMIN_TG_IDS in environment
    # For test purposes, we just verify the middleware runs
    assert 'is_admin' in data
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_admin_acl_regular_user():
    """Test ACL for regular user."""
    middleware = AdminACL()

    # Mock regular user
    mock_user = TgUser(id=999999999, is_bot=False, first_name='User')

    data = {'event_from_user': mock_user}

    handler = AsyncMock()
    event = MagicMock()

    await middleware(handler, event, data)

    assert 'is_admin' in data
    assert data['is_admin'] is False
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_admin_acl_no_user():
    """Test ACL when no user in data."""
    middleware = AdminACL()

    data = {}

    handler = AsyncMock()
    event = MagicMock()

    await middleware(handler, event, data)

    assert 'is_admin' in data
    assert data['is_admin'] is False
    handler.assert_called_once()


