"""Simple but effective Ozon provider with basic bypass techniques."""
import asyncio
import json
import random
import re
import time
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

from bot.core.config import settings
from bot.core.logging import get_logger
from bot.core.providers.anti_bot.proxy_provider import ProxyProvider
from bot.core.providers.base import Provider, ProductData
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)

# Try to import browser automation libraries
try:
    from playwright.async_api import async_playwright
    from playwright_stealth import stealth_async
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


class OzonSimpleProvider(Provider):
    """
    Simple but effective Ozon provider.
    
    This provider focuses on reliability over complexity:
    1. Basic Playwright with stealth
    2. Simple HTTP requests with proper headers
    3. Mobile user agent simulation
    4. Proxy rotation
    """

    def __init__(self):
        self.proxy_provider = None
        self._initialize_proxy_provider()
        
    def _initialize_proxy_provider(self):
        """Initialize proxy provider."""
        if settings.proxy_file:
            logger.info(f'Initializing proxy pool from file: {settings.proxy_file}')
            self.proxy_provider = ProxyProvider(proxy_file=settings.proxy_file)
            if self.proxy_provider.has_proxies():
                logger.info(f'✅ Loaded {self.proxy_provider.pool_size()} proxies')
            else:
                logger.warning('⚠️ No proxies loaded from file')
        elif settings.proxy_url:
            logger.info('Initializing with single proxy URL')
            self.proxy_provider = ProxyProvider(proxy_url=settings.proxy_url)
        else:
            logger.warning('⚠️ No proxy configured - Ozon may block requests!')

    @property
    def provider_type(self) -> ProviderEnum:
        return ProviderEnum.OZON

    def supports(self, url: str) -> bool:
        """Check if URL is from Ozon."""
        parsed = urlparse(url)
        return 'ozon.ru' in parsed.netloc.lower()

    async def normalize(self, url: str) -> str:
        """Normalize Ozon URL."""
        match = re.search(r'/product/.*?-?(\d+)/?$', url)
        if match:
            product_id = match.group(1)
            return f'https://www.ozon.ru/product/-{product_id}/'
        return url

    def _extract_article_from_url(self, url: str) -> Optional[int]:
        """Extract article number from Ozon URL."""
        match = re.search(r'/product/.*?-?(\d+)/?$', url)
        if match:
            return int(match.group(1))
        return None

    async def fetch_product(self, url: str) -> ProductData:
        """Fetch product data using simple but effective methods."""
        
        # Try simple HTTP request first
        if AIOHTTP_AVAILABLE:
            try:
                logger.info("🔄 Trying simple HTTP request")
                result = await self._fetch_with_http(url)
                logger.info("✅ Success with HTTP request")
                return result
            except Exception as e:
                logger.warning(f"❌ HTTP request failed: {e}")
        
        # Fallback to Playwright
        if PLAYWRIGHT_AVAILABLE:
            try:
                logger.info("🔄 Trying Playwright")
                result = await self._fetch_with_playwright(url)
                logger.info("✅ Success with Playwright")
                return result
            except Exception as e:
                logger.warning(f"❌ Playwright failed: {e}")
        
        raise ValueError("All methods failed")

    async def _fetch_with_http(self, url: str) -> ProductData:
        """Fetch using simple HTTP request with proper headers."""
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp not available")
        
        # Get proxy for this request
        proxy_url = None
        if self.proxy_provider and self.proxy_provider.has_proxies():
            proxy_dict = self.proxy_provider.get_random_proxy()
            if proxy_dict:
                proxy_url = proxy_dict['server']
                if proxy_dict.get('username') and proxy_dict.get('password'):
                    proxy_url = f"http://{proxy_dict['username']}:{proxy_dict['password']}@{proxy_url.replace('http://', '')}"
                logger.info(f"🔒 Using proxy: {proxy_dict['server']}")
        
        # Simple headers that look like a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"HTTP request returned status {response.status}")
                    
                    html_content = await response.text()
                    
                    # Extract data from HTML
                    return await self._extract_product_data_from_html(html_content, url)
                    
        except Exception as e:
            logger.error(f"HTTP fetch failed: {e}")
            raise

    async def _fetch_with_playwright(self, url: str) -> ProductData:
        """Fetch using Playwright with basic stealth."""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright not available")
        
        playwright = None
        browser = None
        page = None
        
        try:
            playwright = await async_playwright().start()
            
            # Get proxy for this request
            proxy_config = None
            if self.proxy_provider and self.proxy_provider.has_proxies():
                proxy_dict = self.proxy_provider.get_random_proxy()
                if proxy_dict:
                    proxy_config = {
                        'server': proxy_dict['server'],
                    }
                    if proxy_dict.get('username') and proxy_dict.get('password'):
                        proxy_config['username'] = proxy_dict['username']
                        proxy_config['password'] = proxy_dict['password']
                    logger.info(f"🔒 Using proxy: {proxy_dict['server']}")
            
            # Launch browser with basic options
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                ],
            )
            
            # Create context
            context_options = {
                'viewport': {'width': 375, 'height': 667},
                'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                'locale': 'ru-RU',
                'timezone_id': 'Europe/Moscow',
            }
            
            if proxy_config:
                context_options['proxy'] = proxy_config
            
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            # Apply basic stealth
            await stealth_async(page)
            
            # Navigate to page
            logger.info(f"Navigating to: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # Wait a bit for content to load
            await asyncio.sleep(random.uniform(2, 4))
            
            # Check for blocking
            page_text = await page.evaluate('() => document.body.innerText')
            if 'Доступ ограничен' in page_text or 'Access denied' in page_text:
                raise ValueError("Access denied - page blocked")
            
            # Extract data
            html_content = await page.content()
            return await self._extract_product_data_from_html(html_content, url)
            
        finally:
            if page:
                await page.close()
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

    async def _extract_product_data_from_html(self, html_content: str, url: str) -> ProductData:
        """Extract product data from HTML content."""
        
        # Try to extract from JSON-LD first
        try:
            json_ld_match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_content, re.DOTALL)
            if json_ld_match:
                json_data = json.loads(json_ld_match.group(1))
                if isinstance(json_data, dict) and 'offers' in json_data:
                    offers = json_data['offers']
                    if isinstance(offers, dict) and 'price' in offers:
                        price = Decimal(str(offers['price']))
                        title = json_data.get('name', 'Unknown Product')
                        return ProductData(title=title, price=price, currency='RUB', url=url)
                    elif isinstance(offers, list) and len(offers) > 0 and 'price' in offers[0]:
                        price = Decimal(str(offers[0]['price']))
                        title = json_data.get('name', 'Unknown Product')
                        return ProductData(title=title, price=price, currency='RUB', url=url)
        except Exception:
            pass
        
        # Try to extract from page title
        title = None
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()
            # Clean up title
            title = re.sub(r'\s*-\s*Ozon\s*$', '', title, flags=re.IGNORECASE)
            title = re.sub(r'\s*-\s*Озон\s*$', '', title, flags=re.IGNORECASE)
        
        if not title:
            title = "Unknown Product"
        
        # Try to extract price using multiple patterns
        price = None
        
        # Look for price in various formats
        price_patterns = [
            r'(\d+(?:\s*\d*)*)\s*₽',
            r'(\d+(?:\s*\d*)*)\s*руб',
            r'цена[:\s]+(\d+(?:\s*\d*)*)',
            r'price[:\s]+(\d+(?:\s*\d*)*)',
            r'"price":\s*"?(\d+)"?',
            r'"cardPrice":\s*"?(\d+)"?',
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                try:
                    # Clean up the price string
                    price_str = str(match).replace(' ', '').replace('\xa0', '').replace(',', '.')
                    # Extract only numbers
                    price_match = re.search(r'(\d+(?:\.\d+)?)', price_str)
                    if price_match:
                        test_price = Decimal(price_match.group(1))
                        if 10 < test_price < 10000000:  # Reasonable price range
                            price = test_price
                            break
                except Exception:
                    continue
            if price:
                break
        
        if not price:
            # Last resort: look for any number that could be a price
            numbers = re.findall(r'\b(\d{3,7})\b', html_content)
            for num_str in numbers:
                try:
                    test_price = Decimal(num_str)
                    if 100 < test_price < 1000000:  # Reasonable price range
                        price = test_price
                        break
                except Exception:
                    continue
        
        if not price:
            raise ValueError("Could not extract price from page")
        
        logger.info(f"Successfully parsed: {title}, {price} RUB")
        
        return ProductData(title=title, price=price, currency='RUB', url=url)
