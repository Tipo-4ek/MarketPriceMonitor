"""Per-product price-change threshold.

`/monitor set <id> <delta>` still works in one line, but tapping `/monitor` from
the command menu walks through it: pick a product, then pick a percentage. There
is deliberately no per-user default threshold — that lives in
DEFAULT_THRESHOLD_DELTA — because a command that accepts a value and quietly
ignores it is worse than no command.
"""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.services.tracking_service import TrackingService
from bot.core.states import Flow
from bot.handlers.context import tracked_labels, user_locale
from bot.handlers.tracking import render_list
from bot.keyboards import (
    CB_THRESHOLD_MENU,
    CB_THRESHOLD_SET,
    product_picker,
    threshold_choices,
)
from bot.models import base
from bot.utils.validators import validate_product_id, validate_threshold

logger = get_logger(__name__)

router = Router()


@router.message(Command('monitor'))
async def cmd_monitor(message: Message, command: CommandObject, state: FSMContext):
    """One-line form, or the first step of the interactive one."""
    args = (command.args or '').split()

    if args:
        if len(args) != 3 or args[0].lower() != 'set':
            await message.answer('/monitor set <id> <delta>')
            return
        await _apply_threshold(message, args[1], args[2])
        return

    locale = await user_locale(message.from_user.id)
    labels = await tracked_labels(message.from_user.id)
    if not labels:
        await message.answer(get_text(locale, 'no_tracked_products'))
        return

    await state.set_state(Flow.threshold_product)
    await message.answer(
        get_text(locale, 'prompt_pick_threshold'),
        reply_markup=product_picker(locale, labels, CB_THRESHOLD_MENU),
    )


@router.message(Flow.threshold_product)
async def threshold_product_received(message: Message, state: FSMContext):
    """A product id typed instead of tapping one of the offered products."""
    product_id = validate_product_id((message.text or '').strip())
    locale = await user_locale(message.from_user.id)

    if not product_id:
        await message.answer(get_text(locale, 'invalid_product_id'))
        return

    await state.set_state(Flow.threshold_value)
    await state.update_data(product_id=product_id)
    await message.answer(
        get_text(locale, 'prompt_threshold_value', product_id=product_id),
        reply_markup=threshold_choices(locale, product_id),
    )


@router.callback_query(StateFilter('*'), F.data.startswith(f'{CB_THRESHOLD_MENU}:'))
async def cb_threshold_menu(callback: CallbackQuery, state: FSMContext):
    """A product was picked: offer the percentages."""
    product_id = validate_product_id(callback.data.split(':')[1])
    if not product_id:
        await callback.answer()
        return

    locale = await user_locale(callback.from_user.id)
    await state.set_state(Flow.threshold_value)
    await state.update_data(product_id=product_id)

    await callback.message.edit_text(
        get_text(locale, 'prompt_threshold_value', product_id=product_id),
        reply_markup=threshold_choices(locale, product_id),
    )
    await callback.answer()


@router.message(Flow.threshold_value)
async def threshold_value_received(message: Message, state: FSMContext):
    """A percentage typed instead of tapping one of the offered ones."""
    data = await state.get_data()
    product_id = data.get('product_id')
    if not product_id:
        await state.clear()
        return

    await state.clear()
    await _apply_threshold(message, str(product_id), (message.text or '').strip())


@router.callback_query(StateFilter('*'), F.data.startswith(f'{CB_THRESHOLD_SET}:'))
async def cb_threshold_set(callback: CallbackQuery, state: FSMContext):
    """A percentage was picked from the keyboard."""
    await state.clear()
    _, raw_product_id, raw_delta = callback.data.split(':')
    product_id = validate_product_id(raw_product_id)
    delta = validate_threshold(raw_delta)
    if not product_id or not delta:
        await callback.answer()
        return

    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, callback.from_user.id)
        tracking = await TrackingService.update_tracking_threshold(session, user, product_id, delta)
        await session.commit()
        locale = user.locale

    if tracking:
        await callback.answer(get_text(locale, 'custom_threshold_set', product_id=product_id, delta=delta))
        logger.info(
            'Threshold set via button',
            extra={'tg_user_id': callback.from_user.id, 'product_id': product_id, 'threshold': delta},
        )
    else:
        await callback.answer(get_text(locale, 'product_not_found'))

    text, keyboard = await render_list(callback.from_user.id)
    await callback.message.edit_text(text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)


async def _apply_threshold(message: Message, raw_product_id: str, raw_delta: str) -> None:
    product_id = validate_product_id(raw_product_id)
    threshold = validate_threshold(raw_delta)

    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)

        if not product_id or not threshold:
            # Name the argument that was actually wrong: complaining about the
            # threshold when the id was mistyped sends the user to the wrong place.
            key = 'invalid_product_id' if not product_id else 'invalid_threshold'
            await session.commit()
            await message.answer(get_text(user.locale, key))
            return

        tracking = await TrackingService.update_tracking_threshold(session, user, product_id, threshold)
        await session.commit()

        if tracking:
            text = get_text(user.locale, 'custom_threshold_set', product_id=product_id, delta=threshold)
            logger.info(
                'Threshold set',
                extra={'tg_user_id': message.from_user.id, 'product_id': product_id, 'threshold': threshold},
            )
        else:
            text = get_text(user.locale, 'product_not_found')

    await message.answer(text)
