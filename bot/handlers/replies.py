"""Shared reply helpers for the handlers.

Two aiogram facts drive this module. A ``Message`` or ``CallbackQuery`` types
``from_user`` as optional (channel posts and a few service updates carry none),
and a callback's ``message`` may be a real ``Message``, an ``InaccessibleMessage``
(too old to edit), or ``None``. Every handler would otherwise repeat the same
guards, and the type checker rightly objects to dereferencing them blind. These
helpers hold the guards in one place so the handlers stay about behaviour.
"""

from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


def sender_id(event: Message | CallbackQuery) -> int:
    """The Telegram user id behind a message or callback.

    Every update this bot handles is user-originated, so ``from_user`` is set;
    the assert states that invariant for the type checker and turns the one case
    that would violate it into a clear error rather than an ``AttributeError``.
    """
    assert event.from_user is not None, 'handler reached without an originating user'
    return event.from_user.id


async def edit_or_send(
    callback: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
    disable_web_page_preview: bool | None = None,
) -> None:
    """Re-render the message a callback came from, coping with what Telegram allows.

    The message may be inaccessible (too old) or absent, in which case a fresh
    message is sent instead of editing. Re-rendering identical text raises
    ``message is not modified`` — a non-event here, so it is swallowed.
    """
    message = callback.message
    if isinstance(message, Message):
        with suppress(TelegramBadRequest):
            await message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
        return

    if callback.bot is None:  # pragma: no cover - a callback always carries its bot
        return
    with suppress(TelegramBadRequest):
        await callback.bot.send_message(
            sender_id(callback),
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
