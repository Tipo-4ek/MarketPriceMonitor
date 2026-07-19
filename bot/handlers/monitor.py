"""Monitor handlers (threshold configuration)."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.core.config import settings
from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.services.tracking_service import TrackingService
from bot.models import base
from bot.utils.validators import validate_product_id, validate_threshold

logger = get_logger(__name__)

router = Router()


@router.message(Command('monitor'))
async def cmd_monitor(message: Message):
    """Handle /monitor command."""
    args = message.text.split()

    if len(args) < 3:
        await message.answer('Usage: /monitor default <delta> OR /monitor set <id> <delta>')
        return

    subcommand = args[1].lower()

    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)

        if subcommand == 'default':
            # Set default threshold
            threshold = validate_threshold(args[2])

            if not threshold:
                text = get_text(user.locale, 'invalid_threshold')
                await message.answer(text)
                return

            # Note: Default threshold is global, stored in config/env
            # We can't change it per-user in this implementation
            # Just inform the user of current default
            text = get_text(user.locale, 'default_threshold_set', delta=settings.default_threshold_delta)
            await message.answer(text)

        elif subcommand == 'set':
            if len(args) < 4:
                await message.answer('Usage: /monitor set <id> <delta>')
                return

            product_id = validate_product_id(args[2])
            threshold = validate_threshold(args[3])

            if not product_id or not threshold:
                text = get_text(user.locale, 'invalid_threshold')
                await message.answer(text)
                return

            # Update custom threshold for tracking
            tracking = await TrackingService.update_tracking_threshold(session, user, product_id, threshold)
            await session.commit()

            if tracking:
                text = get_text(user.locale, 'custom_threshold_set', product_id=product_id, delta=threshold)
                logger.info(f'User {message.from_user.id} set threshold {threshold}% for product {product_id}')
            else:
                text = get_text(user.locale, 'product_not_found')

            await message.answer(text)

        else:
            await message.answer('Usage: /monitor default <delta> OR /monitor set <id> <delta>')
