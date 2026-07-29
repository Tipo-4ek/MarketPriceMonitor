"""Product service for managing products."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.logging import get_logger
from bot.core.providers import provider_registry
from bot.models import Product

logger = get_logger(__name__)


class ProductService:
    """Service for product operations."""

    @staticmethod
    async def get_or_create_product(session: AsyncSession, url: str) -> tuple[Product, bool]:
        """Get an existing product, or fetch it from the marketplace and store it.

        Returns:
            Tuple of (product, created) where created is True if product was newly created.

        Raises:
            UnsupportedURLError: no registered provider claims this URL.
            ProviderError: the marketplace blocked us or served no price.
        """
        provider = provider_registry.find_provider(url)
        normalized_url = await provider.normalize(url)

        result = await session.execute(
            select(Product).where(Product.url == normalized_url, Product.provider == provider.provider_type)
        )
        existing_product = result.scalar_one_or_none()
        if existing_product:
            return existing_product, False

        product_data = await provider.fetch_product(normalized_url)

        product = Product(
            provider=provider.provider_type,
            url=normalized_url,
            title=product_data.title,
            currency=product_data.currency,
            last_price=product_data.price,
        )
        session.add(product)
        await session.flush()

        logger.info(
            'Product created',
            extra={'product_id': product.id, 'provider': product.provider.value, 'price': str(product.last_price)},
        )
        return product, True
