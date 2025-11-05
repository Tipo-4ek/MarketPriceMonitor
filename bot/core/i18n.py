"""Internationalization support."""
from typing import Any

# Translations dictionary
TRANSLATIONS: dict[str, dict[str, str]] = {
    'ru': {
        'welcome': '👋 Добро пожаловать! Я помогу отслеживать цены на товары из маркетплейсов.',
        'help': (
            '📖 Доступные команды:\n\n'
            '/add <url> - добавить товар для отслеживания\n'
            '/list - показать отслеживаемые товары\n'
            '/remove <id|url> - удалить товар из отслеживания\n'
            '/monitor default <delta> - установить порог изменения цены по умолчанию (%)\n'
            '/monitor set <id> <delta> - установить порог для конкретного товара (%)\n'
            '/lang <ru|en> - изменить язык\n\n'
            'Вы также можете просто отправить ссылку на товар без команды /add.'
        ),
        'language_changed': '✅ Язык изменен на русский',
        'invalid_language': '❌ Неподдерживаемый язык. Доступны: ru, en',
        'product_added': '✅ Товар добавлен:\n<b>{title}</b>\nЦена: {price} {currency}\nID: {product_id}',
        'product_exists': '⚠️ Этот товар уже отслеживается (ID: {product_id})',
        'invalid_url': '❌ Неподдерживаемая ссылка. Пока поддерживается только Ozon.',
        'provider_error': '❌ Не удалось получить информацию о товаре. Попробуйте позже.',
        'tracked_products': '📦 Ваши отслеживаемые товары:\n\n{products}',
        'no_tracked_products': '📭 У вас нет отслеживаемых товаров',
        'product_removed': '✅ Товар удален из отслеживания',
        'product_not_found': '❌ Товар не найден',
        'invalid_product_id': '❌ Неверный ID товара',
        'default_threshold_set': '✅ Порог по умолчанию установлен: {delta}%',
        'custom_threshold_set': '✅ Порог для товара {product_id} установлен: {delta}%',
        'invalid_threshold': '❌ Неверное значение порога. Укажите число от 1 до 100.',
        'price_changed': (
            '💰 Изменение цены!\n\n'
            '<b>{title}</b>\n'
            'Старая цена: {old_price} {currency}\n'
            'Новая цена: {new_price} {currency}\n'
            'Изменение: {change}%\n\n'
            '<a href="{url}">Перейти к товару</a>'
        ),
        'access_denied': '🚫 Доступ запрещен. Эта команда доступна только администраторам.',
        'provider_status': '🏥 Статус провайдеров:\n\n{statuses}',
        'alerts_enabled': '🔔 Оповещения о сбоях провайдеров включены',
        'alerts_disabled': '🔕 Оповещения о сбоях провайдеров отключены',
        'health_reset': '🔄 Статус провайдеров сброшен',
        'provider_degraded': '⚠️ Провайдер {provider} работает с перебоями',
        'provider_down': '🔴 Провайдер {provider} недоступен',
        'provider_restored': '✅ Провайдер {provider} восстановлен',
    },
    'en': {
        'welcome': '👋 Welcome! I will help you track prices on marketplace products.',
        'help': (
            '📖 Available commands:\n\n'
            '/add <url> - add product to track\n'
            '/list - show tracked products\n'
            '/remove <id|url> - remove product from tracking\n'
            '/monitor default <delta> - set default price change threshold (%)\n'
            '/monitor set <id> <delta> - set threshold for specific product (%)\n'
            '/lang <ru|en> - change language\n\n'
            'You can also just send a product link without the /add command.'
        ),
        'language_changed': '✅ Language changed to English',
        'invalid_language': '❌ Unsupported language. Available: ru, en',
        'product_added': '✅ Product added:\n<b>{title}</b>\nPrice: {price} {currency}\nID: {product_id}',
        'product_exists': '⚠️ This product is already tracked (ID: {product_id})',
        'invalid_url': '❌ Unsupported link. Only Ozon is supported for now.',
        'provider_error': '❌ Failed to fetch product information. Try again later.',
        'tracked_products': '📦 Your tracked products:\n\n{products}',
        'no_tracked_products': '📭 You have no tracked products',
        'product_removed': '✅ Product removed from tracking',
        'product_not_found': '❌ Product not found',
        'invalid_product_id': '❌ Invalid product ID',
        'default_threshold_set': '✅ Default threshold set: {delta}%',
        'custom_threshold_set': '✅ Threshold for product {product_id} set: {delta}%',
        'invalid_threshold': '❌ Invalid threshold value. Specify a number from 1 to 100.',
        'price_changed': (
            '💰 Price change!\n\n'
            '<b>{title}</b>\n'
            'Old price: {old_price} {currency}\n'
            'New price: {new_price} {currency}\n'
            'Change: {change}%\n\n'
            '<a href="{url}">Go to product</a>'
        ),
        'access_denied': '🚫 Access denied. This command is only available to administrators.',
        'provider_status': '🏥 Provider status:\n\n{statuses}',
        'alerts_enabled': '🔔 Provider failure alerts enabled',
        'alerts_disabled': '🔕 Provider failure alerts disabled',
        'health_reset': '🔄 Provider status reset',
        'provider_degraded': '⚠️ Provider {provider} is experiencing issues',
        'provider_down': '🔴 Provider {provider} is down',
        'provider_restored': '✅ Provider {provider} restored',
    },
}


def get_text(locale: str, key: str, **kwargs: Any) -> str:
    """Get localized text for the given key."""
    locale = locale if locale in TRANSLATIONS else 'ru'
    text = TRANSLATIONS[locale].get(key, TRANSLATIONS['ru'].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text


class I18n:
    """Internationalization helper."""

    def __init__(self, default_locale: str = 'ru'):
        self.default_locale = default_locale

    def get(self, locale: str | None, key: str, **kwargs: Any) -> str:
        """Get localized text."""
        return get_text(locale or self.default_locale, key, **kwargs)


