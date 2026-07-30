"""Inline keyboards and the callback data they carry.

Callback payloads are tiny strings because Telegram caps them at 64 bytes:
``menu:list``, ``rm:12``, ``th:12``, ``set:12:5``, ``lang:ru``, ``cancel``. They
are parsed back in bot/handlers/, and the prefixes live here so the producer and
the consumer cannot drift apart.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.core.i18n import get_text

CB_MENU_LIST = 'menu:list'
CB_MENU_HELP = 'menu:help'
CB_MENU_ADD = 'menu:add'
CB_REMOVE = 'rm'
CB_THRESHOLD_MENU = 'th'
CB_THRESHOLD_SET = 'set'
CB_LOCALE = 'lang'
CB_CANCEL = 'cancel'

# Offered on the threshold keyboard. Wide enough to be useful, small enough to
# fit one row on a phone.
THRESHOLD_CHOICES = (3, 5, 10, 20)

# Telegram renders a very long keyboard badly, and nobody manages fifty products
# from buttons. Past this the user is told to type the id instead.
MAX_PRODUCT_ROWS = 8


def main_menu(locale: str) -> InlineKeyboardMarkup:
    """Buttons under the welcome message."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=get_text(locale, 'btn_add'), callback_data=CB_MENU_ADD),
                InlineKeyboardButton(text=get_text(locale, 'btn_my_products'), callback_data=CB_MENU_LIST),
            ],
            [InlineKeyboardButton(text=get_text(locale, 'btn_help'), callback_data=CB_MENU_HELP)],
        ]
    )


def cancel_only(locale: str) -> InlineKeyboardMarkup:
    """Shown while the bot is waiting for something to be typed."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=get_text(locale, 'btn_cancel'), callback_data=CB_CANCEL)]]
    )


def product_actions(locale: str, product_ids: list[int]) -> InlineKeyboardMarkup:
    """One row per tracked product: remove it, or change its threshold.

    Always returns a keyboard: with nothing tracked yet, the Add button is the
    most useful thing on the screen.
    """
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=get_text(locale, 'btn_remove_id', product_id=product_id),
                callback_data=f'{CB_REMOVE}:{product_id}',
            ),
            InlineKeyboardButton(
                text=get_text(locale, 'btn_threshold_id', product_id=product_id),
                callback_data=f'{CB_THRESHOLD_MENU}:{product_id}',
            ),
        ]
        for product_id in product_ids[:MAX_PRODUCT_ROWS]
    ]
    rows.append([InlineKeyboardButton(text=get_text(locale, 'btn_add'), callback_data=CB_MENU_ADD)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_picker(locale: str, labels: dict[int, str], prefix: str) -> InlineKeyboardMarkup:
    """Pick one product to act on. ``prefix`` decides what happens next."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=label, callback_data=f'{prefix}:{product_id}')]
        for product_id, label in list(labels.items())[:MAX_PRODUCT_ROWS]
    ]
    rows.append([InlineKeyboardButton(text=get_text(locale, 'btn_cancel'), callback_data=CB_CANCEL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def threshold_choices(locale: str, product_id: int) -> InlineKeyboardMarkup:
    """Pick a percentage for one product, or go back to the list."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f'{percent}%',
                    callback_data=f'{CB_THRESHOLD_SET}:{product_id}:{percent}',
                )
                for percent in THRESHOLD_CHOICES
            ],
            [InlineKeyboardButton(text=get_text(locale, 'btn_back'), callback_data=CB_MENU_LIST)],
        ]
    )


def locale_choices(locale: str) -> InlineKeyboardMarkup:
    """Language picker, so /lang needs no typing."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='Русский', callback_data=f'{CB_LOCALE}:ru'),
                InlineKeyboardButton(text='English', callback_data=f'{CB_LOCALE}:en'),
            ],
            [InlineKeyboardButton(text=get_text(locale, 'btn_cancel'), callback_data=CB_CANCEL)],
        ]
    )
