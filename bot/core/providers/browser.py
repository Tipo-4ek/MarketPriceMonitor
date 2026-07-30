"""One long-lived browser session, shared by every provider.

Why it looks like this, measured against live marketplaces in 2026
(docs/marketplace-access.md has the full table):

* **Real Chrome, not Playwright's bundled Chromium.** Bundled Chromium is
  refused outright — the challenge page never resolves, headless or headed.
  Launching the installed Chrome (``channel='chrome'``) passes it in seconds.
* **A persistent profile.** The challenge hands out cookies; keeping a profile
  on disk means the next poll starts already trusted instead of re-solving.
* **Headed by default.** The marketplaces tested reject headless, including
  headless real Chrome. A server with no display can still run this under a
  virtual framebuffer — `xvfb-run` — which is how it is deployed.
* **No User-Agent override.** Chrome's own UA matches its engine version and
  client hints; pinning a hand-written UA string creates exactly the
  inconsistency that anti-bot systems look for.
* **One context, reused.** A browser launch per product per cycle is seconds of
  latency and a burst of fresh fingerprints — expensive and more suspicious
  than a single steady session.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from bot.core.config import settings
from bot.core.logging import get_logger

logger = get_logger(__name__)

# Anti-automation shim, kept deliberately small and readable. Real Chrome needs
# very little; this only hides the one flag Playwright cannot avoid setting.
_STEALTH_INIT = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"


class BrowserSession:
    """Lazily started Chrome context that providers borrow pages from."""

    def __init__(
        self,
        *,
        profile_dir: str | None = None,
        channel: str | None = None,
        headless: bool | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self._profile_dir = Path(profile_dir if profile_dir is not None else settings.browser_profile_dir)
        self._channel = channel if channel is not None else settings.browser_channel
        self._headless = headless if headless is not None else settings.headless_enabled
        self._proxy_url = proxy_url if proxy_url is not None else settings.proxy_url

        # Navigations are serialised: polling several products in parallel would
        # multiply the load we put on a marketplace for no real gain.
        self._lock = asyncio.Lock()
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def _ensure_context(self) -> BrowserContext:
        if self._context is not None:
            return self._context

        self._profile_dir.mkdir(parents=True, exist_ok=True)

        launch_kwargs: dict = {
            'user_data_dir': str(self._profile_dir),
            'headless': self._headless,
            'locale': 'ru-RU',
            'timezone_id': 'Europe/Moscow',
            'viewport': {'width': 1440, 'height': 900},
            'args': ['--disable-blink-features=AutomationControlled', '--lang=ru-RU'],
            'extra_http_headers': {'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8'},
        }
        if self._channel:
            launch_kwargs['channel'] = self._channel
        if self._proxy_url:
            launch_kwargs['proxy'] = {'server': self._proxy_url}

        logger.info(
            'Starting browser session',
            extra={'channel': self._channel or 'bundled-chromium', 'headless': self._headless},
        )

        # start() spawns a node driver process. If the launch below fails — no
        # Chrome installed, a stale profile lock — that process must be reaped
        # here, or a persistently failing launch leaks one per attempt.
        playwright = await async_playwright().start()
        try:
            context = await playwright.chromium.launch_persistent_context(**launch_kwargs)
            await context.add_init_script(_STEALTH_INIT)
        except BaseException:
            with contextlib.suppress(Exception):
                await playwright.stop()
            raise

        self._playwright, self._context = playwright, context
        return context

    @contextlib.asynccontextmanager
    async def page(self) -> AsyncIterator[Page]:
        """Borrow the shared page, one caller at a time.

        One page is reused rather than opened and closed per fetch. Opening a tab
        raises and focuses the browser window on macOS, so a poll loop with a
        headed browser would steal focus on every cycle — which is intolerable on
        the desktop this is designed to run on. Reuse also skips the per-fetch
        page setup, and the lock already guarantees one caller at a time.
        """
        async with self._lock:
            context = await self._ensure_context()

            if self._page is None or self._page.is_closed():
                # launch_persistent_context opens with a blank page; adopt it
                # instead of adding a second one.
                self._page = context.pages[0] if context.pages else await context.new_page()

            yield self._page

    async def close(self) -> None:
        """Shut the browser down. Safe to call when it was never started."""
        async with self._lock:
            self._page = None
            if self._context is not None:
                with contextlib.suppress(Exception):
                    await self._context.close()
                self._context = None
            if self._playwright is not None:
                with contextlib.suppress(Exception):
                    await self._playwright.stop()
                self._playwright = None
            logger.info('Browser session closed')


# Shared by every provider; started on first use, closed on shutdown.
browser_session = BrowserSession()
