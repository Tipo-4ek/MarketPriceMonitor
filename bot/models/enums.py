"""Database enums."""

import enum


class ProviderEnum(enum.StrEnum):
    """Providers the bot can fetch a price through.

    A member is added only when something actually reads a price for it: the
    registry is keyed by this enum, so a speculative member would be a promise
    the bot then fails on.

    ``WILDBERRIES`` is a site-specific provider — its own transport and readers.
    ``GENERIC`` is the opt-in fallback for any other host (see
    ``GENERIC_PROVIDER_ENABLED``): it has no site knowledge and reads price only
    from the markup a shop publishes (schema.org, Open Graph, hydration JSON),
    which covers most shops but not a page with none.
    """

    WILDBERRIES = 'wildberries'
    GENERIC = 'generic'


class ProviderStatus(enum.StrEnum):
    """Provider health status."""

    OK = 'ok'
    DEGRADED = 'degraded'
    DOWN = 'down'
