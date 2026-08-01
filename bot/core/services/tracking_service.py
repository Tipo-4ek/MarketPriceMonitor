"""Tracking service for managing user-product tracking."""

from collections.abc import Sequence

from sqlalchemy import Row, delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.logging import get_logger
from bot.models import Product, Tracking, User

logger = get_logger(__name__)


class TrackingService:
    """Service for tracking operations."""

    @staticmethod
    async def get_or_create_user(session: AsyncSession, tg_user_id: int, locale: str = 'ru') -> User:
        """Get or create user."""
        result = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(tg_user_id=tg_user_id, locale=locale)
            session.add(user)
            await session.flush()
            logger.info('Created user', extra={'tg_user_id': tg_user_id})

        return user

    @staticmethod
    async def add_tracking(
        session: AsyncSession, user: User, product: Product, custom_threshold: int | None = None
    ) -> tuple[Tracking, bool]:
        """Add tracking for user and product.

        Returns a ``(tracking, created)`` pair; ``created`` is True only when a
        new row was inserted. The ``uq_tracking_user_product`` constraint makes
        this idempotent under concurrency: two simultaneous /add for the same
        pair cannot both insert, so a user is never notified twice for one move.
        """
        result = await session.execute(
            select(Tracking).where(Tracking.user_id == user.id, Tracking.product_id == product.id)
        )
        existing_tracking = result.scalar_one_or_none()

        if existing_tracking:
            return existing_tracking, False

        tracking = Tracking(user_id=user.id, product_id=product.id, custom_threshold_delta=custom_threshold)
        session.add(tracking)
        await session.flush()

        logger.info('Created tracking', extra={'tg_user_id': user.tg_user_id, 'product_id': product.id})
        return tracking, True

    @staticmethod
    async def get_user_trackings(session: AsyncSession, user: User) -> Sequence[Row[tuple[Tracking, Product]]]:
        """Get all trackings for user with product details, oldest first."""
        result = await session.execute(
            select(Tracking, Product).join(Product).where(Tracking.user_id == user.id).order_by(Tracking.created_at)
        )
        return result.all()

    @staticmethod
    async def remove_tracking(session: AsyncSession, user: User, product_id: int) -> bool:
        """Remove tracking by product ID. Returns True if a row was removed."""
        result = await session.execute(
            delete(Tracking).where(Tracking.user_id == user.id, Tracking.product_id == product_id)
        )
        await session.flush()
        # execute() of a DELETE returns a CursorResult, which carries rowcount.
        return isinstance(result, CursorResult) and result.rowcount > 0

    @staticmethod
    async def update_tracking_threshold(
        session: AsyncSession, user: User, product_id: int, threshold: int
    ) -> Tracking | None:
        """Update custom threshold for tracking."""
        result = await session.execute(
            select(Tracking).where(Tracking.user_id == user.id, Tracking.product_id == product_id)
        )
        tracking = result.scalar_one_or_none()

        if tracking:
            tracking.custom_threshold_delta = threshold
            await session.flush()
            logger.info(
                'Updated tracking threshold',
                extra={'tg_user_id': user.tg_user_id, 'product_id': product_id, 'threshold': threshold},
            )

        return tracking

    @staticmethod
    async def update_user_locale(session: AsyncSession, user: User, locale: str) -> None:
        """Update user locale."""
        user.locale = locale
        await session.flush()
        logger.info('Updated user locale', extra={'tg_user_id': user.tg_user_id, 'locale': locale})
