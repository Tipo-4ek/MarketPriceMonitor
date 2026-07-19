"""Avito provider placeholder."""

from bot.core.providers.base import ProductData, Provider
from bot.models.enums import ProviderEnum


class AvitoProvider(Provider):
    """Avito provider (not implemented yet)."""

    @property
    def provider_type(self) -> ProviderEnum:
        return ProviderEnum.AVITO

    def supports(self, url: str) -> bool:
        return 'avito.ru' in url.lower()

    async def normalize(self, url: str) -> str:
        raise NotImplementedError('Avito provider not implemented yet')

    async def fetch_product(self, url: str) -> ProductData:
        raise NotImplementedError('Avito provider not implemented yet')
