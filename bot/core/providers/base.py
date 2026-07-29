"""Provider interface, the data it returns, and its error taxonomy."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from bot.models.enums import ProviderEnum

# A price outside this range is a parsing accident, not a product: marketplaces
# serve 0 for out-of-stock items, and a stray match on a page can pick up a
# review count or an article number instead.
MIN_PRICE = Decimal('1')
MAX_PRICE = Decimal('100000000')


class ProviderError(Exception):
    """Base class for every failure a provider can report.

    The taxonomy matters to two different audiences: the user gets a specific
    message per subclass, and the health monitor only counts the subclasses that
    actually indicate the marketplace is unhealthy.
    """


class UnsupportedURLError(ProviderError):
    """No registered provider claims this URL."""


class ProviderBlockedError(ProviderError):
    """The marketplace served an anti-bot challenge instead of the product."""


class PriceNotFoundError(ProviderError):
    """The page rendered, but no plausible price could be read from it."""


@dataclass(frozen=True)
class ProductData:
    """Product data returned by providers."""

    title: str
    price: Decimal
    currency: str
    url: str

    def __post_init__(self) -> None:
        if not (MIN_PRICE <= self.price <= MAX_PRICE):
            raise PriceNotFoundError(f'Implausible price parsed: {self.price}')


class Provider(ABC):
    """Abstract base class for marketplace providers."""

    @property
    @abstractmethod
    def provider_type(self) -> ProviderEnum:
        """Provider type."""

    @abstractmethod
    def supports(self, url: str) -> bool:
        """Check if this provider supports the given URL."""

    @abstractmethod
    async def normalize(self, url: str) -> str:
        """Normalize URL to canonical form."""

    @abstractmethod
    async def fetch_product(self, url: str) -> ProductData:
        """Fetch product data from the marketplace."""
