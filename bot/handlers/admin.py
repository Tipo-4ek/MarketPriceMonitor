"""Admin handlers.

Every command here is gated on the ``is_admin`` flag the AdminACL middleware
puts in the handler context; a non-admin is answered with a refusal and the
attempt is logged. Replies use the admin's own locale, like the rest of the bot.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.core.alerts import alert_manager
from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.providers.health import health_monitor
from bot.handlers.context import user_locale
from bot.handlers.replies import sender_id

logger = get_logger(__name__)

router = Router()


async def _deny(message: Message, is_admin: bool) -> bool:
    """Answer and log an unauthorised attempt; return whether it was allowed."""
    if is_admin:
        return True
    locale = await user_locale(sender_id(message))
    await message.answer(get_text(locale, 'access_denied'))
    logger.warning('Unauthorized admin access attempt', extra={'tg_user_id': sender_id(message)})
    return False


@router.message(Command('provider_status'))
async def cmd_provider_status(message: Message, is_admin: bool = False):
    """Handle /provider_status command (admin only)."""
    if not await _deny(message, is_admin):
        return

    locale = await user_locale(sender_id(message))
    statuses = health_monitor.get_all_statuses()
    status_lines = [f'{provider.value}: {status.value}' for provider, status in statuses.items()]

    await message.answer(get_text(locale, 'provider_status', statuses='\n'.join(status_lines)))
    logger.info('Admin checked provider status', extra={'tg_user_id': sender_id(message)})


@router.message(Command('alerts_on'))
async def cmd_alerts_on(message: Message, is_admin: bool = False):
    """Handle /alerts_on command (admin only)."""
    if not await _deny(message, is_admin):
        return

    alert_manager.enable_alerts()
    locale = await user_locale(sender_id(message))
    await message.answer(get_text(locale, 'alerts_enabled'))
    logger.info('Admin enabled alerts', extra={'tg_user_id': sender_id(message)})


@router.message(Command('alerts_off'))
async def cmd_alerts_off(message: Message, is_admin: bool = False):
    """Handle /alerts_off command (admin only)."""
    if not await _deny(message, is_admin):
        return

    alert_manager.disable_alerts()
    locale = await user_locale(sender_id(message))
    await message.answer(get_text(locale, 'alerts_disabled'))
    logger.info('Admin disabled alerts', extra={'tg_user_id': sender_id(message)})


@router.message(Command('health_reset'))
async def cmd_health_reset(message: Message, is_admin: bool = False):
    """Handle /health_reset command (admin only)."""
    if not await _deny(message, is_admin):
        return

    health_monitor.reset()
    alert_manager.reset()
    locale = await user_locale(sender_id(message))
    await message.answer(get_text(locale, 'health_reset'))
    logger.info('Admin reset provider health', extra={'tg_user_id': sender_id(message)})
