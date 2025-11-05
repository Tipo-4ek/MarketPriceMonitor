"""Background scheduler for price polling."""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.alerts import alert_manager
from bot.core.config import settings
from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.providers.health import health_monitor
from bot.models import Product, Tracking, User, base
from bot.models.enums import ProviderStatus

logger = get_logger(__name__)


class PriceScheduler:
    """Background scheduler for periodic price checking."""

    def __init__(self, bot: Bot, provider_registry):
        self.bot = bot
        self.provider_registry = provider_registry
        self.running = False

    async def start(self) -> None:
        """Start the scheduler."""
        self.running = True
        logger.info(f'Price scheduler started with interval {settings.poll_interval_seconds}s')
        await self._run_loop()

    async def stop(self) -> None:
        """Stop the scheduler."""
        self.running = False
        logger.info('Price scheduler stopped')

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self.running:
            try:
                await self._check_prices()
            except Exception as e:
                logger.error(f'Error in scheduler loop: {e}', exc_info=True)

            await asyncio.sleep(settings.poll_interval_seconds)

    async def _check_prices(self) -> None:
        """Check prices for all tracked products."""
        if not base.async_session_maker:
            return
        async with base.async_session_maker() as session:
            result = await session.execute(select(Product))
            products = result.scalars().all()

            logger.info(f'Checking prices for {len(products)} products')

            for product in products:
                try:
                    await self._check_product_price(session, product)
                except Exception as e:
                    logger.error(f'Error checking product {product.id}: {e}')

    async def _check_product_price(self, session: AsyncSession, product: Product) -> None:
        """Check price for a single product."""
        try:
            provider = self.provider_registry.get_provider(product.provider)
            if not provider:
                logger.warning(f'Provider {product.provider} not found')
                return

            product_data = await provider.fetch_product(product.url)

            # Record success
            health_monitor.record_success(product.provider)

            new_price = Decimal(str(product_data.price))
            old_price = product.last_price

            if new_price == old_price:
                return

            # Calculate price change percentage
            price_delta_percent = abs((new_price - old_price) / old_price * 100)

            # Get all trackings for this product
            result = await session.execute(
                select(Tracking, User).join(User).where(Tracking.product_id == product.id)
            )
            trackings_with_users = result.all()

            # Check if any user should be notified
            for tracking, user in trackings_with_users:
                threshold = tracking.custom_threshold_delta or settings.default_threshold_delta

                if price_delta_percent >= threshold:
                    await self._notify_user(user, product, old_price, new_price, price_delta_percent)

            # Update product price
            product.last_price = new_price
            product.updated_at = datetime.utcnow()

            # Add to price history
            from bot.models.price_history import PriceHistory

            price_history = PriceHistory(product_id=product.id, price=new_price)
            session.add(price_history)

            await session.commit()
            logger.info(f'Price updated for product {product.id}: {old_price} -> {new_price}')

        except Exception as e:
            logger.error(f'Error fetching price for product {product.id}: {e}')
            health_monitor.record_error(product.provider, str(e))
            await self._check_provider_health(product.provider)

    async def _notify_user(
        self, user: User, product: Product, old_price: Decimal, new_price: Decimal, change_percent: Decimal
    ) -> None:
        """Notify user about price change."""
        try:
            message = get_text(
                user.locale,
                'price_changed',
                title=product.title,
                old_price=old_price,
                new_price=new_price,
                currency=product.currency,
                change=f'{change_percent:.1f}',
                url=product.url,
            )
            
            # Send message first
            await self.bot.send_message(user.tg_user_id, message, parse_mode='HTML', disable_web_page_preview=True)
            
            # Try to send screenshot if available
            try:
                # Get the latest product data to check for screenshot
                provider = self.provider_registry.get_provider(product.provider)
                if provider:
                    product_data = await provider.fetch_product(product.url)
                    if hasattr(product_data, 'screenshot_path') and product_data.screenshot_path:
                        with open(product_data.screenshot_path, 'rb') as photo:
                            await self.bot.send_photo(
                                user.tg_user_id, 
                                photo, 
                                caption=f"📸 Скриншот страницы товара\n{product.title}"
                            )
                        logger.info(f'Sent screenshot to user {user.tg_user_id} for product {product.id}')
            except Exception as e:
                logger.debug(f'Could not send screenshot to user {user.tg_user_id}: {e}')
            
            logger.info(f'Notified user {user.tg_user_id} about price change for product {product.id}')
        except Exception as e:
            logger.error(f'Error notifying user {user.tg_user_id}: {e}')

    async def _check_provider_health(self, provider_enum) -> None:
        """Check provider health and send alerts if needed."""
        status = health_monitor.get_status(provider_enum)
        previous_status = health_monitor.get_previous_status(provider_enum)

        # Status changed
        if status != previous_status:
            health_monitor.set_previous_status(provider_enum, status)

            if status == ProviderStatus.DEGRADED:
                await self._send_admin_alert(provider_enum, 'provider_degraded', status)
            elif status == ProviderStatus.DOWN:
                await self._send_admin_alert(provider_enum, 'provider_down', status)
            elif status == ProviderStatus.OK and previous_status in (ProviderStatus.DEGRADED, ProviderStatus.DOWN):
                await self._send_admin_alert(provider_enum, 'provider_restored', status)

    async def _send_admin_alert(self, provider_enum, message_key: str, status: ProviderStatus) -> None:
        """Send alert to admins."""
        if not alert_manager.should_send_alert(provider_enum, status):
            logger.info(f'Alert for {provider_enum.value} suppressed due to cooldown')
            return

        admin_ids = settings.admin_ids
        if not admin_ids:
            return

        for admin_id in admin_ids:
            try:
                message = get_text('ru', message_key, provider=provider_enum.value)
                await self.bot.send_message(admin_id, message)
            except Exception as e:
                logger.error(f'Error sending alert to admin {admin_id}: {e}')

        alert_manager.record_alert(provider_enum, status)

