"""Application configuration loaded from the environment (and an optional .env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Scraping
    headless_enabled: bool = True
    proxy_file: str = ''
    proxy_url: str = ''
    test_mode: bool = False

    @property
    def admin_ids(self) -> list[int]:
        """Parse admin IDs from the comma-separated ADMIN_TG_IDS string."""
        if not self.admin_tg_ids:
            return []
        return [int(part.strip()) for part in self.admin_tg_ids.split(',') if part.strip()]


settings = Settings()
