"""Monitor handlers (per-product threshold configuration).

Only `/monitor set` exists. The deployment-wide default lives in
DEFAULT_THRESHOLD_DELTA; there is deliberately no `/monitor default`, because
nothing stores a per-user default, and a command that accepts a value, discards
it and reports success is worse than no command at all.
"""

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.core.i18n import get_text
from bot.core.logging import get_logger
from bot.core.services.tracking_service import TrackingService
from bot.models import base
from bot.utils.validators import validate_product_id, validate_threshold

logger = get_logger(__name__)

router = Router()

_USAGE = 'Usage: /monitor set <id> <delta>'


@router.message(Command('monitor'))
async def cmd_monitor(message: Message, command: CommandObject):
    """Handle /monitor set <id> <delta>."""
    args = (command.args or '').split()

    if len(args) != 3 or args[0].lower() != 'set':
        await message.answer(_USAGE)
        return

    product_id = validate_product_id(args[1])
    threshold = validate_threshold(args[2])

    async with base.async_session_maker() as session:
        user = await TrackingService.get_or_create_user(session, message.from_user.id)

        if not product_id or not threshold:
            await session.commit()
            await message.answer(get_text(user.locale, 'invalid_threshold'))
            return

        tracking = await TrackingService.update_tracking_threshold(session, user, product_id, threshold)
        await session.commit()

        if tracking:
            text = get_text(user.locale, 'custom_threshold_set', product_id=product_id, delta=threshold)
            logger.info(
                'Threshold set',
                extra={'tg_user_id': message.from_user.id, 'product_id': product_id, 'threshold': threshold},
            )
        else:
            text = get_text(user.locale, 'product_not_found')

        await message.answer(text)
