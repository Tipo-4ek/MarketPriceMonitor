"""Start, help, language and the global cancel."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.core.commands import command_reference
from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.services.tracking_service import TrackingService
from bot.core.states import Flow
from bot.handlers.context import user_locale
from bot.keyboards import CB_CANCEL, CB_LOCALE, CB_MENU_HELP, locale_choices, main_menu
from bot.models import base
from bot.utils.validators import validate_locale

logger = get_logger(__name__)

router = Router()


def help_text(locale: str, *, include_admin: bool) -> str:
    """Assemble /help from the same command list Telegram's menu is built from."""
    return '\n'.join(
        (
            get_text(locale, 'help_header'),
            '',
            command_reference(locale, include_admin=include_admin),
            '',
            get_text(locale, 'help_footer'),
        )
    )


@router.message(Command('cancel'), StateFilter('*'))
async def cmd_cancel(message: Message, state: FSMContext):
    """Leave whatever the bot was waiting for."""
    await state.clear()
    locale = await user_locale(message.from_user.id)
    await message.answer(get_text(locale, 'cancelled'), reply_markup=main_menu(locale))


@router.callback_query(StateFilter('*'), F.data == CB_CANCEL)
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    """The Cancel button shown while the bot is waiting for input."""
    await state.clear()
    locale = await user_locale(callback.from_user.id)
    await callback.message.edit_text(get_text(locale, 'cancelled'), reply_markup=main_menu(locale))
    await callback.answer()


@router.message(Command('start'), StateFilter('*'))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    await state.clear()
    locale = await user_locale(message.from_user.id)
    await message.answer(
        get_text(locale, 'welcome'),
        parse_mode='HTML',
        reply_markup=main_menu(locale),
        disable_web_page_preview=True,
    )


@router.message(Command('help'), StateFilter('*'))
async def cmd_help(message: Message, state: FSMContext, is_admin: bool = False):
    """Handle /help command."""
    await state.clear()
    locale = await user_locale(message.from_user.id)
    await message.answer(help_text(locale, include_admin=is_admin), reply_markup=main_menu(locale))


@router.callback_query(F.data == CB_MENU_HELP)
async def cb_help(callback: CallbackQuery, state: FSMContext):
    """The Help button."""
    await state.clear()
    locale = await user_locale(callback.from_user.id)
    await callback.message.edit_text(help_text(locale, include_admin=False), reply_markup=main_menu(locale))
    await callback.answer()


@router.message(Command('lang'))
async def cmd_lang(message: Message, command: CommandObject, state: FSMContext):
    """`/lang ru` acts at once; a bare `/lang` offers the two languages."""
    if command.args:
        await _apply_locale(message, command.args.strip().lower())
        return

    locale = await user_locale(message.from_user.id)
    await state.set_state(Flow.locale_choice)
    await message.answer(get_text(locale, 'prompt_lang'), reply_markup=locale_choices(locale))


@router.message(Flow.locale_choice)
async def locale_typed(message: Message, state: FSMContext):
    """A language code typed instead of tapping a button."""
    await state.clear()
    await _apply_locale(message, (message.text or '').strip().lower())


@router.callback_query(StateFilter('*'), F.data.startswith(f'{CB_LOCALE}:'))
async def cb_locale(callback: CallbackQuery, state: FSMContext):
    """A language picked from the keyboard."""
    await state.clear()
    locale = callback.data.split(':')[1]
    if not validate_locale(locale):
        await callback.answer()
        return

    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, callback.from_user.id)
        await TrackingService.update_user_locale(session, user, locale)
        await session.commit()

    await callback.message.edit_text(get_text(locale, 'language_changed'), reply_markup=main_menu(locale))
    await callback.answer()
    logger.info('Locale changed', extra={'tg_user_id': callback.from_user.id, 'locale': locale})


async def _apply_locale(message: Message, locale: str) -> None:
    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)

        if not validate_locale(locale):
            await session.commit()
            await message.answer(get_text(user.locale, 'invalid_language'), reply_markup=locale_choices(user.locale))
            return

        await TrackingService.update_user_locale(session, user, locale)
        await session.commit()

    await message.answer(get_text(locale, 'language_changed'), reply_markup=main_menu(locale))
    logger.info('Locale changed', extra={'tg_user_id': message.from_user.id, 'locale': locale})
