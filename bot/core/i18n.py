"""Internationalization support.

The wording is deliberately flat: a price tracker reports facts, so the messages
state what happened and what to do next, without greetings, exclamation marks or
decoration. The one arrow in `price_changed` is there because it carries meaning.
"""

from typing import Any

# Translations dictionary
TRANSLATIONS: dict[str, dict[str, str]] = {
    'ru': {
        'welcome': (
            'Слежу за ценами на Wildberries.\n\n'
            'Пришлите ссылку на товар — буду проверять цену по расписанию и напишу, '
            'когда она изменится сильнее порога.\n\n'
            'Wildberries — <code>wildberries.ru/catalog/…/detail.aspx</code>\n\n'
            'Команда /add не обязательна: ссылку можно отправить просто так.'
        ),
        'help_header': 'Команды',
        'help_footer': (
            'Аргументы в квадратных скобках можно не писать: выберите команду в меню, '
            'и я спрошу, что нужно.\n'
            'Ссылку Wildberries можно прислать и вообще без команды.'
        ),
        'btn_add': 'Добавить товар',
        'btn_cancel': 'Отмена',
        'prompt_add_url': 'Пришлите ссылку на товар Wildberries.',
        'prompt_pick_remove': 'Какой товар убрать?',
        'prompt_pick_threshold': 'Для какого товара менять порог?',
        'prompt_threshold_value': 'Товар #{product_id}: выберите порог кнопкой или пришлите число от 1 до 100.',
        'prompt_lang': 'Выберите язык.',
        'cancelled': 'Отменил.',
        'not_a_link': 'Это не похоже на ссылку. Пришлите ссылку на товар или нажмите «Отмена».',
        'btn_my_products': 'Мои товары',
        'btn_help': 'Справка',
        'btn_remove_id': 'Убрать #{product_id}',
        'btn_threshold_id': 'Порог #{product_id}',
        'btn_back': '← К списку',
        'choose_threshold': 'Товар #{product_id}: при каком изменении цены писать?',
        'language_changed': 'Язык переключён на русский.',
        'invalid_language': 'Доступны ru и en.',
        'product_added': 'Добавил: <b>{title}</b>\n{price} {currency}\nID {product_id}',
        'product_exists': 'Этот товар уже отслеживается, ID {product_id}.',
        'invalid_url': 'Не разбираю эту ссылку. Пока работает Wildberries.',
        'provider_error': 'Не удалось получить данные о товаре. Попробуйте позже.',
        'provider_blocked': 'Маркетплейс сейчас не отдаёт страницу — сработала защита от ботов. Попробуйте позже.',
        'price_not_found': 'Страница открылась, но цены на ней нет. Возможно, товара нет в наличии.',
        'tracked_products': 'Отслеживаемые товары:\n\n{products}',
        'tracked_product_entry': (
            '<b>#{product_id}</b> {title}\n{price} {currency} · {provider} · порог {threshold}\n'
            '<a href="{url}">открыть на сайте</a>'
        ),
        'threshold_default': 'по умолчанию',
        'no_tracked_products': 'Пока ничего не отслеживается. Пришлите ссылку на товар.',
        'product_removed': 'Убрал из отслеживания.',
        'product_not_found': 'Товар с таким ID не найден.',
        'invalid_product_id': 'ID — это число. Свои можно посмотреть командой /list.',
        'custom_threshold_set': 'Порог для товара {product_id}: {delta}%.',
        'invalid_threshold': 'Порог — целое число от 1 до 100.',
        'price_changed': (
            'Цена изменилась: <b>{title}</b>\n'
            '{old_price} → {new_price} {currency} ({change}%)\n'
            '<a href="{url}">открыть на сайте</a>'
        ),
        'access_denied': 'Команда только для администраторов.',
        'provider_status': 'Состояние провайдеров:\n\n{statuses}',
        'alerts_enabled': 'Оповещения о сбоях включены.',
        'alerts_disabled': 'Оповещения о сбоях выключены.',
        'health_reset': 'Состояние провайдеров сброшено.',
        'provider_degraded': '{provider}: сбои при получении цен.',
        'provider_down': '{provider}: не отвечает.',
        'provider_restored': '{provider}: снова отвечает.',
    },
    'en': {
        'welcome': (
            'I track prices on Wildberries.\n\n'
            'Send a product link and I will check its price on a schedule, then message you '
            'when it moves past your threshold.\n\n'
            'Wildberries — <code>wildberries.ru/catalog/…/detail.aspx</code>\n\n'
            'The /add command is optional: a bare link works.'
        ),
        'help_header': 'Commands',
        'help_footer': (
            'Arguments in square brackets are optional: pick a command from the menu and '
            'I will ask for what I need.\n'
            'A Wildberries link also works with no command at all.'
        ),
        'btn_add': 'Add product',
        'btn_cancel': 'Cancel',
        'prompt_add_url': 'Send a Wildberries product link.',
        'prompt_pick_remove': 'Which product should I remove?',
        'prompt_pick_threshold': 'Which product should change threshold?',
        'prompt_threshold_value': 'Product #{product_id}: pick a threshold, or send a number from 1 to 100.',
        'prompt_lang': 'Choose a language.',
        'cancelled': 'Cancelled.',
        'not_a_link': 'That does not look like a link. Send a product link, or press Cancel.',
        'btn_my_products': 'My products',
        'btn_help': 'Help',
        'btn_remove_id': 'Remove #{product_id}',
        'btn_threshold_id': 'Threshold #{product_id}',
        'btn_back': '← Back to list',
        'choose_threshold': 'Product #{product_id}: how big a price move should I report?',
        'language_changed': 'Language switched to English.',
        'invalid_language': 'Available: ru, en.',
        'product_added': 'Added: <b>{title}</b>\n{price} {currency}\nID {product_id}',
        'product_exists': 'Already tracked, ID {product_id}.',
        'invalid_url': 'I cannot parse that link. Wildberries works for now.',
        'provider_error': 'Could not fetch the product. Try again later.',
        'provider_blocked': 'The marketplace is not serving the page right now — anti-bot. Try again later.',
        'price_not_found': 'The page opened but carries no price. The item may be out of stock.',
        'tracked_products': 'Tracked products:\n\n{products}',
        'tracked_product_entry': (
            '<b>#{product_id}</b> {title}\n{price} {currency} · {provider} · threshold {threshold}\n'
            '<a href="{url}">open on the site</a>'
        ),
        'threshold_default': 'default',
        'no_tracked_products': 'Nothing tracked yet. Send a product link.',
        'product_removed': 'Removed from tracking.',
        'product_not_found': 'No product with that ID.',
        'invalid_product_id': 'The ID is a number. Use /list to see yours.',
        'custom_threshold_set': 'Threshold for product {product_id}: {delta}%.',
        'invalid_threshold': 'The threshold is a whole number from 1 to 100.',
        'price_changed': (
            'Price changed: <b>{title}</b>\n'
            '{old_price} → {new_price} {currency} ({change}%)\n'
            '<a href="{url}">open on the site</a>'
        ),
        'access_denied': 'Administrators only.',
        'provider_status': 'Provider health:\n\n{statuses}',
        'alerts_enabled': 'Failure alerts enabled.',
        'alerts_disabled': 'Failure alerts disabled.',
        'health_reset': 'Provider health reset.',
        'provider_degraded': '{provider}: errors while fetching prices.',
        'provider_down': '{provider}: not responding.',
        'provider_restored': '{provider}: responding again.',
    },
}


def get_text(locale: str, key: str, **kwargs: Any) -> str:
    """Get localized text for the given key."""
    locale = locale if locale in TRANSLATIONS else 'ru'
    text = TRANSLATIONS[locale].get(key, TRANSLATIONS['ru'].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text
