"""Bot entry point."""

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.core.commands import register_bot_commands
from bot.core.config import ConfigError, settings, validate_runtime_settings
from bot.core.logging import get_logger, setup_logging
from bot.core.providers import provider_registry
from bot.core.providers.browser import browser_session
from bot.core.scheduler import PriceScheduler
from bot.handlers import setup_handlers
from bot.models.base import init_db

logger = get_logger(__name__)


async def main() -> None:
    """Start the bot and the price-polling scheduler, and shut both down cleanly."""
    setup_logging(settings.log_level)
    logger.info('Starting MarketPriceMonitor')

    init_db(settings.database_url)

    bot = Bot(token=settings.bot_token)
    # In-memory FSM storage: the only state kept is 'which argument am I
    # waiting for', which is worth nothing after a restart. Anything durable
    # lives in the database.
    dp = Dispatcher(storage=MemoryStorage())
    setup_handlers(dp)

    # Publish the command menu so clients can show it instead of the user having
    # to already know what to type.
    await register_bot_commands(bot)

    scheduler = PriceScheduler(bot, provider_registry)
    scheduler_task = asyncio.create_task(scheduler.start(), name='price-scheduler')

    try:
        # No allowed_updates= here on purpose. Passing a hand-written list
        # ('message') overrides aiogram's own resolution and makes Telegram
        # withhold every other update type server-side — callback_query included,
        # which silently kills every inline button the bot ships. Omitting it lets
        # aiogram compute the set from the registered handlers.
        await dp.start_polling(bot)
    finally:
        logger.info('Shutting down')
        await scheduler.stop()
        # stop() sets an event the loop waits on, so this returns promptly
        # instead of blocking until the current poll interval elapses.
        await scheduler_task
        # The browser is a long-lived child process; leaking it would leave a
        # Chrome window behind on every restart.
        await browser_session.close()
        await bot.session.close()


def run() -> None:
    """Console-script entry point (`market-price-monitor`)."""
    try:
        validate_runtime_settings()
    except ConfigError as exc:
        # A missing token is a configuration mistake, not a crash: say what to
        # do in one line rather than printing an aiogram traceback.
        print(f'Configuration error: {exc}', file=sys.stderr)  # noqa: T201
        raise SystemExit(2) from None

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')


if __name__ == '__main__':
    run()
