"""Application configuration loaded from the environment (and an optional .env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Raised when a setting the bot cannot run without is missing."""


class Settings(BaseSettings):
    """Runtime settings. Field names map to upper-case environment variables."""

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # Telegram
    bot_token: str = ''
    admin_tg_ids: str = ''

    # Database (async SQLAlchemy URL). SQLite by default so a fresh clone runs
    # with no infrastructure; docker-compose overrides it with Postgres.
    database_url: str = 'sqlite+aiosqlite:///./price_tracker.db'

    # Behaviour
    default_locale: str = 'ru'
    default_threshold_delta: int = 5
    poll_interval_seconds: int = 900
    log_level: str = 'INFO'

    # Provider health / alerts.
    #
    # The error window must outlast the time it takes to accumulate the whole
    # threshold. A provider is polled once per interval, so the Nth error lands
    # (N-1) intervals after the first; if the window is shorter than that, the
    # first error ages out before the last arrives and the counter never reaches
    # the threshold — the health machine reports OK forever. The default sits
    # comfortably above (threshold-1)*interval = 3600s; validate_runtime_settings
    # enforces the relationship.
    alert_cooldown_hours: int = 24
    provider_error_window_seconds: int = 7200
    provider_error_threshold: int = 5

    # Browser used for scraping. The defaults are the configuration that was
    # measured to actually work: real Chrome, headed, with a persistent profile.
    # Headless is left as a switch because it is useful for experiments, but the
    # marketplaces tested reject it (see providers/browser.py).
    headless_enabled: bool = False
    browser_channel: str = 'chrome'
    browser_profile_dir: str = '.browser-profile'
    proxy_url: str = ''

    # Minimum gap between two requests to the same marketplace. Marketplaces
    # escalate against bursts from one address (see docs/marketplace-access.md),
    # so this is a working requirement rather than good manners.
    min_request_interval_seconds: float = 30.0

    # Read prices from any site, not just the shipped providers. Off by default:
    # it points a real browser at whatever a user sends, so it is a deliberate
    # opt-in with its own safety gate (see providers/url_safety.py and the
    # README's security note).
    generic_provider_enabled: bool = False

    # Extra hosts the generic provider must never fetch, on top of the built-in
    # block of private / loopback / link-local addresses. Comma-separated
    # hostnames or IPs; a hostname also blocks its subdomains. Empty by default:
    # a public deployment that enables the generic provider fills this with its
    # own domains and public IP so a stranger cannot point the browser at them.
    blocked_hosts: str = ''

    @property
    def blocked_host_set(self) -> frozenset[str]:
        """The BLOCKED_HOSTS entries, lower-cased, as a set."""
        return frozenset(part.strip().lower() for part in self.blocked_hosts.split(',') if part.strip())

    @property
    def admin_ids(self) -> list[int]:
        """Parse admin IDs from the comma-separated ADMIN_TG_IDS string.

        Raises ``ValueError`` on a non-numeric entry; :func:`validate_runtime_settings`
        turns that into one actionable line at startup rather than an exception on
        every incoming update.
        """
        if not self.admin_tg_ids:
            return []
        return [int(part.strip()) for part in self.admin_tg_ids.split(',') if part.strip()]


settings = Settings()


def validate_runtime_settings() -> None:
    """Fail fast, and legibly, on settings the bot cannot start without.

    BOT_TOKEN is deliberately *not* a required pydantic field: making it one
    would raise a ValidationError at import time, so merely importing the
    package (in tests, or on the Alembic path) would need a token. Checking it
    here keeps imports cheap and turns a stack trace into one actionable line.
    """
    if not settings.bot_token:
        raise ConfigError('BOT_TOKEN is not set — copy .env.example to .env and fill in your @BotFather token')

    try:
        _ = settings.admin_ids  # parsing the property is the validation
    except ValueError as exc:
        raise ConfigError(
            f'ADMIN_TG_IDS must be comma-separated numeric Telegram user IDs, got {settings.admin_tg_ids!r} ({exc})'
        ) from None

    # A provider is polled once per interval, so reaching the error threshold
    # takes (threshold - 1) intervals of accumulation. The window must outlast
    # that, or the oldest error ages out before the newest arrives and the
    # counter can never reach the threshold — the health machine reports OK
    # forever. Requiring merely window >= interval is not enough with the shipped
    # threshold of 5 and one product per provider.
    min_window = (settings.provider_error_threshold - 1) * settings.poll_interval_seconds
    if settings.provider_error_window_seconds <= min_window:
        raise ConfigError(
            f'PROVIDER_ERROR_WINDOW_SECONDS ({settings.provider_error_window_seconds}) must exceed '
            f'(PROVIDER_ERROR_THRESHOLD - 1) * POLL_INTERVAL_SECONDS ({min_window}), otherwise a provider that '
            'fails every cycle still never accumulates enough errors inside the window to be marked DOWN'
        )
