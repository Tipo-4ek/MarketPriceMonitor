"""Admin access control middleware."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from bot.core.config import settings


class AdminACL(BaseMiddleware):
    """Middleware to add admin flag to context."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Check if user is admin and add flag to data."""
        user: User | None = data.get('event_from_user')

        if user:
            data['is_admin'] = user.id in settings.admin_ids
        else:
            data['is_admin'] = False

        return await handler(event, data)


