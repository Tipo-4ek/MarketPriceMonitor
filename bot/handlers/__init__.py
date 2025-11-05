"""Handlers package."""
from aiogram import Dispatcher

from bot.core.middlewares.admin_acl import AdminACL
from bot.handlers import admin, common, monitor, tracking


def setup_handlers(dp: Dispatcher) -> None:
    """Setup all handlers and middlewares."""
    # Register middlewares
    dp.message.middleware(AdminACL())

    # Register routers
    dp.include_router(common.router)
    dp.include_router(tracking.router)
    dp.include_router(monitor.router)
    dp.include_router(admin.router)


