"""Provider registry: routes an incoming URL to the provider that claims it."""

from bot.core.providers.base import Provider, UnsupportedURLError
from bot.core.providers.wildberries import WildberriesProvider
from bot.models.enums import ProviderEnum


class ProviderRegistry:
    """Registry for all marketplace providers."""

    def __init__(self, providers: dict[ProviderEnum, Provider] | None = None):
        self.providers: dict[ProviderEnum, Provider] = providers or {
            ProviderEnum.WILDBERRIES: WildberriesProvider(),
        }

    def get_provider(self, provider_type: ProviderEnum) -> Provider | None:
        """Get provider by type."""
        return self.providers.get(provider_type)

    def find_provider(self, url: str) -> Provider:
        """Find the provider that supports this URL, or refuse the URL."""
        for provider in self.providers.values():
            if provider.supports(url):
                return provider
        raise UnsupportedURLError(f'No provider supports this URL: {url}')


# Global provider registry
provider_registry = ProviderRegistry()
