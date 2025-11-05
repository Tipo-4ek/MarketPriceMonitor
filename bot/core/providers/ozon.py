"""Ozon provider implementation using Playwright."""
import asyncio
import json
import random
import re
from decimal import Decimal
from urllib.parse import urlparse

from playwright.async_api import async_playwright
try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

from bot.core.config import settings
from bot.core.logging import get_logger
from bot.core.providers.anti_bot.proxy_provider import ProxyProvider
from bot.core.providers.base import Provider, ProductData
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)


class OzonProvider(Provider):
    """Ozon marketplace provider using Playwright for browser automation."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        
        # Initialize proxy provider
        self.proxy_provider = None
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
        # Extract product ID and return clean URL
        match = re.search(r'/product/[^/]+-(\d+)', url)
        if match:
            product_id = match.group(1)
            return f'https://www.ozon.ru/product/-{product_id}/'
        return url

    async def _setup_browser(self):
        """Setup Playwright browser with advanced anti-detection."""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            
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
                    
                    logger.info(f'🔒 Using proxy: {proxy_dict["server"]}')
            
            # Use Chromium with advanced anti-detection
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
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-field-trial-config',
                    '--disable-ipc-flooding-protection',
                    '--disable-hang-monitor',
                    '--disable-prompt-on-repost',
                    '--disable-sync',
                    '--disable-translate',
                    '--disable-logging',
                    '--disable-gpu-logging',
                    '--silent',
                    '--log-level=3',
                    '--disable-default-apps',
                    '--disable-component-extensions-with-background-pages',
                    '--disable-background-networking',
                    '--disable-sync-preferences',
                    '--disable-component-update',
                    '--disable-domain-reliability',
                    '--disable-features=TranslateUI',
                    '--lang=ru-RU',
                ],
            )
            
            # Create context with realistic settings and proxy
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'locale': 'ru-RU',
                'timezone_id': 'Europe/Moscow',
                'extra_http_headers': {
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                },
            }
            
            # Add proxy if configured
            if proxy_config:
                context_options['proxy'] = proxy_config
            
            context = await self.browser.new_context(**context_options)
            
            self.page = await context.new_page()
            
            # Apply playwright-stealth for advanced anti-detection
            if STEALTH_AVAILABLE:
                await stealth_async(self.page)
            
            # Advanced anti-detection measures
            await self.page.add_init_script(
                """
                // Override chrome property
                window.chrome = {
                    runtime: {}
                };
                
                // Override webdriver detection
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                
                // Override plugins
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                
                // Override languages
                Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
                
                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                """
            )

    async def _human_delay(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """Random delay to mimic human behavior."""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def fetch_product(self, url: str) -> ProductData:
        """Fetch product data from Ozon using Playwright."""
        try:
            await self._setup_browser()

            logger.info(f'Fetching product from Ozon: {url}')
            
            # Step 1: Visit main page to establish session
            try:
                logger.info('Visiting Ozon main page first to establish session...')
                await self.page.goto('https://www.ozon.ru/', wait_until='domcontentloaded', timeout=30000)
                await self._human_delay(3, 5)
                
                # Human-like behavior on main page
                await self.page.mouse.move(100, 100)
                await self._human_delay(0.3, 0.5)
                await self.page.evaluate('window.scrollTo(0, 500)')
                await self._human_delay(2, 3)
                await self.page.evaluate('window.scrollTo(0, 1000)')
                await self._human_delay(2, 4)
                await self.page.evaluate('window.scrollTo(0, 0)')
                await self._human_delay(1, 2)
                
                # Take screenshot of main page
                try:
                    await self.page.screenshot(path='/tmp/ozon_main_page.png')
                    logger.info('Screenshot of main page saved to /tmp/ozon_main_page.png')
                except Exception:
                    pass
                    
            except Exception as e:
                logger.warning(f'Could not visit main page: {e}')
                # Take screenshot even if main page failed
                try:
                    await self.page.screenshot(path='/tmp/ozon_main_page_failed.png')
                    logger.info('Screenshot of failed main page saved to /tmp/ozon_main_page_failed.png')
                except Exception:
                    pass
            
            # Step 2: Navigate to product page
            try:
                logger.info('Navigating to product page...')
                await self.page.goto(url, wait_until='networkidle', timeout=50000)
            except Exception as e:
                logger.warning(f'networkidle failed, trying domcontentloaded: {e}')
                try:
                    await self.page.goto(url, wait_until='domcontentloaded', timeout=40000)
                except Exception as e2:
                    logger.warning(f'domcontentloaded also failed: {e2}')
                    # Try with basic load
                    await self.page.goto(url, timeout=30000)
            
            # Human-like delay after page load
            await self._human_delay(2, 4)
            
            # Take screenshot of product page
            try:
                await self.page.screenshot(path='/tmp/ozon_product_page.png')
                logger.info('Screenshot of product page saved to /tmp/ozon_product_page.png')
            except Exception:
                pass
            
            # Check if we hit a block page
            page_text = await self.page.evaluate('() => document.body.innerText')
            if 'Доступ ограничен' in page_text or 'Access denied' in page_text:
                logger.error('🚫 Ozon blocked the request - Anti-bot detected!')
                logger.error('This means Ozon detected automation. Possible solutions:')
                logger.error('1. Use residential proxy (set PROXY_URL in .env)')
                logger.error('2. Add delays between requests')
                logger.error('3. Use headless=False mode')
                
                # Take screenshot of blocked page
                try:
                    await self.page.screenshot(path='/tmp/ozon_blocked_page.png')
                    logger.info('Screenshot of blocked page saved to /tmp/ozon_blocked_page.png')
                except Exception:
                    pass
                
                raise ValueError(
                    'Ozon blocked the request. The site detected automation. '
                    'Try: 1) Using a proxy, 2) Waiting before retrying, 3) Using a different network'
                )

            # Wait for key elements to load - try multiple selectors
            page_loaded = False
            load_selectors = [
                '[data-widget="webProductHeading"]',
                '[data-widget="webPrice"]',
                'h1',
            ]
            
            for selector in load_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=10000)
                    page_loaded = True
                    logger.info(f'Page loaded, found selector: {selector}')
                    break
                except Exception:
                    continue
            
            if not page_loaded:
                logger.warning('Failed to load page - no key elements found, trying alternative approach...')
                
                # Try to wait a bit more and check again
                await asyncio.sleep(5)
                
                # Try again with different selectors
                alternative_selectors = [
                    'body',
                    'div',
                    'main',
                    '[class*="Product"]',
                    '[class*="product"]',
                ]
                
                for selector in alternative_selectors:
                    try:
                        await self.page.wait_for_selector(selector, timeout=5000)
                        page_loaded = True
                        logger.info(f'Page loaded with alternative selector: {selector}')
                        break
                    except Exception:
                        continue
                
                if not page_loaded:
                    logger.error('Failed to load page - no key elements found')
                    # Take screenshot for debugging if possible
                    try:
                        await self.page.screenshot(path='/tmp/ozon_error.png')
                        logger.info('Screenshot saved to /tmp/ozon_error.png')
                    except Exception:
                        pass
                    raise ValueError('Page did not load properly - no key elements found')

            # Additional delay for dynamic content
            await self._human_delay(1, 2)
            
            # Human-like interaction to trigger dynamic content
            try:
                # Move mouse to simulate real user
                await self.page.mouse.move(100, 100)
                await self._human_delay(0.3, 0.5)
                
                # Scroll slowly to trigger lazy loading
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight / 3)')
                await self._human_delay(1, 2)
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
                await self._human_delay(1, 2)
                await self.page.evaluate('window.scrollTo(0, 0)')
                await self._human_delay(1, 2)
                
                # Additional wait for price to load
                logger.info('Waiting for dynamic price elements to load...')
                await asyncio.sleep(3)
            except Exception as e:
                logger.debug(f'Scrolling failed: {e}')

            # Parse title with more selectors from Habr article
            title = None
            title_selectors = [
                '[data-widget="webProductHeading"] h1',
                'h1[data-widget="webProductHeading"]',
                'div[data-widget="webProductHeading"] h1',
                'h1.tsHeadline550Medium',
                'h1[class*="ProductHeading"]',
                'h1',
            ]
            
            for selector in title_selectors:
                try:
                    title_element = await self.page.query_selector(selector)
                    if title_element:
                        title = await title_element.inner_text()
                        title = title.strip()
                        if title and len(title) > 3:  # Valid title check
                            logger.info(f'Found title with selector: {selector}')
                            break
                except Exception as e:
                    logger.debug(f'Title selector {selector} failed: {e}')
                    continue

            if not title:
                logger.error('Could not find product title with any selector')
                raise ValueError('Could not parse product title')

            # Parse price - try JSON-LD first, then DOM selectors
            price = None
            
            # First, try to extract price from JSON-LD structured data (most reliable)
            try:
                logger.info('Trying to extract price from JSON-LD structured data...')
                json_ld_script = await self.page.query_selector('script[type="application/ld+json"]')
                if json_ld_script:
                    json_text = await json_ld_script.inner_text()
                    json_data = json.loads(json_text)
                    
                    # Look for price in different possible locations
                    if isinstance(json_data, dict):
                        # Try offers.price
                        if 'offers' in json_data:
                            offers = json_data['offers']
                            if isinstance(offers, dict) and 'price' in offers:
                                price = Decimal(str(offers['price']))
                                logger.info(f'✅ Found price in JSON-LD offers: {price}')
                            elif isinstance(offers, list) and len(offers) > 0 and 'price' in offers[0]:
                                price = Decimal(str(offers[0]['price']))
                                logger.info(f'✅ Found price in JSON-LD offers[0]: {price}')
            except Exception as e:
                logger.debug(f'JSON-LD extraction failed: {e}')
            
            # If JSON-LD didn't work, try DOM selectors
            if not price:
                logger.info('JSON-LD failed, trying DOM selectors...')
                
                # Try to wait for price widget to appear
                try:
                    logger.info('Waiting for price widget...')
                    await self.page.wait_for_selector('[data-widget="webPrice"]', timeout=5000)
                    await self._human_delay(0.5, 1)
                except Exception:
                    logger.warning('Price widget not found with wait_for_selector, trying alternatives...')
                
                price_selectors = [
                    '[data-widget="webPrice"] span',
                    '[data-widget="webPrice"]',
                    'span[class*="Price_price"]',
                    'span[class*="price"]',
                    'div[class*="PriceInfo"] span',
                    '.price span',
                    # Additional selectors for edge cases
                    'div[data-widget="webPrice"] span',
                    'span[class*="tsBodyControl500Medium"]',
                    'span[class*="tsHeadline500Medium"]',
                    '[class*="PriceBlock"] span',
                    '[class*="priceInfo"] span',
                    # More specific selectors for Ozon
                    '[data-widget="webPrice"] [class*="price"]',
                    '[data-widget="webPrice"] [class*="Price"]',
                    'div[data-widget="webPrice"] [class*="price"]',
                    'div[data-widget="webPrice"] [class*="Price"]',
                    # Generic price selectors
                    'span:contains("₽")',
                    'span:contains("руб")',
                    'div:contains("₽")',
                    'div:contains("руб")',
                ]

                for selector in price_selectors:
                    try:
                        price_elements = await self.page.query_selector_all(selector)
                        logger.debug(f'Selector "{selector}" found {len(price_elements)} elements')
                        for element in price_elements:
                            price_text = await element.inner_text()
                            price_text = price_text.strip()
                            logger.debug(f'Price text from "{selector}": "{price_text}"')
                            
                            # Skip empty or very short text
                            if not price_text or len(price_text) < 1:
                                continue
                            
                            # Extract numbers from price (remove spaces, ₽, non-breaking spaces, etc)
                            # Handle formats like: "1 500 ₽", "1500₽", "1 500", etc.
                            price_text_clean = price_text.replace('\xa0', '').replace(' ', '').replace('₽', '').replace(',', '.')
                            price_match = re.search(r'(\d+(?:\.\d+)?)', price_text_clean)
                            
                            if price_match:
                                try:
                                    price_str = price_match.group(1)
                                    price = Decimal(price_str)
                                    if price > 0:
                                        logger.info(f'✅ Found price: {price} with selector: {selector}')
                                        break
                                except Exception as e:
                                    logger.debug(f'Failed to parse price from "{price_text}": {e}')
                                    continue
                        
                        if price and price > 0:
                            break
                    except Exception as e:
                        logger.debug(f'Price selector {selector} failed: {e}')
                        continue

            # If DOM selectors didn't work, try page text extraction
            if not price:
                logger.info('DOM selectors failed, trying page text extraction...')
                try:
                    page_text = await self.page.evaluate('() => document.body.innerText')
                    
                    # Log sample of page text for debugging
                    logger.debug(f'Page text sample (first 500 chars): {page_text[:500]}')
                    
                    # Check for common blocking messages
                    if 'captcha' in page_text.lower() or 'проверка' in page_text.lower():
                        logger.error('⚠️  CAPTCHA or verification detected on page!')
                    
                    # Look for price patterns in text (Russian format)
                    price_patterns = [
                        r'(\d{1,3}(?:\s\d{3})*)\s*₽',  # "77 000 ₽"
                        r'(\d{1,3}(?:\s\d{3})*)\s*руб',  # "77 000 руб"
                        r'цена[:\s]+(\d{1,3}(?:\s\d{3})*)',  # "цена: 77 000"
                        r'(\d{1,3}(?:\s\d{3})*)\s*рублей',  # "77 000 рублей"
                        r'от\s+(\d{1,3}(?:\s\d{3})*)',  # "от 77 000"
                        r'(\d{1,3}(?:\s\d{3})*)\s*р\.',  # "77 000 р."
                    ]
                    
                    for pattern in price_patterns:
                        matches = re.findall(pattern, page_text, re.IGNORECASE)
                        for match in matches:
                            try:
                                price_str = match.replace(' ', '').replace('\xa0', '')
                                test_price = Decimal(price_str)
                                # More flexible price range for expensive items
                                if 10 < test_price < 100000000:  # Up to 100M RUB
                                    price = test_price
                                    logger.info(f'✅ Extracted price from page text: {price}')
                                    break
                            except Exception:
                                continue
                        if price:
                            break
                except Exception as e:
                    logger.debug(f'Failed to extract price from page text: {e}')

            if not price:
                logger.error('Could not find product price with any method')
                
                # Log page title and URL to verify we're on the right page
                try:
                    page_title = await self.page.title()
                    current_url = self.page.url
                    logger.info(f'Current page title: {page_title}')
                    logger.info(f'Current URL: {current_url}')
                except Exception:
                    pass
                
                # Save screenshot for debugging
                try:
                    screenshot_path = f'/tmp/ozon_no_price_{urlparse(url).path.split("/")[-2]}.png'
                    await self.page.screenshot(path=screenshot_path)
                    logger.info(f'Screenshot saved to {screenshot_path}')
                except Exception:
                    pass
                
                # Try to get page content for debugging
                try:
                    content = await self.page.content()
                    logger.debug(f'Page content sample: {content[:1000]}...')
                except Exception:
                    pass
                raise ValueError('Could not parse product price')

            # Currency is always RUB for Ozon
            currency = 'RUB'

            # Take final screenshot with price highlighted
            try:
                # Try to highlight price elements
                await self.page.evaluate("""
                    // Highlight price elements
                    const priceElements = document.querySelectorAll('[data-widget="webPrice"], .price, [class*="Price"]');
                    priceElements.forEach(el => {
                        el.style.border = '3px solid red';
                        el.style.backgroundColor = 'yellow';
                    });
                """)
                await self.page.screenshot(path='/tmp/ozon_final_with_price.png')
                logger.info('Final screenshot with highlighted price saved to /tmp/ozon_final_with_price.png')
            except Exception:
                pass

            logger.info(f'Successfully parsed: {title}, {price} {currency}')

            # Prepare debug info
            debug_info = {
                'screenshots_taken': [
                    '/tmp/ozon_main_page.png',
                    '/tmp/ozon_product_page.png',
                    '/tmp/ozon_final_with_price.png'
                ],
                'price_extraction_method': 'JSON-LD' if 'JSON-LD' in str(price) else 'DOM/text',
                'page_loaded_successfully': True,
                'blocked': False
            }

            return ProductData(
                title=title, 
                price=price, 
                currency=currency, 
                url=url,
                screenshot_path='/tmp/ozon_final_with_price.png',
                debug_info=debug_info
            )

        except Exception as e:
            logger.error(f'Error fetching product from Ozon: {e}', exc_info=True)
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


