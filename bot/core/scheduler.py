"""Background scheduler for price polling."""

import asyncio
import contextlib
from decimal import Decimal
from html import escape

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.alerts import alert_manager
from bot.core.config import settings
from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.providers.health import health_monitor
from bot.models import PriceHistory, Product, Tracking, User, base
from bot.models.enums import ProviderEnum, ProviderStatus

logger = get_logger(__name__)

# How many cycles a DOWN provider is left alone before it is tried again.
_DOWN_BACKOFF_CYCLES = 4


class PriceScheduler:
    """Poll every tracked product on an interval and notify on price moves."""

    def __init__(self, bot: Bot, provider_registry):
        self.bot = bot
        self.provider_registry = provider_registry
        self._stop = asyncio.Event()
        self._down_cycles: dict[ProviderEnum, int] = {}

    async def start(self) -> None:
        """Run the polling loop until :meth:`stop` is called."""
        self._stop.clear()
        logger.info('Price scheduler started', extra={'interval_seconds': settings.poll_interval_seconds})
        await self._run_loop()

    async def stop(self) -> None:
        """Ask the loop to finish; it wakes from its sleep immediately."""
        self._stop.set()
        logger.info('Price scheduler stopping')

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._check_prices()
            except Exception:
                logger.exception('Scheduler cycle failed')

            # An interruptible sleep. A bare asyncio.sleep(poll_interval) would
            # leave shutdown blocked for up to a full interval (15 min by
            # default), which reads as a hung process to whatever supervises us.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=settings.poll_interval_seconds)

        logger.info('Price scheduler stopped')

    def _pollable_providers(self) -> set[ProviderEnum]:
        """Decide which marketplaces to contact this cycle.

        A provider the health monitor has marked DOWN is left alone for a few
        cycles. Hammering a marketplace that is actively refusing us is both the
        fastest way to stay refused and the rudest thing this bot can do.
        """
        pollable = set()
        for provider in ProviderEnum:
            if health_monitor.get_status(provider) is not ProviderStatus.DOWN:
                self._down_cycles.pop(provider, None)
                pollable.add(provider)
                continue

            waited = self._down_cycles.get(provider, 0) + 1
            if waited >= _DOWN_BACKOFF_CYCLES:
                self._down_cycles[provider] = 0
                pollable.add(provider)
            else:
                self._down_cycles[provider] = waited
                logger.info(
                    'Skipping a provider that is down',
                    extra={'provider': provider.value, 'cycles_waited': waited},
                )
        return pollable

    async def _check_prices(self) -> None:
        """Check prices for all tracked products."""
        if not base.async_session_maker:
            return

        pollable = self._pollable_providers()

        async with base.async_session_maker() as session:
            # Only products somebody still tracks. `/remove` deletes the
            # tracking and leaves the product row, so a plain select(Product)
            # would keep scraping items nobody asked about.
            result = await session.execute(
                select(Product.id).join(Tracking).where(Product.provider.in_(pollable)).distinct()
            )
            product_ids = list(result.scalars().all())

        logger.info('Checking prices', extra={'product_count': len(product_ids)})

        for product_id in product_ids:
            if self._stop.is_set():
                return
            # One session per product. Sharing a session means a rollback for
            # one product expires every other object in it, and the next
            # attribute read raises MissingGreenlet — silently skipping the rest
            # of the cycle.
            async with base.async_session_maker() as session:
                product = await session.get(Product, product_id)
                if product is not None:
                    await self._check_product_price(session, product)

    async def _check_product_price(self, session: AsyncSession, product: Product) -> None:
        """Fetch one product's price, persist a change and notify its trackers."""
        provider = self.provider_registry.get_provider(product.provider)
        if not provider:
            logger.warning('No provider registered', extra={'provider': product.provider.value})
            return

        try:
            product_data = await provider.fetch_product(product.url)
        except Exception as exc:
            logger.warning(
                'Price fetch failed',
                extra={'product_id': product.id, 'provider': product.provider.value, 'error': str(exc)},
            )
            health_monitor.record_error(product.provider, str(exc))
            await self._check_provider_health(product.provider)
            return

        health_monitor.record_success(product.provider)
        # Health is evaluated on success too, otherwise the OK transition never
        # fires and the "provider restored" alert is unreachable.
        await self._check_provider_health(product.provider)

        try:
            await self._apply_price(session, product, Decimal(str(product_data.price)))
        except Exception:
            await session.rollback()
            logger.exception('Failed to record price', extra={'product_id': product.id})

    async def _apply_price(self, session: AsyncSession, product: Product, new_price: Decimal) -> None:
        """Persist a new price and notify trackers whose threshold was crossed."""
        old_price = product.last_price
        if new_price == old_price:
            return

        # `updated_at` carries an onupdate= default, so the flush stamps it.
        product.last_price = new_price
        session.add(PriceHistory(product_id=product.id, price=new_price))

        # A zero previous price makes the relative change meaningless (and would
        # divide by zero); treat any move away from it as worth reporting.
        delta_percent = abs((new_price - old_price) / old_price * 100) if old_price else Decimal(100)

        result = await session.execute(select(Tracking, User).join(User).where(Tracking.product_id == product.id))
        for tracking, user in result.all():
            threshold = tracking.custom_threshold_delta or settings.default_threshold_delta
            if delta_percent >= threshold:
                await self._notify_user(user, product, old_price, new_price, delta_percent)

        await session.commit()
        logger.info(
            'Price updated',
            extra={'product_id': product.id, 'old_price': str(old_price), 'new_price': str(new_price)},
        )

    async def _notify_user(
        self, user: User, product: Product, old_price: Decimal, new_price: Decimal, change_percent: Decimal
    ) -> None:
        """Notify user about price change."""
        try:
            message = get_text(
                user.locale,
                'price_changed',
                # Title, currency and URL come from a marketplace page and go
                # into a parse_mode='HTML' message: a '&' or '<' in a product
                # name makes Telegram reject the whole notification.
                title=escape(product.title),
                old_price=old_price,
                new_price=new_price,
                currency=escape(product.currency),
                change=f'{change_percent:.1f}',
                url=escape(product.url, quote=True),
            )
            await self.bot.send_message(user.tg_user_id, message, parse_mode='HTML', disable_web_page_preview=True)
            logger.info('Notified user', extra={'tg_user_id': user.tg_user_id, 'product_id': product.id})
        except Exception as exc:
            logger.warning('Could not notify user', extra={'tg_user_id': user.tg_user_id, 'error': str(exc)})

    async def _check_provider_health(self, provider: ProviderEnum) -> None:
        """Alert admins when a provider's health status changes."""
        status = health_monitor.get_status(provider)
        previous_status = health_monitor.get_previous_status(provider)

        if status == previous_status:
            return

        health_monitor.set_previous_status(provider, status)

        if status == ProviderStatus.DEGRADED:
            await self._send_admin_alert(provider, 'provider_degraded', status)
        elif status == ProviderStatus.DOWN:
            await self._send_admin_alert(provider, 'provider_down', status)
        elif status == ProviderStatus.OK and previous_status in (ProviderStatus.DEGRADED, ProviderStatus.DOWN):
            await self._send_admin_alert(provider, 'provider_restored', status)

    async def _send_admin_alert(self, provider: ProviderEnum, message_key: str, status: ProviderStatus) -> None:
        """Send alert to admins."""
        if not alert_manager.should_send_alert(provider, status):
            logger.info('Alert suppressed by cooldown', extra={'provider': provider.value, 'status': status.value})
            return

        admin_ids = settings.admin_ids
        if not admin_ids:
            return

        for admin_id in admin_ids:
            try:
                message = get_text(settings.default_locale, message_key, provider=provider.value)
                await self.bot.send_message(admin_id, message)
            except Exception as exc:
                logger.warning('Could not alert admin', extra={'admin_id': admin_id, 'error': str(exc)})

        alert_manager.record_alert(provider, status)
