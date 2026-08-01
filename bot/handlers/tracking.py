"""Adding, listing and removing tracked products.

Every command works two ways. Typed with its argument (`/add <url>`) it acts
immediately; tapped from Telegram's command menu, which sends no arguments, it
asks for what it needs and waits for the next message. Anything that can be
offered as a button is offered as a button instead of asking for an id.

Two rules keep the FSM honest. A command always clears any half-finished step
first, so `/list` typed mid-`/add` runs `/list` rather than being read as a URL;
and the step handlers below ignore anything starting with `/`, so the command
reaches its own handler instead of being swallowed as input.
"""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.providers.base import (
    PriceNotFoundError,
    ProviderBlockedError,
    ProviderError,
    UnsupportedURLError,
)
from bot.core.services.product_service import ProductService
from bot.core.services.tracking_service import TrackingService
from bot.core.states import Flow
from bot.handlers.context import tracked_labels, user_locale
from bot.handlers.replies import edit_or_send, sender_id
from bot.keyboards import (
    CB_MENU_ADD,
    CB_MENU_LIST,
    CB_REMOVE,
    cancel_only,
    product_actions,
    product_picker,
)
from bot.models import base
from bot.utils.parsing import is_valid_url
from bot.utils.validators import validate_product_id

logger = get_logger(__name__)

router = Router()

# A message a step handler must not consume: it is a command, and the command's
# own handler should win. The bare-`/` check is enough — Telegram commands start
# with it and product links never do.
_NOT_A_COMMAND = ~F.text.startswith('/')

# Telegram rejects a message over 4096 characters. The list is built up to this
# budget and then capped with a note, so a user tracking many products still
# gets a list rather than nothing.
_LIST_CHAR_BUDGET = 3800

# Which provider failure maps to which message: "try again later" is true for a
# blocked marketplace and a lie for an unsupported link.
_ERROR_MESSAGES = {
    UnsupportedURLError: 'invalid_url',
    ProviderBlockedError: 'provider_blocked',
    PriceNotFoundError: 'price_not_found',
}


# --- adding ----------------------------------------------------------------


@router.message(Command('add'))
async def cmd_add(message: Message, command: CommandObject, state: FSMContext):
    """`/add <url>` acts at once; a bare `/add` asks for the link."""
    await state.clear()
    locale = await user_locale(sender_id(message))
    # CommandObject.args rather than message.text.split(): aiogram matches a
    # command in a media caption too, where message.text is None.
    if command.args:
        await add_product(message, command.args.strip())
        return

    await state.set_state(Flow.add_url)
    await message.answer(get_text(locale, 'prompt_add_url'), reply_markup=cancel_only(locale))


@router.callback_query(F.data == CB_MENU_ADD)
async def cb_add(callback: CallbackQuery, state: FSMContext):
    """The Add product button."""
    locale = await user_locale(sender_id(callback))
    await state.set_state(Flow.add_url)
    await edit_or_send(callback, get_text(locale, 'prompt_add_url'), reply_markup=cancel_only(locale))
    await callback.answer()


@router.message(Flow.add_url, F.text, _NOT_A_COMMAND)
async def add_url_received(message: Message, state: FSMContext):
    """The link the bot was waiting for."""
    url = (message.text or '').strip()
    if not is_valid_url(url):
        locale = await user_locale(sender_id(message))
        await message.answer(get_text(locale, 'not_a_link'), reply_markup=cancel_only(locale))
        return

    await state.clear()
    await add_product(message, url)


@router.message(StateFilter(None), F.text.regexp(r'https?://'))
async def handle_url(message: Message):
    """A link sent with no command at all."""
    url = (message.text or '').strip()
    if is_valid_url(url):
        await add_product(message, url)


async def add_product(message: Message, url: str):
    """Fetch the product and start tracking it for this user."""
    tg_user_id = sender_id(message)
    async with base.new_session() as session:
        user = await TrackingService.get_or_create_user(session, tg_user_id)

        try:
            # get_or_create_product already fetches title and price for a new
            # product; refetching here would mean two browser renders per /add.
            product, _ = await ProductService.get_or_create_product(session, url)
            _tracking, tracking_created = await TrackingService.add_tracking(session, user, product)
            await session.commit()

            if tracking_created:
                text = get_text(
                    user.locale,
                    'product_added',
                    title=escape(product.title),
                    price=product.last_price,
                    currency=escape(product.currency),
                    product_id=product.id,
                )
                logger.info('Product added', extra={'tg_user_id': tg_user_id, 'product_id': product.id})
            else:
                text = get_text(user.locale, 'product_exists', product_id=product.id)

        except ProviderError as exc:
            await message.answer(get_text(user.locale, _ERROR_MESSAGES.get(type(exc), 'provider_error')))
            logger.info(
                'Could not add product',
                extra={'tg_user_id': tg_user_id, 'url': url, 'reason': type(exc).__name__, 'error': str(exc)},
            )
            return

        except Exception:
            await message.answer(get_text(user.locale, 'provider_error'))
            logger.exception('Error adding product', extra={'tg_user_id': tg_user_id, 'url': url})
            return

    await message.answer(text, parse_mode='HTML')

    # Follow the confirmation with the list, so the buttons for the new product
    # are immediately at hand.
    body, keyboard = await render_list(tg_user_id)
    await message.answer(body, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)


