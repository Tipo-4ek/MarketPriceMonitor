"""Wildberries provider placeholder."""
from bot.core.providers.base import Provider, ProductData
from bot.models.enums import ProviderEnum


class WildberriesProvider(Provider):
    """Wildberries provider (not implemented yet)."""

    @property
    def provider_type(self) -> ProviderEnum:
        return ProviderEnum.WILDBERRIES

    def supports(self, url: str) -> bool:
        return 'wildberries.ru' in url.lower() or 'wb.ru' in url.lower()

    async def normalize(self, url: str) -> str:
        raise NotImplementedError('Wildberries provider not implemented yet')

    async def fetch_product(self, url: str) -> ProductData:
        raise NotImplementedError('Wildberries provider not implemented yet')


