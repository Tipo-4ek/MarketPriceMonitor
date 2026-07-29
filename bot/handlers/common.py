"""Common handlers (start, help, lang)."""

from aiogram import Router
from aiogram.filters import Command, CommandObject
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

        await message.answer(get_text(user.locale, 'welcome'))


@router.message(Command('help'))
async def cmd_help(message: Message):
    """Handle /help command."""
    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)
        # get_or_create_user only flushes; without this commit a first-time user
        # who starts with /help is rolled back and re-created on every command.
        await session.commit()

        await message.answer(get_text(user.locale, 'help'))


@router.message(Command('lang'))
async def cmd_lang(message: Message, command: CommandObject):
    """Handle /lang command."""
    # CommandObject.args rather than message.text.split(): aiogram matches a
    # command in a media caption too, where message.text is None.
    if not command.args:
        await message.answer('Usage: /lang <ru|en>')
        return

    locale = command.args.strip().lower()

    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)

        if not validate_locale(locale):
            await session.commit()
            await message.answer(get_text(user.locale, 'invalid_language'))
            return

        await TrackingService.update_user_locale(session, user, locale)
        await session.commit()

        await message.answer(get_text(locale, 'language_changed'))
        logger.info('Locale changed', extra={'tg_user_id': message.from_user.id, 'locale': locale})