# --- listing ---------------------------------------------------------------


async def render_list(tg_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build the tracked-product list and its keyboard for one user.

    The body is capped at the Telegram message limit: entries are added while
    they fit and any remainder is summarised, so a large collection produces a
    valid message rather than one Telegram rejects outright.
    """
    async with base.new_session() as session:
        user = await TrackingService.get_or_create_user(session, tg_user_id)
        trackings = await TrackingService.get_user_trackings(session, user)
        await session.commit()

        if not trackings:
            return get_text(user.locale, 'no_tracked_products'), product_actions(user.locale, [])

        entries: list[str] = []
        product_ids: list[int] = []
        running = 0
        hidden = 0
        for tracking, product in trackings:
            product_ids.append(product.id)
            threshold = (
                f'{tracking.custom_threshold_delta}%'
                if tracking.custom_threshold_delta
                else get_text(user.locale, 'threshold_default')
            )
            entry = get_text(
                user.locale,
                'tracked_product_entry',
                product_id=product.id,
                # Titles come from the marketplace page, so they are escaped
                # before going anywhere near parse_mode='HTML'.
                title=escape(product.title),
                price=product.last_price,
                currency=escape(product.currency),
                provider=product.provider.value,
                threshold=threshold,
                url=escape(product.url, quote=True),
            )
            if running + len(entry) > _LIST_CHAR_BUDGET:
                hidden += 1
                continue
            entries.append(entry)
            running += len(entry) + 2  # the '\n\n' join between entries

        body = get_text(user.locale, 'tracked_products', products='\n\n'.join(entries))
        if hidden:
            body = f'{body}\n\n{get_text(user.locale, "list_truncated", count=hidden)}'
        return body, product_actions(user.locale, product_ids)


@router.message(Command('list'))
async def cmd_list(message: Message, state: FSMContext):
    """Handle /list command."""
    await state.clear()
    text, keyboard = await render_list(sender_id(message))
    await message.answer(text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)


@router.callback_query(F.data == CB_MENU_LIST)
async def cb_list(callback: CallbackQuery, state: FSMContext):
    """The My products button, and Back from the threshold keyboard."""
    await state.clear()
    text, keyboard = await render_list(sender_id(callback))
    await edit_or_send(callback, text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)
    await callback.answer()


# --- removing --------------------------------------------------------------


@router.message(Command('remove'))
async def cmd_remove(message: Message, command: CommandObject, state: FSMContext):
    """`/remove <id>` acts at once; a bare `/remove` offers the products."""
    await state.clear()
    if command.args:
        await _remove_and_report(message, command.args.strip())
        return

    locale = await user_locale(sender_id(message))
    labels = await tracked_labels(sender_id(message))
    if not labels:
        await message.answer(get_text(locale, 'no_tracked_products'))
        return

    await state.set_state(Flow.remove_id)
    await message.answer(
        get_text(locale, 'prompt_pick_remove'),
        reply_markup=product_picker(locale, labels, CB_REMOVE),
    )


@router.message(Flow.remove_id, F.text, _NOT_A_COMMAND)
async def remove_id_received(message: Message, state: FSMContext):
    """An id typed instead of tapping one of the offered products."""
    await state.clear()
    await _remove_and_report(message, (message.text or '').strip())


async def _remove_and_report(message: Message, raw_product_id: str) -> None:
    product_id = validate_product_id(raw_product_id)
    tg_user_id = sender_id(message)

    async with base.new_session() as session:
        user = await TrackingService.get_or_create_user(session, tg_user_id)

        if not product_id:
            await session.commit()
            await message.answer(get_text(user.locale, 'invalid_product_id'))
            return

        removed = await TrackingService.remove_tracking(session, user, product_id)
        await session.commit()

        if removed:
            text = get_text(user.locale, 'product_removed')
            logger.info('Product removed', extra={'tg_user_id': tg_user_id, 'product_id': product_id})
        else:
            text = get_text(user.locale, 'product_not_found')

    await message.answer(text)
    body, keyboard = await render_list(tg_user_id)
    await message.answer(body, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)


@router.callback_query(StateFilter('*'), F.data.startswith(f'{CB_REMOVE}:'))
async def cb_remove(callback: CallbackQuery, state: FSMContext):
    """Remove a product from the list keyboard or the picker."""
    await state.clear()
    product_id = validate_product_id((callback.data or '').split(':')[1])
    if not product_id:
        await callback.answer()
        return

    tg_user_id = sender_id(callback)
    async with base.new_session() as session:
        user = await TrackingService.get_or_create_user(session, tg_user_id)
        removed = await TrackingService.remove_tracking(session, user, product_id)
        await session.commit()
        locale = user.locale

    await callback.answer(get_text(locale, 'product_removed' if removed else 'product_not_found'))
    logger.info(
        'Product removed via button',
        extra={'tg_user_id': tg_user_id, 'product_id': product_id, 'removed': removed},
    )

    # Re-render so the row for the removed product disappears.
    text, keyboard = await render_list(tg_user_id)
    await edit_or_send(callback, text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)
