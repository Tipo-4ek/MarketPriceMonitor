# MarketPriceMonitor

A Telegram bot that tracks product prices on Russian marketplaces: send it a
product link, it polls the price on a schedule and messages you when the price
moves past your threshold.

![CI](https://github.com/Tipo-4ek/MarketPriceMonitor/actions/workflows/ci.yml/badge.svg)

**Stack:** Python 3.14 · aiogram 3 · SQLAlchemy 2 (async) · PostgreSQL · Alembic
· Playwright · Poetry · pytest · ruff

The interesting part of this repository is not that it scrapes — it is the
shape around the scraping: a provider abstraction that survives two
marketplaces with genuinely different mechanics, a polling scheduler that
notices when a provider stops working, and an honest account of what actually
does and does not work against live anti-bot systems.

## Architecture

- **Provider abstraction + URL-dispatch registry.** A provider implements
  `supports` / `normalize` / `fetch_product` plus a `provider_type`
  ([`base.py`](bot/core/providers/base.py)); the registry routes an incoming URL
  to whichever provider claims it. Adding a marketplace is one module, one
  registry entry and one `ProviderEnum` member.
- **Two providers, two strategies.** Ozon is parsed from the rendered page
  ([`ozon.py`](bot/core/providers/ozon.py)); Wildberries renders prices
  client-side, so its provider intercepts the marketplace's own JSON API
  response instead of parsing markup ([`wildberries.py`](bot/core/providers/wildberries.py)).
  The abstraction earning its keep across those two is the point of having it.
- **One shared browser session.** Both providers borrow pages from a single
  long-lived Chrome context ([`browser.py`](bot/core/providers/browser.py))
  rather than launching a browser per product.
- **Health-checked polling scheduler.** [`scheduler.py`](bot/core/scheduler.py)
  polls every tracked product on an interval. A sliding error window per
  provider ([`health.py`](bot/core/providers/health.py)) drives an
  OK → DEGRADED → DOWN state machine, and admins get de-duplicated,
  cooldown-gated alerts ([`alerts.py`](bot/core/alerts.py)) on every status
  transition, recovery included.
- **A typed error taxonomy.** `UnsupportedURLError`, `ProviderBlockedError` and
  `PriceNotFoundError` are distinct, because "the marketplace is blocking us"
  and "this link is not supported" are different problems and deserve different
  messages.
- **Per-marketplace throttle.** A minimum gap between requests to the same site
  ([`throttle.py`](bot/core/providers/throttle.py)) — see the note below for why
  this is a working requirement rather than good manners.
- **Typed SQLAlchemy 2 models + Alembic**, timezone-aware throughout, i18n
  (ru/en) with fallback, and an admin ACL middleware.

## What actually works, and what does not

Measured against live ozon.ru and wildberries.ru in July 2026, not assumed:

| Configuration | Result |
| --- | --- |
| Playwright's bundled Chromium, headless | refused — anti-bot challenge, never resolves |
| Playwright's bundled Chromium, headed | refused — same |
| Real Chrome (`channel='chrome'`), headed, persistent profile | **works** |
| Plain HTTP to either marketplace's internal JSON API | 403 |

Two consequences the code and the docs are built around:

1. **Price tracking needs a desktop host with Chrome installed.** That is why
   `HEADLESS_ENABLED` defaults to `false` and `BROWSER_CHANNEL` to `chrome`.
2. **The shipped container cannot scrape.** It has no real Chrome and no
   display, so providers report themselves blocked and the health monitor marks
   them DOWN — correct behaviour, not a bug. Docker is for the database,
   migrations, tests and development.

**Ozon's protection escalates.** During this work it served pages normally at
first and then, after roughly a dozen automated loads from one address within an
hour, began returning a captcha to everything from that address — including a
browser profile it had previously accepted. `MIN_REQUEST_INTERVAL_SECONDS`
exists because of that, and the default poll interval is 15 minutes for the same
reason. Treat the Ozon provider as a demonstration that works under polite use,
not as a guaranteed feed.

## Is it still working?

The standing question for any scraper. One command answers it, with no bot
token, database or Telegram involved:

```bash
poetry run market-price-check https://www.wildberries.ru/catalog/219279898/detail.aspx
# OK    ETNA COFFEE Кофе в зернах 250 гр, Суль-де-Минас
#       558 RUB  (wildberries)
```

Exit code 0 means a price was read; 1 means the marketplace refused or the page
no longer parses — exactly what the scheduler would record as a provider error.

## Running

### Locally — the only configuration that tracks prices

Requires Google Chrome installed.

```bash
poetry install
cp .env.example .env         # then fill in BOT_TOKEN and ADMIN_TG_IDS
poetry run alembic upgrade head
poetry run market-price-monitor
```

A Chrome window opens and stays open; that is the shared browser session. The
first request to a marketplace may sit through an anti-bot challenge for a
while, after which the profile in `.browser-profile/` is trusted and subsequent
polls are fast.

### With Docker — database, migrations, tests

```bash
cp .env.example .env
docker compose up --build
```

The bot container waits for Postgres, applies migrations and starts polling —
and, as described above, its providers will report themselves blocked.

## Tests

Tests run against an in-memory SQLite database and never touch the network.

```bash
poetry run pytest -q                              # 44 tests
docker compose --profile test run --rm tests      # the same suite inside the image
```

## Configuration

Every variable maps to a field in [`config.py`](bot/core/config.py); see
[`.env.example`](.env.example).

| Variable | Default | Description |
| --- | --- | --- |
| `BOT_TOKEN` | – | Telegram bot token from [@BotFather](https://t.me/botfather) (required) |
| `ADMIN_TG_IDS` | – | Comma-separated admin Telegram user IDs |
| `DATABASE_URL` | `postgresql+asyncpg://…` | Async SQLAlchemy URL (Postgres or `sqlite+aiosqlite://…`) |
| `DEFAULT_LOCALE` | `ru` | Default language |
| `DEFAULT_THRESHOLD_DELTA` | `5` | Default price-change threshold (%) |
| `POLL_INTERVAL_SECONDS` | `900` | Polling interval |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALERT_COOLDOWN_HOURS` | `24` | Minimum gap between repeat alerts for the same provider and status |
| `PROVIDER_ERROR_WINDOW_SECONDS` | `300` | Sliding window for the provider error counter |
| `PROVIDER_ERROR_THRESHOLD` | `5` | Errors within the window before a provider is DOWN |
| `HEADLESS_ENABLED` | `false` | Run the browser headless (both marketplaces refuse it) |
| `BROWSER_CHANNEL` | `chrome` | Playwright channel; empty falls back to bundled Chromium |
| `BROWSER_PROFILE_DIR` | `.browser-profile` | Where the browser profile is kept |
| `MIN_REQUEST_INTERVAL_SECONDS` | `30` | Minimum gap between requests to one marketplace |
| `PROXY_URL` | – | Optional proxy for the browser |

## Bot commands

**Users:** `/start`, `/help`, `/add <url>`, `/list`, `/remove <id>`,
`/monitor set <id> <delta>`, `/lang <ru|en>` (you can also just paste a URL).

**Admins:** `/provider_status`, `/alerts_on`, `/alerts_off`, `/health_reset`.

## Project layout

```text
bot/
  cli.py               # market-price-check: fetch one URL and report
  core/
    config.py          # pydantic-settings, reads env / .env
    clock.py           # one source of timezone-aware "now"
    logging.py         # JSON logs to stdout
    i18n.py            # ru/en translations with fallback
    scheduler.py       # background price-polling loop
    alerts.py          # alert cooldown + dedup
    startup.py         # entry point
    middlewares/       # admin ACL
    providers/
      base.py          # Provider interface, ProductData, error taxonomy
      __init__.py      # registry / URL dispatch
      browser.py       # shared Chrome session
      throttle.py      # per-marketplace minimum request interval
      ozon.py          # page-parsing provider
      wildberries.py   # API-interception provider
      health.py        # provider health state machine
    services/          # product / tracking business logic
  handlers/            # bot command handlers
  models/              # SQLAlchemy models
  utils/               # parsing / validation helpers
migrations/            # Alembic
tests/                 # pytest (in-memory sqlite, no network)
```

## A note on scraping

This is a personal-use project. It reads publicly visible product pages at a
deliberately slow rate, identifies itself as an ordinary browser without
attempting to defeat CAPTCHAs, uses no credentials, and backs off when a
marketplace signals that it does not want the traffic. If you run it, keep it
that way: respect each marketplace's Terms of Service and `robots.txt`, and do
not lower the polling interval.

## License

[MIT](LICENSE) © Ilya Lyubimov
