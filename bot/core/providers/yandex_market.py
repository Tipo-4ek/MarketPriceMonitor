"""Yandex Market provider placeholder."""
from bot.core.providers.base import Provider, ProductData
from bot.models.enums import ProviderEnum


class YandexMarketProvider(Provider):
    """Yandex Market provider (not implemented yet)."""

    @property
    def provider_type(self) -> ProviderEnum:
        return ProviderEnum.YANDEX_MARKET

    def supports(self, url: str) -> bool:
        return 'market.yandex.ru' in url.lower()

    async def normalize(self, url: str) -> str:
        raise NotImplementedError('Yandex Market provider not implemented yet')

    async def fetch_product(self, url: str) -> ProductData:
        raise NotImplementedError('Yandex Market provider not implemented yet')


