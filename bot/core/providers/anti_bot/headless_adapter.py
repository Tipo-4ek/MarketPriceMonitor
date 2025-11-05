"""Headless browser adapter for JavaScript-rendered pages."""


class HeadlessAdapter:
    """Adapter for headless browser scraping (not implemented)."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    async def fetch(self, url: str) -> str:
        """Fetch page using headless browser."""
        raise NotImplementedError('Headless browser not implemented yet')


