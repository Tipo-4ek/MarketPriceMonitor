# MarketPriceMonitor

A Telegram bot that tracks product prices on marketplaces: send it a product
link, it polls the price on a schedule and messages you when the price moves
past your threshold.

![CI](https://github.com/Tipo-4ek/MarketPriceMonitor/actions/workflows/ci.yml/badge.svg)

The point of this repository is the **architecture** — a pluggable provider
model behind a health-checked async scheduler — not a maintained scraper for
any one marketplace. One example provider (Ozon) is included to exercise the
design end to end.

> **Status:** reference implementation. Marketplace anti-bot measures change
> over time; the example provider reflects a workable approach and is not
> guaranteed to keep parsing any given site.

**Stack:** Python 3.12 · aiogram 3 · SQLAlchemy 2 (async) · PostgreSQL · Alembic
· Playwright · Poetry · pytest · ruff

## Architecture

- **Provider abstraction + URL-dispatch registry.** Adding a marketplace means
  implementing one interface (`supports` / `normalize` / `fetch_product` in
  [`bot/core/providers/base.py`](bot/core/providers/base.py)) and registering
  it. The registry routes an incoming URL to the provider that claims it.
- **Health-checked async polling scheduler.**
  [`scheduler.py`](bot/core/scheduler.py) polls every tracked product on an
  interval. A sliding error window per provider
  ([`health.py`](bot/core/providers/health.py)) drives an OK → DEGRADED → DOWN
  state machine, and admins get de-duplicated, cooldown-gated alerts
  ([`alerts.py`](bot/core/alerts.py)) on status transitions.
- **Typed SQLAlchemy 2 models + Alembic.** `Mapped[...]` models with cascades
  and constraints ([`bot/models/`](bot/models/)) and a hand-written initial
  migration ([`migrations/versions/001_initial.py`](migrations/versions/001_initial.py)).
- **i18n (ru/en) with fallback** ([`i18n.py`](bot/core/i18n.py)) and an
  **admin ACL middleware** ([`admin_acl.py`](bot/core/middlewares/admin_acl.py)).
- **Config from the environment** via pydantic-settings
  ([`config.py`](bot/core/config.py)) — see [`.env.example`](.env.example).

## Project layout

```text
bot/
  core/
    config.py          # pydantic-settings, reads env / .env
    logging.py         # structured logging
    i18n.py            # ru/en translations with fallback
    scheduler.py       # background price-polling loop
    alerts.py          # alert cooldown + dedup
    startup.py         # entry point
    middlewares/       # admin ACL
    providers/
      base.py          # Provider interface + ProductData
      __init__.py      # registry / URL dispatch
      ozon.py          # example provider (Playwright)
      health.py        # provider health state machine
      anti_bot/        # proxy pool + user-agent rotation
    services/          # product / tracking business logic
  handlers/            # bot command handlers
  models/              # SQLAlchemy models
  utils/               # parsing / validation helpers
migrations/            # Alembic
tests/                 # pytest (in-memory sqlite)
```

## Configuration

Copy `.env.example` to `.env` and fill it in. Settings are read from the
environment (upper-case names map to the fields in `config.py`).

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_TOKEN` | – | Telegram bot token from [@BotFather](https://t.me/botfather) (required) |
| `ADMIN_TG_IDS` | – | Comma-separated admin Telegram user IDs |
| `DATABASE_URL` | `postgresql+asyncpg://…` | Async SQLAlchemy URL (Postgres or `sqlite+aiosqlite://…`) |
| `DEFAULT_LOCALE` | `ru` | Default language |
| `DEFAULT_THRESHOLD_DELTA` | `5` | Default price-change threshold (%) |
| `POLL_INTERVAL_SECONDS` | `900` | Polling interval |
| `LOG_LEVEL` | `INFO` | Logging level |
| `HEADLESS_ENABLED` | `true` | Run the scraping browser headless (see note below) |
| `PROXY_FILE` / `PROXY_URL` | – | Optional proxy pool / single proxy |

## Running

### Locally (recommended for real tracking)

```bash
poetry install
poetry run playwright install chromium
cp .env.example .env         # then edit BOT_TOKEN, ADMIN_TG_IDS, DATABASE_URL
poetry run alembic upgrade head
poetry run python -m bot.core.startup
```

### With Docker (development / trying it out)

```bash
cp .env.example .env         # set BOT_TOKEN, ADMIN_TG_IDS
docker compose up --build
```

The bot container waits for Postgres, applies migrations, and starts polling.
See the note in `docker-compose.yml`: containers/datacenter IPs are easier for
marketplaces to flag, so a residential/desktop host is better for real use.

## Tests

Tests run against an in-memory SQLite database — no Postgres required.

```bash
poetry run pytest -v          # or: docker compose --profile test run --rm tests
```

## Bot commands

**Users:** `/start`, `/help`, `/add <url>`, `/list`, `/remove <id>`,
`/monitor set <id> <delta>`, `/lang <ru|en>` (you can also just paste a URL).

**Admins:** `/provider_status`, `/alerts_on`, `/alerts_off`, `/health_reset`.

## A note on scraping

The example provider uses Playwright to render an Ozon product page and reads
the price from the page's structured data. `HEADLESS_ENABLED=false` runs a
visible browser, which a residential host can use to avoid anti-bot challenges.
Respect each marketplace's Terms of Service and `robots.txt`, and keep polling
intervals reasonable. This project is for personal/educational use.

## License

[MIT](LICENSE) © Ilya Lyubimov
