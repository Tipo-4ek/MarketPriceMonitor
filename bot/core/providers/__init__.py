"""Provider registry: routes an incoming URL to the provider that claims it."""

from bot.core.config import settings
from bot.core.providers.base import Provider, UnsupportedURLError
from bot.core.providers.generic import GenericProvider
from bot.core.providers.url_safety import is_blocked_host, is_safe_url
from bot.core.providers.wildberries import WildberriesProvider
from bot.models.enums import ProviderEnum


def _default_providers() -> dict[ProviderEnum, Provider]:
    """The shipped providers, site-specific first and the generic one last.

    The generic provider is only added when ``GENERIC_PROVIDER_ENABLED`` is set,
    because it opens arbitrary user-supplied URLs; it goes last so a
    site-specific provider claims its own hosts first.
    """
    providers: dict[ProviderEnum, Provider] = {ProviderEnum.WILDBERRIES: WildberriesProvider()}
    if settings.generic_provider_enabled:
        providers[ProviderEnum.GENERIC] = GenericProvider()
    return providers


class ProviderRegistry:
    """Registry for all providers."""

    def __init__(self, providers: dict[ProviderEnum, Provider] | None = None):
        # `providers if providers is not None`, not `providers or ...`: an
        # explicit empty registry (a test wanting no providers) must stay empty
        # rather than being silently replaced by the default.
        self.providers: dict[ProviderEnum, Provider] = providers if providers is not None else _default_providers()

    def get_provider(self, provider_type: ProviderEnum) -> Provider | None:
        """Get provider by type."""
        return self.providers.get(provider_type)

    def find_provider(self, url: str) -> Provider:
        """Find the provider that supports this URL, or refuse the URL.

        A URL that is not an ordinary public http(s) address, or that a
        deployment has block-listed, is refused before any provider sees it:
        letting the shared browser reach the host's own network is exactly the
        risk the generic provider has to guard against.
        """
        if not is_safe_url(url) or is_blocked_host(url, settings.blocked_host_set):
            raise UnsupportedURLError(f'URL is not an allowed fetch target: {url}')
        for provider in self.providers.values():
            if provider.supports(url):
                return provider
        raise UnsupportedURLError(f'No provider supports this URL: {url}')


# Global provider registry
provider_registry = ProviderRegistry()
