"""Tracking handlers (add, list, remove)."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.providers.base import (
    PriceNotFoundError,
    ProviderBlockedError,
    ProviderError,
    UnsupportedURLError,
)
from bot.core.services.product_service import ProductService
from bot.core.services.tracking_service import TrackingService
from bot.models import base
from bot.utils.parsing import is_valid_url
from bot.utils.validators import validate_product_id

logger = get_logger(__name__)

router = Router()


@router.message(Command('add'))
async def cmd_add(message: Message, command: CommandObject):
    """Handle /add command."""
    # CommandObject.args rather than message.text.split(): aiogram matches a
    # command in a media caption too, where message.text is None.
    if not command.args:
        await message.answer('Usage: /add <url>')
        return

    await add_product(message, command.args.strip())


@router.message(F.text.regexp(r'https?://'))
async def handle_url(message: Message):
    """Handle URL messages without command."""
    url = message.text.strip()
    if is_valid_url(url):
        await add_product(message, url)


async def add_product(message: Message, url: str):
    """Add product for tracking."""
    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)

        try:
            # get_or_create_product already fetches title and price for a new
            # product; refetching here would mean two browser renders per /add.
            product, _ = await ProductService.get_or_create_product(session, url)
            _tracking, tracking_created = await TrackingService.add_tracking(session, user, product)
            await session.commit()

            if tracking_created:
                text = get_text(
                    user.locale,
                    'product_added',
                    title=escape(product.title),
                    price=product.last_price,
                    currency=escape(product.currency),
                    product_id=product.id,
                )
                logger.info('Product added', extra={'tg_user_id': message.from_user.id, 'product_id': product.id})
            else:
                text = get_text(user.locale, 'product_exists', product_id=product.id)

            await message.answer(text, parse_mode='HTML')

        except ProviderError as exc:
            # Each failure mode gets its own message: "try again later" for a
            # blocked marketplace is true, for an unsupported link it is a lie.
            key = {
                UnsupportedURLError: 'invalid_url',
                ProviderBlockedError: 'provider_blocked',
                PriceNotFoundError: 'price_not_found',
            }.get(type(exc), 'provider_error')
            await message.answer(get_text(user.locale, key))
            logger.info(
                'Could not add product',
                extra={
                    'tg_user_id': message.from_user.id,
                    'url': url,
                    'reason': type(exc).__name__,
                    'error': str(exc),
                },
            )

        except Exception:
            await message.answer(get_text(user.locale, 'provider_error'))
            logger.exception('Error adding product', extra={'tg_user_id': message.from_user.id, 'url': url})


@router.message(Command('list'))
async def cmd_list(message: Message):
    """Handle /list command."""
    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)
        trackings = await TrackingService.get_user_trackings(session, user)
        await session.commit()

        if not trackings:
            await message.answer(get_text(user.locale, 'no_tracked_products'))
            return

        entries = []
        for tracking, product in trackings:
            threshold = (
                f'{tracking.custom_threshold_delta}%'
                if tracking.custom_threshold_delta
                else get_text(user.locale, 'threshold_default')
            )
            entries.append(
                get_text(
                    user.locale,
                    'tracked_product_entry',
                    product_id=product.id,
                    # Titles come from the marketplace page, so they are escaped
                    # before going anywhere near parse_mode='HTML'.
                    title=escape(product.title),
                    price=product.last_price,
                    currency=escape(product.currency),
                    provider=product.provider.value,
                    threshold=threshold,
                    url=escape(product.url, quote=True),
                )
            )

        text = get_text(user.locale, 'tracked_products', products='\n\n'.join(entries))
        await message.answer(text, parse_mode='HTML', disable_web_page_preview=True)


@router.message(Command('remove'))
async def cmd_remove(message: Message, command: CommandObject):
    """Handle /remove command."""
    if not command.args:
        await message.answer('Usage: /remove <id>')
        return

    product_id = validate_product_id(command.args.strip())

    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)

        if not product_id:
            await session.commit()
            await message.answer(get_text(user.locale, 'invalid_product_id'))
            return

        removed = await TrackingService.remove_tracking(session, user, product_id)
        await session.commit()

        if removed:
            text = get_text(user.locale, 'product_removed')
            logger.info('Product removed', extra={'tg_user_id': message.from_user.id, 'product_id': product_id})
        else:
            text = get_text(user.locale, 'product_not_found')

        await message.answer(text)
