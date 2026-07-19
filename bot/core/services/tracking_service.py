"""Tracking service for managing user-product tracking."""

from sqlalchemy import delete, select
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
            logger.info(f'Created user: {tg_user_id}')

        return user

    @staticmethod
    async def add_tracking(
        session: AsyncSession, user: User, product: Product, custom_threshold: int | None = None
    ) -> tuple[Tracking, bool]:
        """Add tracking for user and product.

        Returns:
            Tuple of (tracking, created) where created is True if tracking was newly created.
        """
        # Check if tracking exists
        result = await session.execute(
            select(Tracking).where(Tracking.user_id == user.id, Tracking.product_id == product.id)
        )
        existing_tracking = result.scalar_one_or_none()

        if existing_tracking:
            return existing_tracking, False

        # Create new tracking
        tracking = Tracking(user_id=user.id, product_id=product.id, custom_threshold_delta=custom_threshold)

        session.add(tracking)
        await session.flush()

        logger.info(f'Created tracking: user={user.tg_user_id}, product={product.id}')
        return tracking, True

    @staticmethod
    async def get_user_trackings(session: AsyncSession, user: User) -> list[tuple[Tracking, Product]]:
        """Get all trackings for user with product details."""
        result = await session.execute(
            select(Tracking, Product).join(Product).where(Tracking.user_id == user.id).order_by(Tracking.created_at)
        )
        return result.all()

    @staticmethod
    async def remove_tracking(session: AsyncSession, user: User, product_id: int) -> bool:
        """Remove tracking by product ID.

        Returns:
            True if tracking was removed, False if not found.
        """
        result = await session.execute(
            delete(Tracking).where(Tracking.user_id == user.id, Tracking.product_id == product_id)
        )
        await session.flush()
        return result.rowcount > 0

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
                f'Updated threshold for tracking: user={user.tg_user_id}, product={product_id}, threshold={threshold}'
            )

        return tracking

    @staticmethod
    async def update_user_locale(session: AsyncSession, user: User, locale: str) -> None:
        """Update user locale."""
        user.locale = locale
        await session.flush()
        logger.info(f'Updated locale for user {user.tg_user_id}: {locale}')
