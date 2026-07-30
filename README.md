# MarketPriceMonitor

A Telegram bot that tracks product prices: send it a product link, it polls the
price on a schedule and messages you when the price moves past your threshold.

![CI](https://github.com/Tipo-4ek/MarketPriceMonitor/actions/workflows/ci.yml/badge.svg)

**Stack:** Python 3.14 · aiogram 3 · SQLAlchemy 2 (async) · PostgreSQL · Alembic
· Playwright · Poetry · pytest · ruff

The hard part of price tracking is not the schedule or the database. It is that
every shop hides its price somewhere else, moves it without warning, and — for the
large marketplaces — decides whether to serve you a page at all. This repository is
built around that problem: site-agnostic price readers tried in turn, a transport
measured against live anti-bot systems, and an honest record of what works.

## Reading a price without knowing the site

The core is a chain of readers that know web conventions rather than shops
([`generic_parsers.py`](bot/core/providers/generic_parsers.py)):

- **schema.org JSON-LD** — `Product` / `offers.price`, including `@graph` nesting.
- **schema.org microdata** — `itemprop="price"`.
- **Open Graph / product meta** — `product:price:amount`.
- **Hydration state** — the JSON a front end feeds its own widgets from, found by
  searching any nesting for price-shaped keys rather than a fixed path, because
  that shape changes freely between deploys.
- **Rendered text** — money in the price element, with unit rates like
  "218 ₽ за 100 гр" discarded.

Each breaks on a different kind of redesign and none breaks on all of them, which
is the point of having five.

A [`StrategyChain`](bot/core/providers/strategies.py) runs them until one returns a
plausible price, then **remembers which one worked and tries it first next time**.
One page fetch feeds every reader, so trying more ways costs no extra requests to
the shop. When the shape is ambiguous the chain returns nothing rather than a
guess: a price out by a factor of two fires a false alert to everyone tracking
that product, which is worse than a missed poll.

## Architecture

- **Provider abstraction + URL-dispatch registry.** A provider implements
  `supports` / `normalize` / `fetch_product` plus a `provider_type`
  ([`base.py`](bot/core/providers/base.py)); the registry routes an incoming URL to
  whichever provider claims it. A provider supplies the transport and any
  site-specific reader; the generic readers it gets for free.
- **One shared browser session.** Providers borrow a single long-lived Chrome page
  ([`browser.py`](bot/core/providers/browser.py)) rather than launching a browser
  per product.
- **Health-checked polling scheduler.** [`scheduler.py`](bot/core/scheduler.py)
  polls every tracked product on an interval. A sliding error window per provider
  ([`health.py`](bot/core/providers/health.py)) drives an OK → DEGRADED → DOWN state
  machine; admins get de-duplicated, cooldown-gated alerts
  ([`alerts.py`](bot/core/alerts.py)) on each transition, recovery included; and a
  provider marked DOWN is skipped for several cycles instead of hammered.
- **A typed error taxonomy.** `UnsupportedURLError`, `ProviderBlockedError` and
  `PriceNotFoundError` are distinct, because "this link is not supported", "the shop
  is refusing us" and "the page changed shape" are three different problems that
  deserve three different messages — and only some of them say anything about the
  shop's health.
- **Per-host throttle** ([`throttle.py`](bot/core/providers/throttle.py)) — a minimum
  gap between requests to the same site. Measured necessity, not manners.
- **Typed SQLAlchemy 2 models + Alembic**, timezone-aware throughout, i18n (ru/en),
  admin ACL middleware, and structured JSON logs to stdout.

## What actually works

Everything in [docs/marketplace-access.md](docs/marketplace-access.md) was run, from
two networks — a residential connection and a datacenter VM on an unrelated subnet.
The short version:

- **A real browser is the only transport that gets a page.** TLS impersonation is
  not enough: `curl_cffi` across six browser fingerprints and three endpoints was
  refused eighteen times out of eighteen.
- **The browser profile is the asset, not the IP.** A cold profile is refused even
  from an address that has never contacted the site; the same profile, once through
  the transparent challenge, is served normally. So `BROWSER_PROFILE_DIR` must
  survive restarts, and the first fetch after a fresh deploy is slow.
- **Headless is refused** — including headless real Chrome. A server with no display
  still works under a virtual framebuffer (`xvfb-run`), which is how it is deployed.
- **Shipped provider: Wildberries.** Ozon is deliberately **not** shipped: it serves
  a captcha and a structured block record, and getting past that is circumventing an
  access control rather than finding a compatible configuration. The measurements are
  kept because they are the useful part; code that always fails is not.

## Is it still working?

The standing question for anything that scrapes. One command answers it, with no bot
token, database or Telegram involved:

```bash
poetry run market-price-check https://www.wildberries.ru/catalog/219279898/detail.aspx
# OK    ETNA COFFEE Кофе в зернах 250 гр, Суль-де-Минас
#       661 RUB  (wildberries)
#       https://www.wildberries.ru/catalog/219279898/detail.aspx
```

Exit code 0 means a price was read; 1 means the shop refused or the page no longer
parses — exactly what the scheduler would record as a provider error. The log names
the strategy that won, so a silent migration from one reader to another is visible
rather than mysterious.

## Running

### On a desktop with Chrome

```bash
poetry install
cp .env.example .env         # fill in BOT_TOKEN, ADMIN_TG_IDS, POSTGRES_PASSWORD
poetry run alembic upgrade head
poetry run market-price-monitor
```

A Chrome window opens and stays open — that is the shared session. The first request
to a shop may sit through a challenge; after that the profile in `.browser-profile/`
is trusted and polls are fast.

### On a headless server

Ubuntu 24.04, verified end to end:

```bash
sudo apt-get install -y xvfb google-chrome-stable
xvfb-run -a --server-args="-screen 0 1440x900x24" poetry run market-price-monitor
```

### With Docker — database, migrations, tests

```bash
cp .env.example .env    # BOT_TOKEN and POSTGRES_PASSWORD are required
docker compose up --build
```

The image carries Chromium but no display and no real Chrome, so it runs the bot,
the migrations and the tests — not the scraping.

## Tests

92 tests against an in-memory SQLite database. None touch the network.

```bash
poetry run pytest -q
docker compose --profile test run --rm tests      # the same suite inside the image
```

CI additionally runs the migrations against a real PostgreSQL and asserts the
resulting schema matches the models
([`scripts/check_schema_drift.py`](scripts/check_schema_drift.py)) — the unit suite
builds its schema from the models on SQLite, so it cannot see that class of drift by
construction.

## Configuration

Every variable maps to a field in [`config.py`](bot/core/config.py); see
[`.env.example`](.env.example).

| Variable | Default | Description |
| --- | --- | --- |
| `BOT_TOKEN` | – | Telegram bot token from [@BotFather](https://t.me/botfather) (required) |
| `ADMIN_TG_IDS` | – | Comma-separated admin Telegram user IDs |
| `DATABASE_URL` | `sqlite+aiosqlite:///./price_tracker.db` | Async SQLAlchemy URL; docker compose overrides it with Postgres |
| `POSTGRES_PASSWORD` | – | Required by docker compose; there is deliberately no default |
| `DEFAULT_LOCALE` | `ru` | Default language |
| `DEFAULT_THRESHOLD_DELTA` | `5` | Default price-change threshold (%) |
| `POLL_INTERVAL_SECONDS` | `900` | Polling interval |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALERT_COOLDOWN_HOURS` | `24` | Minimum gap between repeat alerts for one provider and status |
| `PROVIDER_ERROR_WINDOW_SECONDS` | `3600` | Sliding window for the error counter; must be >= the poll interval |
| `PROVIDER_ERROR_THRESHOLD` | `5` | Errors within the window before a provider is DOWN |
| `HEADLESS_ENABLED` | `false` | Run the browser headless (the shops tested refuse it) |
| `BROWSER_CHANNEL` | `chrome` | Playwright channel; empty falls back to bundled Chromium |
| `BROWSER_PROFILE_DIR` | `.browser-profile` | Where the browser profile is kept |
| `MIN_REQUEST_INTERVAL_SECONDS` | `30` | Minimum gap between requests to one host |
| `PROXY_URL` | – | Optional proxy for the browser |

## Bot commands

Arguments are optional: tapping a command in Telegram's menu sends it bare and the
bot then asks for what it needs, offering buttons wherever a choice can be made
instead of an id typed.

**Users:** `/start`, `/add [url]`, `/list`, `/remove [id]`,
`/monitor [set <id> <delta>]`, `/lang [ru|en]`, `/cancel`, `/help`.
A bare link works with no command at all.

**Admins:** `/provider_status`, `/alerts_on`, `/alerts_off`, `/health_reset` —
published to admins only, via a per-chat command scope.

The menu, the `/help` text and the handlers are all generated from one list
([`commands.py`](bot/core/commands.py)), and a test fails if a handler exists without
a declared command or the reverse.

## Project layout

```text
bot/
  cli.py               # market-price-check: fetch one URL and report
  keyboards.py         # inline keyboards and their callback payloads
  core/
    commands.py        # the command list: menu, /help and handlers agree
    config.py          # pydantic-settings, reads env / .env
    clock.py           # one source of timezone-aware "now"
    logging.py         # JSON logs to stdout
    i18n.py            # ru/en translations with fallback
    states.py          # FSM states for commands that ask for arguments
    scheduler.py       # background price-polling loop
    alerts.py          # alert cooldown + dedup
    startup.py         # entry point
    middlewares/       # admin ACL
    providers/
      base.py          # Provider interface, ProductData, error taxonomy
      __init__.py      # registry / URL dispatch
      strategies.py    # the self-reordering strategy chain
      generic_parsers.py     # site-agnostic price readers
      wildberries.py         # transport
      wildberries_parsers.py # site-specific readers
      browser.py       # shared Chrome session
      throttle.py      # per-host minimum request interval
      health.py        # provider health state machine
    services/          # product / tracking business logic
  handlers/            # bot command handlers and callbacks
  models/              # SQLAlchemy models
  utils/               # parsing / validation helpers
docs/                  # marketplace-access.md: what was measured
migrations/            # Alembic
scripts/               # check_schema_drift.py, run in CI
tests/                 # pytest (in-memory sqlite, no network)
```

## A note on scraping

This is a personal-use project, and worth being exact about rather than claiming a
clean conscience it has not earned.

It reads publicly visible product pages slowly: fifteen minutes between polls,
thirty seconds minimum between two requests to the same host, and a provider the
health monitor marks DOWN is skipped for several cycles rather than retried. It uses
no credentials, does not solve or bypass CAPTCHAs, and treats a site that serves one
as a site that has said no.

It does not present itself as an ordinary browser in perfect good faith: it hides the
`navigator.webdriver` flag and passes `--disable-blink-features=AutomationControlled`.
Whether either is still needed for the shipped provider is an open question — an A/B
test was inconclusive because it accidentally compared profile warmth instead.

Before adding a shop, `robots.txt` is read for it; a site that denies data crawlers
by name is treated as having answered, even when the product path itself is allowed.
If you run this, keep the intervals where they are.

## License

[MIT](LICENSE) © Ilya Lyubimov
