"""Small shared lookups the handlers need before they can answer.

Every handler needs the user's locale, and several need the list of products they
track in order to offer them as buttons. Both open and commit their own session:
`get_or_create_user` only flushes, so without a commit a first-time user is
rolled back and re-created on the next message.
"""

from bot.core.services.tracking_service import TrackingService
from bot.models import base


async def user_locale(tg_user_id: int) -> str:
    """The user's language, creating the user row on first contact."""
    async with base.new_session() as session:
        user = await TrackingService.get_or_create_user(session, tg_user_id)
        await session.commit()
        return user.locale


async def tracked_labels(tg_user_id: int) -> dict[int, str]:
    """Product id -> short button label, for the product pickers."""
    async with base.new_session() as session:
        user = await TrackingService.get_or_create_user(session, tg_user_id)
        trackings = await TrackingService.get_user_trackings(session, user)
        await session.commit()

        labels = {}
        for _tracking, product in trackings:
            # Telegram button labels are one line and get truncated on narrow
            # screens, so the id goes first and the title is clipped.
            title = product.title if len(product.title) <= 28 else f'{product.title[:27]}…'
            labels[product.id] = f'#{product.id} {title}'
        return labels
