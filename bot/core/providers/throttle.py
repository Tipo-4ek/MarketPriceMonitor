"""A minimum gap between requests to the same marketplace.

This exists because of something measured rather than assumed. Ozon's anti-bot
protection escalates: the first visits from a residential IP with real Chrome
are served normally, and after roughly a dozen automated page loads within an
hour it starts returning a captcha to *everything* from that address —
including a browser profile it had previously accepted.

So politeness here is not decoration, it is the difference between a provider
that keeps working and one that gets the whole host blocked. The default gap is
deliberately larger than a human would need, because nothing about price
tracking is urgent.
"""

import asyncio
import time
from collections import defaultdict

from bot.core.config import settings
from bot.core.logging import get_logger
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)


class Throttle:
    """Serialise requests per marketplace, with a minimum gap between them."""

    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._last_request: dict[ProviderEnum, float] = defaultdict(float)
        self._locks: dict[ProviderEnum, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def wait(self, provider: ProviderEnum) -> None:
        """Block until this marketplace may be contacted again."""
        async with self._locks[provider]:
            elapsed = time.monotonic() - self._last_request[provider]
            remaining = self.min_interval_seconds - elapsed
            if remaining > 0:
                logger.debug(
                    'Throttling request',
                    extra={'provider': provider.value, 'sleep_seconds': round(remaining, 1)},
                )
                await asyncio.sleep(remaining)
            self._last_request[provider] = time.monotonic()


# Shared by every provider.
throttle = Throttle(settings.min_request_interval_seconds)
