"""Database enums."""

import enum


class ProviderEnum(str, enum.Enum):
    """Supported marketplace providers."""

    OZON = 'ozon'
    AVITO = 'avito'
    WILDBERRIES = 'wildberries'
    YANDEX_MARKET = 'yandex_market'


class ProviderStatus(str, enum.Enum):
    """Provider health status."""

    OK = 'ok'
    DEGRADED = 'degraded'
    DOWN = 'down'
