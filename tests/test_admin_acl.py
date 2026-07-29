"""Tests for admin access control."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import User as TgUser

from bot.core.middlewares.admin_acl import AdminACL


@pytest.mark.asyncio
async def test_admin_acl_admin_user(isolated_settings):
    """A user listed in ADMIN_TG_IDS is flagged as an admin."""
    middleware = AdminACL()

    admin_id = isolated_settings.admin_ids[0]
    mock_user = TgUser(id=admin_id, is_bot=False, first_name='Admin')

    data = {'event_from_user': mock_user}

    handler = AsyncMock()
    event = MagicMock()

    await middleware(handler, event, data)

    assert data['is_admin'] is True
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
