"""Application configuration using hardcoded settings."""
import sys
import os

# Add project root to path to import bot_config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot_config


class Settings:
    """Application settings using hardcoded configuration."""

    def __init__(self):
        # Bot Configuration
        self.bot_token = bot_config.BOT_TOKEN

        # Database Configuration
        self.database_url = bot_config.DATABASE_URL

        # Bot Settings
        self.default_locale = bot_config.DEFAULT_LOCALE
        self.default_threshold_delta = bot_config.DEFAULT_THRESHOLD_DELTA
        self.poll_interval_seconds = bot_config.POLL_INTERVAL_SECONDS
        self.log_level = bot_config.LOG_LEVEL

        # Admin Configuration
        self.admin_tg_ids = bot_config.ADMIN_TG_IDS

        # Alert Settings
        self.alert_cooldown_hours = bot_config.ALERT_COOLDOWN_HOURS
        self.provider_error_window_seconds = bot_config.PROVIDER_ERROR_WINDOW_SECONDS
        self.provider_error_threshold = bot_config.PROVIDER_ERROR_THRESHOLD

        # Anti-bot Configuration
        self.proxy_url = bot_config.PROXY_URL
        self.proxy_file = bot_config.PROXY_FILE
        self.headless_enabled = bot_config.HEADLESS_ENABLED
        
        # Test mode
        self.test_mode = bot_config.TEST_MODE

    @property
    def admin_ids(self) -> list[int]:
        """Parse admin IDs from comma-separated string."""
        if not self.admin_tg_ids:
            return []
        return [int(id_.strip()) for id_ in self.admin_tg_ids.split(',') if id_.strip()]


# Global settings instance
settings = Settings()

