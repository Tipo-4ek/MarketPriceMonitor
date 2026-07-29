"""Fetch one product URL through the provider registry and print the result.

The standing question for any scraper is "does it still work?". This answers it
in one command, without a bot token, a database or Telegram:

    poetry run market-price-check https://www.ozon.ru/product/...

Exit code 0 means a price was read; 1 means the marketplace refused or the page
no longer parses — which is exactly what the scheduler would have recorded as a
provider error.
"""

import argparse
import asyncio
import sys

from bot.core.config import settings
from bot.core.logging import get_logger, setup_logging
from bot.core.providers import provider_registry
from bot.core.providers.base import ProviderError
from bot.core.providers.browser import browser_session

logger = get_logger(__name__)


async def check(urls: list[str]) -> int:
    """Fetch each URL and report what came back. Returns a process exit code."""
    failures = 0
    try:
        for url in urls:
            try:
                provider = provider_registry.find_provider(url)
                normalized = await provider.normalize(url)
                data = await provider.fetch_product(normalized)
            except ProviderError as exc:
                failures += 1
                print(f'FAIL  {url}\n      {type(exc).__name__}: {exc}')  # noqa: T201 - this is the CLI's output
                continue

            print(  # noqa: T201 - this is the CLI's output
                f'OK    {data.title}\n'
                f'      {data.price} {data.currency}  ({provider.provider_type.value})\n'
                f'      {data.url}'
            )
    finally:
        await browser_session.close()

    return 1 if failures else 0


def main() -> None:
    """Console-script entry point (`market-price-check`)."""
    parser = argparse.ArgumentParser(description='Check that a marketplace provider still returns a price.')
    parser.add_argument('urls', nargs='+', help='product URLs to fetch')
    parser.add_argument('--log-level', default='WARNING', help='log level for the fetch itself')
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger.info('Provider check starting', extra={'headless': settings.headless_enabled})
    sys.exit(asyncio.run(check(args.urls)))


if __name__ == '__main__':
    main()
