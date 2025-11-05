"""Product service for managing products."""
from decimal import Decimal

from sqlalchemy import select
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
        """Get existing product or create new one by fetching data from provider.

        Returns:
            Tuple of (product, created) where created is True if product was newly created.
        """
        # Find provider for URL
        provider = provider_registry.find_provider(url)
        if not provider:
            raise ValueError('Unsupported URL')

        # Normalize URL
        normalized_url = await provider.normalize(url)

        # Check if product exists
        result = await session.execute(
            select(Product).where(Product.url == normalized_url, Product.provider == provider.provider_type)
        )
        existing_product = result.scalar_one_or_none()

        if existing_product:
            return existing_product, False

        # Fetch product data
        product_data = await provider.fetch_product(normalized_url)

        # Create new product
        product = Product(
            provider=provider.provider_type,
            url=normalized_url,
            title=product_data.title,
            currency=product_data.currency,
            last_price=Decimal(str(product_data.price)),
        )

        session.add(product)
        await session.flush()

        logger.info(f'Created product: {product.title} ({product.provider.value})')
        return product, True

    @staticmethod
    async def get_product_by_id(session: AsyncSession, product_id: int) -> Product | None:
        """Get product by ID."""
        result = await session.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_product_by_url(session: AsyncSession, url: str, provider: ProviderEnum) -> Product | None:
        """Get product by URL and provider."""
        result = await session.execute(select(Product).where(Product.url == url, Product.provider == provider))
        return result.scalar_one_or_none()


