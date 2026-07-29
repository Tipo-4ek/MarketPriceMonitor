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

    # Database (async SQLAlchemy URL)
    database_url: str = 'postgresql+asyncpg://postgres:postgres@localhost:5432/price_tracker'

    # Behaviour
    default_locale: str = 'ru'
    default_threshold_delta: int = 5
    poll_interval_seconds: int = 900
    log_level: str = 'INFO'

    # Provider health / alerts
    alert_cooldown_hours: int = 24
    provider_error_window_seconds: int = 300
    provider_error_threshold: int = 5

    # Browser used for scraping. The defaults are the configuration that was
    # measured to actually work: real Chrome, headed, with a persistent profile.
    # Headless is left as a switch because it is useful for experiments, but
    # both supported marketplaces reject it (see providers/browser.py).
    headless_enabled: bool = False
    browser_channel: str = 'chrome'
    browser_profile_dir: str = '.browser-profile'
    proxy_url: str = ''

    # Minimum gap between two requests to the same marketplace. Ozon escalates
    # against bursts of automated traffic from one address, so this is a working
    # requirement rather than good manners.
    min_request_interval_seconds: float = 30.0

    @property
    def admin_ids(self) -> list[int]:
        """Parse admin IDs from the comma-separated ADMIN_TG_IDS string."""
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
