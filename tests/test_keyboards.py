"""Tests for the inline keyboards and their callback payloads."""

from aiogram.types import InlineKeyboardMarkup

from bot.keyboards import (
    CB_CANCEL,
    CB_LOCALE,
    CB_MENU_ADD,
    CB_MENU_HELP,
    CB_MENU_LIST,
    CB_REMOVE,
    CB_THRESHOLD_MENU,
    CB_THRESHOLD_SET,
    MAX_PRODUCT_ROWS,
    THRESHOLD_CHOICES,
    cancel_only,
    locale_choices,
    main_menu,
    product_actions,
    product_picker,
    threshold_choices,
)

# Telegram rejects callback_data longer than this, and the failure is a runtime
# BadRequest rather than anything visible in review.
TELEGRAM_CALLBACK_LIMIT = 64


def payloads(keyboard: InlineKeyboardMarkup) -> list[str]:
    return [button.callback_data for row in keyboard.inline_keyboard for button in row]


def test_main_menu_offers_add_list_and_help():
    assert set(payloads(main_menu('ru'))) == {CB_MENU_ADD, CB_MENU_LIST, CB_MENU_HELP}


def test_cancel_keyboard_has_exactly_one_button():
    assert payloads(cancel_only('ru')) == [CB_CANCEL]


def test_product_actions_offers_remove_and_threshold_per_product():
    keyboard = product_actions('ru', [7, 9])
    assert f'{CB_REMOVE}:7' in payloads(keyboard)
    assert f'{CB_THRESHOLD_MENU}:9' in payloads(keyboard)
    # Adding another product is always one tap away.
    assert CB_MENU_ADD in payloads(keyboard)


def test_product_actions_with_no_products_only_offers_add():
    assert payloads(product_actions('ru', [])) == [CB_MENU_ADD]


def test_product_actions_caps_the_number_of_rows():
    keyboard = product_actions('ru', list(range(1, MAX_PRODUCT_ROWS + 20)))
    # One row per shown product, plus the trailing Add row.
    assert len(keyboard.inline_keyboard) == MAX_PRODUCT_ROWS + 1


def test_product_picker_uses_the_prefix_it_is_given():
    keyboard = product_picker('ru', {3: '#3 Coffee', 4: '#4 Tea'}, CB_REMOVE)
    assert f'{CB_REMOVE}:3' in payloads(keyboard)
    assert f'{CB_REMOVE}:4' in payloads(keyboard)
    # A picker must always be escapable.
    assert CB_CANCEL in payloads(keyboard)


def test_threshold_keyboard_offers_every_choice_and_a_way_back():
    keyboard = threshold_choices('ru', 12)
    for percent in THRESHOLD_CHOICES:
        assert f'{CB_THRESHOLD_SET}:12:{percent}' in payloads(keyboard)
    assert CB_MENU_LIST in payloads(keyboard)


def test_locale_keyboard_offers_both_languages():
    assert f'{CB_LOCALE}:ru' in payloads(locale_choices('ru'))
    assert f'{CB_LOCALE}:en' in payloads(locale_choices('en'))


def test_every_payload_fits_telegram_limit():
    # A five-digit product id is far more than this bot will ever reach, and is
    # the worst case for the longest prefix.
    keyboards = [
        main_menu('ru'),
        cancel_only('ru'),
        product_actions('ru', [99999]),
        product_picker('ru', {99999: 'x' * 40}, CB_THRESHOLD_MENU),
        threshold_choices('ru', 99999),
        locale_choices('ru'),
    ]
    for keyboard in keyboards:
        for payload in payloads(keyboard):
            assert len(payload.encode()) <= TELEGRAM_CALLBACK_LIMIT, payload


def test_button_labels_are_translated_not_raw_keys():
    for locale in ('ru', 'en'):
        labels = [button.text for row in main_menu(locale).inline_keyboard for button in row]
        # get_text falls back to returning the key when a string is missing.
        assert 'btn_add' not in labels
        assert 'btn_help' not in labels
        assert all(labels)
