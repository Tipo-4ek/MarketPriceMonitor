"""Base provider interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from bot.models.enums import ProviderEnum


@dataclass
class ProductData:
    """Product data returned by providers."""

    title: str
    price: Decimal
    currency: str
    url: str
    screenshot_path: str = None  # Path to screenshot of the product page
    raw_html: str = None  # Raw HTML content for debugging
    debug_info: dict = None  # Additional debug information


class Provider(ABC):
    """Abstract base class for marketplace providers."""

    @property
    @abstractmethod
    def provider_type(self) -> ProviderEnum:
        """Provider type."""
        pass

    @abstractmethod
    def supports(self, url: str) -> bool:
        """Check if this provider supports the given URL."""
        pass

    @abstractmethod
    async def normalize(self, url: str) -> str:
        """Normalize URL to canonical form."""
        pass

    @abstractmethod
    async def fetch_product(self, url: str) -> ProductData:
        """Fetch product data from the marketplace."""
        pass


