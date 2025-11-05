"""Docker-specific bot configuration."""

# Bot Configuration
BOT_TOKEN = ""  # Set your bot token here or use environment variable

# Database Configuration (using PostgreSQL for Docker)
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db:5432/price_tracker"

# Bot Settings
DEFAULT_LOCALE = "ru"
DEFAULT_THRESHOLD_DELTA = 5
POLL_INTERVAL_SECONDS = 900
LOG_LEVEL = "INFO"

# Admin Configuration
ADMIN_TG_IDS = ""  # Set your admin Telegram user ID here

# Alert Settings
ALERT_COOLDOWN_HOURS = 24
PROVIDER_ERROR_WINDOW_SECONDS = 300
PROVIDER_ERROR_THRESHOLD = 5

# Anti-bot Configuration
PROXY_FILE = "proxies.txt"
PROXY_URL = ""
HEADLESS_ENABLED = True

# Test Mode
TEST_MODE = False
