"""Common handlers (start, help, lang)."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.services.tracking_service import TrackingService
from bot.models import base
from bot.utils.validators import validate_locale

logger = get_logger(__name__)

router = Router()


@router.message(Command('start'))
async def cmd_start(message: Message):
    """Handle /start command."""
    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)
        await session.commit()

        text = get_text(user.locale, 'welcome')
        await message.answer(text)


@router.message(Command('help'))
async def cmd_help(message: Message):
    """Handle /help command."""
    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)

        text = get_text(user.locale, 'help')
        await message.answer(text)


@router.message(Command('lang'))
async def cmd_lang(message: Message):
    """Handle /lang command."""
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer('Usage: /lang <ru|en>')
        return

    locale = args[1].strip().lower()

    if not validate_locale(locale):
        async with base.async_session_maker() as session:
            user = await TrackingService.get_or_create_user(session, message.from_user.id)
            text = get_text(user.locale, 'invalid_language')
            await message.answer(text)
        return

    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)
        await TrackingService.update_user_locale(session, user, locale)
        await session.commit()

        text = get_text(locale, 'language_changed')
        await message.answer(text)
        logger.info(f'User {message.from_user.id} changed locale to {locale}')
