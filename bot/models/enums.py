"""Database enums."""

import enum


class ProviderEnum(enum.StrEnum):
    """Marketplaces with a working provider implementation.

    A member is added here only when a provider actually fetches prices for it:
    the registry is keyed by this enum, so a speculative member would be a
    marketplace the bot claims to support and then fails on.
    """

    OZON = 'ozon'
    WILDBERRIES = 'wildberries'


class ProviderStatus(enum.StrEnum):
    """Provider health status."""

    OK = 'ok'
    DEGRADED = 'degraded'
    DOWN = 'down'
