"""Product service for managing products."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.logging import get_logger
from bot.core.providers import provider_registry
from bot.models import Product
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)


class ProductService:
    """Service for product operations."""

    @staticmethod
    async def get_or_create_product(session: AsyncSession, url: str) -> tuple[Product, bool]:
        """Get an existing product, or fetch it from the marketplace and store it.

        Returns ``(product, created)``; ``created`` is True only for a fresh row.

        The insert is guarded against the two-concurrent-/add race: both callers
        can pass the SELECT and both try to insert, but ``uq_product_url_provider``
        lets only one win. The loser catches the IntegrityError and re-selects the
        row the winner committed, so it returns the same product rather than a
        generic error.

        Raises:
            UnsupportedURLError: no registered provider claims this URL.
            ProviderError: the marketplace blocked us or served no price.
        """
        provider = provider_registry.find_provider(url)
        normalized_url = await provider.normalize(url)

        existing = await ProductService._find(session, normalized_url, provider.provider_type)
        if existing is not None:
            return existing, False

        product_data = await provider.fetch_product(normalized_url)

        product = Product(
            provider=provider.provider_type,
            url=normalized_url,
            title=product_data.title,
            currency=product_data.currency,
            last_price=product_data.price,
        )
        session.add(product)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raced = await ProductService._find(session, normalized_url, provider.provider_type)
            if raced is None:
                raise
            return raced, False

        logger.info(
            'Product created',
            extra={'product_id': product.id, 'provider': product.provider.value, 'price': str(product.last_price)},
        )
        return product, True

    @staticmethod
    async def _find(session: AsyncSession, normalized_url: str, provider_type: ProviderEnum) -> Product | None:
        result = await session.execute(
            select(Product).where(Product.url == normalized_url, Product.provider == provider_type)
        )
        return result.scalar_one_or_none()
