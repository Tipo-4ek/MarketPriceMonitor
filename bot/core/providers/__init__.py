"""Provider registry and initialization."""
from bot.core.providers.avito import AvitoProvider
from bot.core.providers.base import Provider
from bot.core.providers.ozon import OzonProvider
from bot.core.providers.wildberries import WildberriesProvider
from bot.core.providers.yandex_market import YandexMarketProvider
from bot.models.enums import ProviderEnum


class ProviderRegistry:
    """Registry for all marketplace providers."""

    def __init__(self):
        self.providers: dict[ProviderEnum, Provider] = {
            ProviderEnum.OZON: OzonProvider(),
            ProviderEnum.AVITO: AvitoProvider(),
            ProviderEnum.WILDBERRIES: WildberriesProvider(),
            ProviderEnum.YANDEX_MARKET: YandexMarketProvider(),
        }

    def get_provider(self, provider_type: ProviderEnum) -> Provider | None:
        """Get provider by type."""
        return self.providers.get(provider_type)

    def find_provider(self, url: str) -> Provider | None:
        """Find provider that supports the given URL."""
        for provider in self.providers.values():
            if provider.supports(url):
                return provider
        return None


# Global provider registry
provider_registry = ProviderRegistry()

