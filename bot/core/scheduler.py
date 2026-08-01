"""Background scheduler for price polling."""

import asyncio
import contextlib
import re
from dataclasses import dataclass
from decimal import Decimal
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.alerts import alert_manager
from bot.core.config import settings
from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.providers.base import ProductData, ProviderError
from bot.core.providers.health import health_monitor
from bot.models import PriceHistory, Product, Tracking, User, base
from bot.models.enums import ProviderEnum, ProviderStatus

logger = get_logger(__name__)

# How many cycles a DOWN provider is skipped before it is polled again to probe.
_DOWN_BACKOFF_CYCLES = 3

# Money is stored as Numeric(12, 2); prices are quantised to that scale before
# being compared or written, so a shop that reports 661.004 does not write a new
# history row every cycle for a value that rounds to the same stored 661.00.
_MONEY_QUANTUM = Decimal('0.01')

# The fallback shape a provider returns when it read a price but no name, e.g.
# "Wildberries 219279898". A poll must never overwrite a real stored title with
# one of these.
_FALLBACK_TITLE_RE = re.compile(r'^[A-Za-z]+ \d+$')


@dataclass(frozen=True)
class _Notification:
    """Everything one price-change message needs, captured before the commit.

    The ORM objects are expired by ``session.commit()``; snapshotting the plain
    values here lets the messages be sent after the transaction closes without a
    lazy load firing MissingGreenlet.
    """

    tg_user_id: int
    locale: str
    title: str
    currency: str
    url: str
    old_price: Decimal
    new_price: Decimal
    change_percent: Decimal


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

        A provider is left alone for ``_DOWN_BACKOFF_CYCLES`` after it goes DOWN.
        Hammering a marketplace that is actively refusing us is both the fastest
        way to stay refused and the rudest thing this bot can do.

        The backoff is a pure countdown decremented here and armed/cleared in
        :meth:`_check_product_price` on the poll result — not a re-read of the
        health status. Skipping a DOWN provider records no new errors, so its
        window drains and the status decays to DEGRADED on its own; gating on the
        status would re-poll it early. When the countdown reaches zero the
        provider is polled once to probe whether the refusal has lifted; a
        success clears the countdown, a failure re-arms it.
        """
        pollable = set()
        for provider in ProviderEnum:
            penalty = self._down_cycles.get(provider, 0)
            if penalty > 0:
                self._down_cycles[provider] = penalty - 1
                logger.info(
                    'Skipping a provider in DOWN backoff',
                    extra={'provider': provider.value, 'cycles_left': penalty - 1},
                )
                continue
            pollable.add(provider)
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
            # of the cycle. The per-product guard is a second layer of the same
            # promise: one product that raises must not end the cycle for the
            # rest.
            try:
                async with base.async_session_maker() as session:
                    product = await session.get(Product, product_id)
                    if product is not None:
                        await self._check_product_price(session, product)
            except Exception:
                logger.exception('Price check failed for a product', extra={'product_id': product_id})

    async def _check_product_price(self, session: AsyncSession, product: Product) -> None:
        """Fetch one product's price, persist a change and notify its trackers."""
        # Read the identity now, while the instance is live. Anything read after
        # a rollback below would trigger a lazy load on an expired object and
        # raise MissingGreenlet from inside the error handler.
        product_id = product.id
        provider_enum = product.provider

        provider = self.provider_registry.get_provider(provider_enum)
        if not provider:
            logger.warning('No provider registered', extra={'provider': provider_enum.value})
            return

        try:
            product_data = await provider.fetch_product(product.url)
        except ProviderError as exc:
            # Only a provider-level failure — the shop refusing us, or the page
            # no longer carrying a price — reflects marketplace health. A bug in
            # our own code must not drive a provider to DOWN.
            logger.warning(
                'Price fetch failed',
                extra={'product_id': product_id, 'provider': provider_enum.value, 'error': str(exc)},
            )
            health_monitor.record_error(provider_enum, str(exc))
            await self._check_provider_health(provider_enum)
            # Arm the poll backoff the moment a provider is DOWN, so the next
            # cycles skip it instead of hammering a marketplace that is refusing
            # us. A later probe that fails re-arms it here again.
            if health_monitor.get_status(provider_enum) is ProviderStatus.DOWN:
                self._down_cycles[provider_enum] = _DOWN_BACKOFF_CYCLES
            return
        except Exception:
            logger.exception(
                'Unexpected error fetching a price',
                extra={'product_id': product_id, 'provider': provider_enum.value},
            )
            return

        health_monitor.record_success(provider_enum)
        # A successful poll lifts any backoff: the provider answered.
        self._down_cycles.pop(provider_enum, None)
        # Health is evaluated on success too, otherwise the OK transition never
        # fires and the "provider restored" alert is unreachable.
        await self._check_provider_health(provider_enum)

        try:
            await self._apply_price(session, product, product_data)
        except Exception:
            await session.rollback()
            logger.exception('Failed to record price', extra={'product_id': product_id})

    async def _apply_price(self, session: AsyncSession, product: Product, product_data: ProductData) -> None:
        """Persist a new price and notify trackers whose threshold was crossed.

        The write is committed before anyone is notified. Notifying first and
        committing after means a failed commit leaves users told about a move
        that was never stored — and re-announced every cycle, since the stored
        price never advanced. So the recipients are collected inside the
        transaction, the transaction is committed, and only then are the
        messages sent, outside it.
        """
        new_price = Decimal(product_data.price).quantize(_MONEY_QUANTUM)
        old_price = product.last_price

        # Upgrade a title that is still the fallback shape ("Wildberries
        # 219279898") to a real name a later poll managed to read. Only ever in
        # that direction: a real stored title is never overwritten, so a
        # transient fallback cannot clobber a good name.
        if (
            _FALLBACK_TITLE_RE.match(product.title)
            and product_data.title
            and not _FALLBACK_TITLE_RE.match(product_data.title)
        ):
            product.title = product_data.title

        if new_price == old_price:
            await session.commit()
            return

        # `updated_at` carries an onupdate= default, so the flush stamps it.
        product.last_price = new_price
        session.add(PriceHistory(product_id=product.id, price=new_price))

        # A zero previous price makes the relative change meaningless (and would
        # divide by zero); treat any move away from it as worth reporting.
        delta_percent = abs((new_price - old_price) / old_price * 100) if old_price else Decimal(100)

        result = await session.execute(select(Tracking, User).join(User).where(Tracking.product_id == product.id))
        recipients = [
            _Notification(
                tg_user_id=user.tg_user_id,
                locale=user.locale,
                title=product.title,
                currency=product.currency,
                url=product.url,
                old_price=old_price,
                new_price=new_price,
                change_percent=delta_percent,
            )
            for tracking, user in result.all()
            if delta_percent >= (tracking.custom_threshold_delta or settings.default_threshold_delta)
        ]

        await session.commit()
        logger.info(
            'Price updated',
            extra={'product_id': product.id, 'old_price': str(old_price), 'new_price': str(new_price)},
        )

        for recipient in recipients:
            await self._notify_user(recipient)

    async def _notify_user(self, note: '_Notification') -> None:
        """Send one price-change message, built from values captured pre-commit."""
        # Title, currency and URL come from a marketplace page and go into a
        # parse_mode='HTML' message: a '&' or '<' in a product name makes
        # Telegram reject the whole notification. Rendering happens outside the
        # try so a formatting bug surfaces as an error rather than a lost alert.
        message = get_text(
            note.locale,
            'price_changed',
            title=escape(note.title),
            old_price=note.old_price,
            new_price=note.new_price,
            currency=escape(note.currency),
            change=f'{note.change_percent:.1f}',
            url=escape(note.url, quote=True),
        )
        try:
            await self.bot.send_message(note.tg_user_id, message, parse_mode='HTML', disable_web_page_preview=True)
            logger.info('Notified user', extra={'tg_user_id': note.tg_user_id})
        except TelegramAPIError as exc:
            logger.warning('Could not notify user', extra={'tg_user_id': note.tg_user_id, 'error': str(exc)})

    async def _check_provider_health(self, provider: ProviderEnum) -> None:
        """Alert admins when a provider's health status changes."""
        status = health_monitor.get_status(provider)
        previous_status = health_monitor.get_previous_status(provider)

        if status == previous_status:
            return

        message_key = {
            ProviderStatus.DEGRADED: 'provider_degraded',
            ProviderStatus.DOWN: 'provider_down',
        }.get(status)
        if status is ProviderStatus.OK and previous_status in (ProviderStatus.DEGRADED, ProviderStatus.DOWN):
            message_key = 'provider_restored'

        # Only record the transition as reported once the alert is actually
        # handled (delivered, or legitimately suppressed by cooldown / no
        # admins). Advancing it after a failed send would swallow the transition
        # and never retry — the admin would never hear about the outage.
        handled = True
        if message_key is not None:
            handled = await self._send_admin_alert(provider, message_key, status)

        if handled:
            health_monitor.set_previous_status(provider, status)

    async def _send_admin_alert(self, provider: ProviderEnum, message_key: str, status: ProviderStatus) -> bool:
        """Alert every admin. Return whether the transition can be marked handled.

        True means delivered, suppressed by cooldown, or there is nobody to
        alert; False means every send failed and the caller should retry.
        """
        if not alert_manager.should_send_alert(provider, status):
            logger.info('Alert suppressed by cooldown', extra={'provider': provider.value, 'status': status.value})
            return True

        admin_ids = settings.admin_ids
        if not admin_ids:
            return True

        delivered = False
        for admin_id in admin_ids:
            try:
                message = get_text(settings.default_locale, message_key, provider=provider.value)
                await self.bot.send_message(admin_id, message)
                delivered = True
            except TelegramAPIError as exc:
                logger.warning('Could not alert admin', extra={'admin_id': admin_id, 'error': str(exc)})

        # Arm the 24h cooldown only if at least one admin actually got the alert;
        # otherwise a transient outage would silence the alert for a full day.
        if delivered:
            alert_manager.record_alert(provider, status)
        return delivered
