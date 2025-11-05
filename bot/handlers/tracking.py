"""Tracking handlers (add, list, remove)."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.core.i18n import get_text
from bot.core.logging import get_logger
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
            # Get or create product
            product, product_created = await ProductService.get_or_create_product(session, url)

            # Add tracking
            tracking, tracking_created = await TrackingService.add_tracking(session, user, product)

            await session.commit()

            if tracking_created:
                # Get fresh product data to ensure we have the latest title and price
                try:
                    from bot.core.providers import provider_registry
                    provider = provider_registry.find_provider(url)
                    if provider:
                        product_data = await provider.fetch_product(url)
                        # Update product with fresh data
                        product.title = product_data.title
                        product.last_price = product_data.price
                        product.currency = product_data.currency
                        await session.commit()
                        logger.info(f'Updated product {product.id} with fresh data: {product.title} - {product.last_price} {product.currency}')
                except Exception as e:
                    logger.warning(f'Could not fetch fresh product data for {product.id}: {e}')
                
                text = get_text(
                    user.locale,
                    'product_added',
                    title=product.title,
                    price=product.last_price,
                    currency=product.currency,
                    product_id=product.id,
                )
                logger.info(f'User {message.from_user.id} added product {product.id}')
                
                # Try to send screenshots if available
                try:
                    if provider and hasattr(product_data, 'screenshot_path') and product_data.screenshot_path:
                        with open(product_data.screenshot_path, 'rb') as photo:
                            await message.answer_photo(
                                photo, 
                                caption=f"📸 Скриншот страницы товара\n\n<b>{product.title}</b>\n💰 Цена: {product.last_price} {product.currency}",
                                parse_mode='HTML'
                            )
                            logger.info(f'Sent screenshot to user {message.from_user.id} for new product {product.id}')
                    
                    # Send additional screenshots if available in debug_info
                    if hasattr(product_data, 'debug_info') and product_data.debug_info:
                        screenshots = product_data.debug_info.get('screenshots_taken', [])
                        for screenshot_path in screenshots:
                            if screenshot_path != product_data.screenshot_path:  # Don't send the same screenshot twice
                                try:
                                    with open(screenshot_path, 'rb') as photo:
                                        await message.answer_photo(
                                            photo, 
                                            caption=f"📸 Дополнительный скриншот: {screenshot_path.split('/')[-1]}",
                                            parse_mode='HTML'
                                        )
                                        logger.info(f'Sent additional screenshot {screenshot_path} to user {message.from_user.id}')
                                except Exception as e:
                                    logger.debug(f'Could not send additional screenshot {screenshot_path}: {e}')
                except Exception as e:
                    logger.debug(f'Could not send screenshot to user {message.from_user.id}: {e}')
            else:
                text = get_text(user.locale, 'product_exists', product_id=product.id)

            await message.answer(text, parse_mode='HTML')

        except ValueError as e:
            error_msg = str(e)
            if 'Unsupported URL' in error_msg:
                text = get_text(user.locale, 'invalid_url')
            else:
                text = get_text(user.locale, 'provider_error') + f'\n\n<i>Детали: {error_msg}</i>'
            await message.answer(text, parse_mode='HTML')
            logger.warning(f'Error adding product for user {message.from_user.id}: {e}')

        except Exception as e:
            error_msg = str(e)
            
            # Try to send error screenshots if available
            try:
                error_screenshots = [
                    '/tmp/ozon_main_page_failed.png',
                    '/tmp/ozon_blocked_page.png',
                    '/tmp/ozon_error.png',
                    '/tmp/ozon_no_price_*.png'
                ]
                
                screenshots_sent = 0
                for screenshot_pattern in error_screenshots:
                    if '*' in screenshot_pattern:
                        # Handle wildcard patterns
                        import glob
                        matching_files = glob.glob(screenshot_pattern)
                        for screenshot_path in matching_files:
                            try:
                                with open(screenshot_path, 'rb') as photo:
                                    await message.answer_photo(
                                        photo, 
                                        caption=f"🚨 Скриншот ошибки: {screenshot_path.split('/')[-1]}\n\n<i>Ошибка: {error_msg}</i>",
                                        parse_mode='HTML'
                                    )
                                    screenshots_sent += 1
                                    logger.info(f'Sent error screenshot {screenshot_path} to user {message.from_user.id}')
                            except Exception:
                                continue
                    else:
                        # Handle exact file paths
                        try:
                            with open(screenshot_pattern, 'rb') as photo:
                                await message.answer_photo(
                                    photo, 
                                    caption=f"🚨 Скриншот ошибки: {screenshot_pattern.split('/')[-1]}\n\n<i>Ошибка: {error_msg}</i>",
                                    parse_mode='HTML'
                                )
                                screenshots_sent += 1
                                logger.info(f'Sent error screenshot {screenshot_pattern} to user {message.from_user.id}')
                        except Exception:
                            continue
                
                if screenshots_sent > 0:
                    logger.info(f'Sent {screenshots_sent} error screenshots to user {message.from_user.id}')
                    
            except Exception as screenshot_error:
                logger.debug(f'Could not send error screenshots: {screenshot_error}')
            
            # Provide more user-friendly error messages
            if 'Page did not load properly' in error_msg:
                user_msg = 'Страница товара не загрузилась. Попробуйте позже или проверьте ссылку.'
            elif 'Ozon blocked the request' in error_msg:
                user_msg = 'Ozon заблокировал запрос. Попробуйте через несколько минут.'
            elif 'All methods failed' in error_msg:
                user_msg = 'Не удалось получить данные о товаре. Возможно, сайт временно недоступен.'
            else:
                user_msg = f'Ошибка: {error_msg}'
            
            text = get_text(user.locale, 'provider_error') + f'\n\n<i>{user_msg}</i>'
            await message.answer(text, parse_mode='HTML')
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

        # Build product list
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

