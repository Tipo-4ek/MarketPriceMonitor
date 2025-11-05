"""Ozon provider using mobile version (m.ozon.ru) for better bypass."""
import asyncio
import json
import random
import re
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

from bot.core.config import settings
from bot.core.logging import get_logger
from bot.core.providers.base import Provider, ProductData
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)


class OzonMobileProvider(Provider):
    """
    Ozon provider using mobile version (m.ozon.ru) for better bypass.
    
    Mobile versions often have less aggressive anti-bot protection.
    """

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        
    @property
    def provider_type(self) -> ProviderEnum:
        return ProviderEnum.OZON

    def supports(self, url: str) -> bool:
        """Check if URL is from Ozon."""
        parsed = urlparse(url)
        return 'ozon.ru' in parsed.netloc.lower()

    async def normalize(self, url: str) -> str:
        """Normalize Ozon URL to mobile version."""
        # Extract product ID and return mobile URL
        match = re.search(r'/product/.*?-?(\d+)/?$', url)
        if match:
            product_id = match.group(1)
            return f'https://m.ozon.ru/product/-{product_id}/'
        return url

    def _extract_article_from_url(self, url: str) -> Optional[int]:
        """Extract article number from Ozon URL."""
        match = re.search(r'/product/.*?-?(\d+)/?$', url)
        if match:
            return int(match.group(1))
        return None

    async def _setup_browser(self):
        """Setup Playwright browser for mobile version."""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            
            # Use Chromium with mobile settings
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--lang=ru-RU',
                ],
            )
            
            # Create context with mobile settings
            context = await self.browser.new_context(
                viewport={'width': 375, 'height': 667},  # iPhone size
                user_agent=(
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
                ),
                locale='ru-RU',
                timezone_id='Europe/Moscow',
                extra_http_headers={
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                },
            )
            
            self.page = await context.new_page()
            
            # Apply playwright-stealth
            await stealth_async(self.page)
            
            # Additional mobile-specific anti-detection
            await self.page.add_init_script(
                """
                // Override navigator properties for mobile
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'iPhone'
                });
                
                Object.defineProperty(navigator, 'maxTouchPoints', {
                    get: () => 5
                });
                
                // Override screen properties
                Object.defineProperty(screen, 'width', {
                    get: () => 375
                });
                
                Object.defineProperty(screen, 'height', {
                    get: () => 667
                });
                
                // Override chrome property
                window.chrome = undefined;
                """
            )

    async def _human_delay(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """Random delay to mimic human behavior."""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def fetch_product(self, url: str) -> ProductData:
        """Fetch product data from Ozon mobile version."""
        try:
            await self._setup_browser()

            # Convert to mobile URL
            mobile_url = await self.normalize(url)
            logger.info(f'Fetching product from Ozon mobile: {mobile_url}')
            
            # Navigate to mobile page
            await self.page.goto(mobile_url, wait_until='domcontentloaded', timeout=30000)
            
            # Human-like delay
            await self._human_delay(2, 4)
            
            # Check if we hit a block page
            page_text = await self.page.evaluate('() => document.body.innerText')
            if 'Доступ ограничен' in page_text or 'Access denied' in page_text:
                logger.error('🚫 Ozon mobile blocked the request!')
                raise ValueError('Ozon mobile blocked the request')
            
            # Wait for key elements to load
            try:
                await self.page.wait_for_selector('h1', timeout=10000)
                logger.info('Page loaded successfully')
            except Exception:
                logger.warning('Could not find h1 element, trying to continue...')
            
            # Additional delay for dynamic content
            await self._human_delay(1, 2)
            
            # Parse title
            title = None
            title_selectors = [
                'h1',
                '[data-widget="webProductHeading"] h1',
                '.product-title',
                '.title',
            ]
            
            for selector in title_selectors:
                try:
                    title_element = await self.page.query_selector(selector)
                    if title_element:
                        title = await title_element.inner_text()
                        title = title.strip()
                        if title and len(title) > 3:
                            logger.info(f'Found title with selector: {selector}')
                            break
                except Exception:
                    continue

            if not title:
                raise ValueError('Could not parse product title')

            # Parse price
            price = None
            price_selectors = [
                '[data-widget="webPrice"] span',
                '[data-widget="webPrice"]',
                '.price span',
                '.price',
                '[class*="price"] span',
                '[class*="Price"] span',
            ]

            for selector in price_selectors:
                try:
                    price_elements = await self.page.query_selector_all(selector)
                    for element in price_elements:
                        price_text = await element.inner_text()
                        price_text = price_text.strip()
                        
                        if not price_text or len(price_text) < 1:
                            continue
                        
                        # Extract numbers from price
                        price_text_clean = price_text.replace('\xa0', '').replace(' ', '').replace('₽', '').replace(',', '.')
                        price_match = re.search(r'(\d+(?:\.\d+)?)', price_text_clean)
                        
                        if price_match:
                            try:
                                price_str = price_match.group(1)
                                price = Decimal(price_str)
                                if price > 0:
                                    logger.info(f'Found price: {price} with selector: {selector}')
                                    break
                            except Exception:
                                continue
                    
                    if price and price > 0:
                        break
                except Exception:
                    continue

            if not price:
                # Try to extract price from page text
                try:
                    page_text = await self.page.evaluate('() => document.body.innerText')
                    
                    # Look for price patterns in text
                    price_patterns = [
                        r'(\d+\s*\d*\s*\d*)\s*₽',
                        r'(\d+\s*\d*\s*\d*)\s*руб',
                        r'цена[:\s]+(\d+\s*\d*)',
                    ]
                    
                    for pattern in price_patterns:
                        matches = re.findall(pattern, page_text, re.IGNORECASE)
                        for match in matches:
                            try:
                                price_str = match.replace(' ', '').replace('\xa0', '')
                                test_price = Decimal(price_str)
                                if 10 < test_price < 10000000:  # Reasonable price range
                                    price = test_price
                                    logger.info(f'Extracted price from page text: {price}')
                                    break
                            except Exception:
                                continue
                        if price:
                            break
                except Exception:
                    pass
                
                if not price:
                    raise ValueError('Could not parse product price')

            # Currency is always RUB for Ozon
            currency = 'RUB'

            logger.info(f'Successfully parsed: {title}, {price} {currency}')

            return ProductData(title=title, price=price, currency=currency, url=url)

        except Exception as e:
            logger.error(f'Error fetching product from Ozon mobile: {e}', exc_info=True)
            raise
        finally:
            # Clean up browser
            await self._close_browser()

    async def _close_browser(self):
        """Close browser and cleanup."""
        if self.page:
            await self.page.close()
            self.page = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

