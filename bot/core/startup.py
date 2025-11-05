"""Bot startup script."""
import asyncio

from aiogram import Bot, Dispatcher

from bot.core.config import settings
from bot.core.logging import get_logger, setup_logging
from bot.core.providers import provider_registry
from bot.core.scheduler import PriceScheduler
from bot.handlers import setup_handlers
from bot.models.base import init_db

logger = get_logger(__name__)


async def main():
    """Main entry point."""
    # Setup logging
    setup_logging(settings.log_level)
    logger.info('Starting MarketPriceMonitor Bot')

    # Initialize database
    init_db(settings.database_url)
    logger.info('Database initialized')

    # Create bot and dispatcher
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    # Setup handlers
    setup_handlers(dp)
    logger.info('Handlers registered')

    # Create and start scheduler
    scheduler = PriceScheduler(bot, provider_registry)
    scheduler_task = asyncio.create_task(scheduler.start())

    try:
        # Start polling
        logger.info('Starting polling')
        await dp.start_polling(bot, allowed_updates=['message'])
    finally:
        # Cleanup
        logger.info('Shutting down...')
        await scheduler.stop()
        await scheduler_task
        await bot.session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')


