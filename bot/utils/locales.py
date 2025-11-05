"""Locale utilities."""

SUPPORTED_LOCALES = ('ru', 'en')


def normalize_locale(locale: str | None) -> str:
    """Normalize locale to supported value."""
    if locale and locale.lower() in SUPPORTED_LOCALES:
        return locale.lower()
    return 'ru'


