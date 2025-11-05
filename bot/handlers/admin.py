"""Admin handlers."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.core.alerts import alert_manager
from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.providers.health import health_monitor

logger = get_logger(__name__)

router = Router()


async def check_admin(message: Message, is_admin: bool) -> bool:
    """Check if user is admin."""
    if not is_admin:
        await message.answer(get_text('ru', 'access_denied'))
        logger.warning(f'Unauthorized admin access attempt by user {message.from_user.id}')
        return False
    return True


@router.message(Command('provider_status'))
async def cmd_provider_status(message: Message, is_admin: bool = False):
    """Handle /provider_status command (admin only)."""
    if not await check_admin(message, is_admin):
        return

    statuses = health_monitor.get_all_statuses()
    status_lines = [f'{provider.value}: {status.value}' for provider, status in statuses.items()]

    text = get_text('ru', 'provider_status', statuses='\n'.join(status_lines))
    await message.answer(text)
    logger.info(f'Admin {message.from_user.id} checked provider status')


@router.message(Command('alerts_on'))
async def cmd_alerts_on(message: Message, is_admin: bool = False):
    """Handle /alerts_on command (admin only)."""
    if not await check_admin(message, is_admin):
        return

    alert_manager.enable_alerts()
    text = get_text('ru', 'alerts_enabled')
    await message.answer(text)
    logger.info(f'Admin {message.from_user.id} enabled alerts')


@router.message(Command('alerts_off'))
async def cmd_alerts_off(message: Message, is_admin: bool = False):
    """Handle /alerts_off command (admin only)."""
    if not await check_admin(message, is_admin):
        return

    alert_manager.disable_alerts()
    text = get_text('ru', 'alerts_disabled')
    await message.answer(text)
    logger.info(f'Admin {message.from_user.id} disabled alerts')


@router.message(Command('health_reset'))
async def cmd_health_reset(message: Message, is_admin: bool = False):
    """Handle /health_reset command (admin only)."""
    if not await check_admin(message, is_admin):
        return

    health_monitor.reset()
    alert_manager.reset()
    text = get_text('ru', 'health_reset')
    await message.answer(text)
    logger.info(f'Admin {message.from_user.id} reset health status')


