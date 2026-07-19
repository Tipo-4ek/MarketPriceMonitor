"""Tracking handlers (add, list, remove)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.providers import provider_registry
from bot.core.services.product_service import ProductService
from bot.core.services.tracking_service import TrackingService
from bot.models import base
from bot.utils.parsing import is_valid_url
from bot.utils.validators import validate_product_id

logger = get_logger(__name__)

router = Router()


@router.message(Command('add'))
async def cmd_add(message: Message):
    """Handle /add command."""
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer('Usage: /add <url>')
        return

    url = args[1].strip()
    await add_product(message, url)


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
            product, _ = await ProductService.get_or_create_product(session, url)
            tracking, tracking_created = await TrackingService.add_tracking(session, user, product)
            await session.commit()

            if tracking_created:
                # Refresh title/price so the confirmation shows current data.
                try:
                    provider = provider_registry.find_provider(url)
                    if provider:
                        product_data = await provider.fetch_product(url)
                        product.title = product_data.title
                        product.last_price = product_data.price
                        product.currency = product_data.currency
                        await session.commit()
                        logger.info(f'Refreshed product {product.id}: {product.title} - {product.last_price}')
                except Exception as e:
                    logger.warning(f'Could not refresh product data for {product.id}: {e}')

                text = get_text(
                    user.locale,
                    'product_added',
                    title=product.title,
                    price=product.last_price,
                    currency=product.currency,
                    product_id=product.id,
                )
                logger.info(f'User {message.from_user.id} added product {product.id}')
            else:
                text = get_text(user.locale, 'product_exists', product_id=product.id)

            await message.answer(text, parse_mode='HTML')

        except ValueError as e:
            key = 'invalid_url' if 'Unsupported URL' in str(e) else 'provider_error'
            await message.answer(get_text(user.locale, key), parse_mode='HTML')
            logger.warning(f'Error adding product for user {message.from_user.id}: {e}')

        except Exception as e:
            await message.answer(get_text(user.locale, 'provider_error'), parse_mode='HTML')
            logger.error(f'Error adding product for user {message.from_user.id}: {e}', exc_info=True)


@router.message(Command('list'))
async def cmd_list(message: Message):
    """Handle /list command."""
    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)
        trackings = await TrackingService.get_user_trackings(session, user)

        if not trackings:
            text = get_text(user.locale, 'no_tracked_products')
            await message.answer(text)
            return

        products_text = []
        for tracking, product in trackings:
            threshold = tracking.custom_threshold_delta or '(default)'
            products_text.append(
                f'<b>ID:</b> {product.id}\n'
                f'<b>📦 {product.title}</b>\n'
                f'💰 Цена: {product.last_price} {product.currency}\n'
                f'🏪 Магазин: {product.provider.value}\n'
                f'📊 Порог: {threshold}%\n'
                f'🔗 <a href="{product.url}">Ссылка на товар</a>'
            )

        text = get_text(user.locale, 'tracked_products', products='\n\n'.join(products_text))
        await message.answer(text, parse_mode='HTML', disable_web_page_preview=True)


@router.message(Command('remove'))
async def cmd_remove(message: Message):
    """Handle /remove command."""
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer('Usage: /remove <id>')
        return

    product_id = validate_product_id(args[1].strip())

    if not product_id:
        async with base.async_session_maker() as session:
            user = await TrackingService.get_or_create_user(session, message.from_user.id)
            text = get_text(user.locale, 'invalid_product_id')
            await message.answer(text)
        return

    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)
        removed = await TrackingService.remove_tracking(session, user, product_id)
        await session.commit()

        if removed:
            text = get_text(user.locale, 'product_removed')
            logger.info(f'User {message.from_user.id} removed product {product_id}')
        else:
            text = get_text(user.locale, 'product_not_found')

        await message.answer(text)
