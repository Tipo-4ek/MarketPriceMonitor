"""Enhanced Ozon provider with multiple bypass strategies."""
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
from bot.core.providers.anti_bot.user_agent_pool import UserAgentPool
from bot.core.providers.base import Provider, ProductData
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)

# Try to import different browser automation libraries
try:
    from playwright.async_api import async_playwright
    from playwright_stealth import stealth
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    DRISSION_AVAILABLE = True
except ImportError:
    DRISSION_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from selenium_stealth import stealth
    SELENIUM_STEALTH_AVAILABLE = True
except ImportError:
    SELENIUM_STEALTH_AVAILABLE = False


class OzonEnhancedProvider(Provider):
    """
    Enhanced Ozon provider with multiple bypass strategies.
    
    This provider tries different methods in order:
    1. DrissionPage with mobile viewport (best for Cloudflare bypass)
    2. Playwright with stealth and proxy rotation
    3. Selenium with undetected-chromedriver
    4. Mobile version fallback
    """

    def __init__(self):
        self.proxy_provider = None
        self.user_agent_pool = UserAgentPool()
        self._initialize_proxy_provider()
        
    def _initialize_proxy_provider(self):
        """Initialize proxy provider with rotation support."""
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
        """Normalize Ozon URL - keep full URL for better compatibility."""
        # Keep the original URL as-is to avoid getting wrong product pages
        # The short format /product/-{id}/ can sometimes return different products
        return url

    def _extract_article_from_url(self, url: str) -> Optional[int]:
        """Extract article number from Ozon URL."""
        match = re.search(r'/product/.*?-?(\d+)/?$', url)
        if match:
            return int(match.group(1))
        return None

    async def fetch_product(self, url: str) -> ProductData:
        """Fetch product data using multiple strategies."""
        strategies = [
            ("Playwright Stealth", self._fetch_with_playwright_stealth),
            ("DrissionPage Mobile", self._fetch_with_drission_mobile),
            ("Selenium Undetected", self._fetch_with_selenium_undetected),
        ]
        
        # Filter available strategies
        available_strategies = []
        for name, method in strategies:
            if name == "DrissionPage Mobile" and DRISSION_AVAILABLE:
                available_strategies.append((name, method))
            elif name == "Playwright Stealth" and PLAYWRIGHT_AVAILABLE:
                available_strategies.append((name, method))
            elif name == "Selenium Undetected" and SELENIUM_AVAILABLE:
                available_strategies.append((name, method))
        
        if not available_strategies:
            raise ValueError("No browser automation libraries available. Install playwright, DrissionPage, or selenium.")
        
        print(f"Available strategies: {[s[0] for s in available_strategies]}")
        logger.info(f"Available strategies: {[s[0] for s in available_strategies]}")
        
        # Try each strategy until one succeeds
        last_error = None
        for strategy_name, strategy_method in available_strategies:
            try:
                print(f"🔄 Trying strategy: {strategy_name}")
                logger.info(f"🔄 Trying strategy: {strategy_name}")
                result = await strategy_method(url)
                print(f"✅ Success with strategy: {strategy_name}")
                logger.info(f"✅ Success with strategy: {strategy_name}")
                return result
            except Exception as e:
                print(f"❌ Strategy {strategy_name} failed: {e}")
                logger.warning(f"❌ Strategy {strategy_name} failed: {e}")
                last_error = e
                continue
        
        # If all strategies failed
        raise ValueError(f"All strategies failed. Last error: {last_error}")

    async def _fetch_with_drission_mobile(self, url: str) -> ProductData:
        """Fetch using DrissionPage with mobile viewport."""
        if not DRISSION_AVAILABLE:
            raise ImportError("DrissionPage not available")
        
        page = None
        try:
            # Configure Chromium options for mobile - using new API
            options = ChromiumOptions()
            
            # Use new API methods
            options.set_argument("--no-sandbox")
            options.set_argument("--disable-dev-shm-usage")
            options.set_argument("--disable-blink-features=AutomationControlled")
            options.set_argument("--disable-extensions")
            options.set_argument("--disable-plugins")
            options.set_argument("--disable-web-security")
            options.set_argument("--disable-features=IsolateOrigins,site-per-process")
            options.headless(True)
            
            # Desktop viewport for better compatibility
            options.set_argument("--window-size=1920,1080")
            options.set_user_agent(self.user_agent_pool.get_random())
            options.set_argument("--lang=ru-RU")
            
            # Add proxy if available (only without auth for DrissionPage)
            if self.proxy_provider and self.proxy_provider.has_proxies():
                proxy_dict = self.proxy_provider.get_random_proxy()
                if proxy_dict and not proxy_dict.get('username') and not proxy_dict.get('password'):
                    proxy_url = proxy_dict['server']
                    options.set_proxy(proxy_url)
                    logger.info(f"🔒 Using proxy: {proxy_dict['server']}")
                else:
                    logger.info("Skipping proxy for DrissionPage (auth not supported)")
            
            page = ChromiumPage(addr_or_opts=options)
            page.set.timeouts(page_load=30, script=20)
            
            # Navigate to page
            logger.info(f"Navigating to: {url}")
            page.get(url)
            
            # Wait and check for blocking
            time.sleep(random.uniform(3, 5))
            
            page_text = page.html[:1000].lower()
            logger.info(f"Page text sample: {page_text[:200]}...")
            if "cloudflare" in page_text or "access denied" in page_text or "challenge" in page_text:
                logger.warning("Cloudflare protection detected")
                raise ValueError("Cloudflare protection detected")
            
            # Wait for page to load
            logger.info("Waiting for page to load...")
            page.wait.load_start()
            logger.info("Page loaded successfully")
            
            # Take screenshot
            try:
                page.get_screenshot(path='/tmp/ozon_drission_page.png')
                logger.info('Screenshot saved to /tmp/ozon_drission_page.png')
            except Exception as e:
                logger.debug(f'Could not take screenshot: {e}')
            
            # Log page content for debugging
            logger.info(f'Page content length: {len(page.html)}')
            logger.info(f'Page title: {page.title}')
            
            # Extract data
            return await self._extract_product_data_from_html(page.html, url)
            
        finally:
            if page:
                try:
                    page.quit()
                except Exception:
                    pass

    async def _fetch_with_playwright_stealth(self, url: str) -> ProductData:
        """Fetch using Playwright with stealth and proxy."""
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
            
            # Launch browser with anti-detection
            browser = await playwright.chromium.launch(
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
            
            # Create context with realistic settings
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': self.user_agent_pool.get_random(),
                'locale': 'ru-RU',
                'timezone_id': 'Europe/Moscow',
                'extra_http_headers': {
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1',
                },
            }
            
            if proxy_config:
                context_options['proxy'] = proxy_config
            
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            # Apply stealth (commented out as it's for Selenium, not Playwright)
            # await stealth(page)
            
            # Additional anti-detection
            await page.add_init_script("""
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
            
            # Navigate with human-like behavior
            logger.info(f"Navigating to: {url}")
            
            # First visit main page
            try:
                await page.goto('https://www.ozon.ru/', wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(random.uniform(3, 5))
                await page.evaluate('window.scrollTo(0, 500)')
                await asyncio.sleep(random.uniform(2, 3))
            except Exception:
                pass
            
            # Navigate to product page
            await page.goto(url, wait_until='networkidle', timeout=40000)
            await asyncio.sleep(random.uniform(2, 4))
            
            # Check for blocking
            page_text = await page.evaluate('() => document.body.innerText')
            if 'Доступ ограничен' in page_text or 'Access denied' in page_text:
                # Take screenshot of blocked page
                try:
                    await page.screenshot(path='/tmp/ozon_playwright_blocked.png')
                    logger.info('Screenshot of blocked page saved to /tmp/ozon_playwright_blocked.png')
                except Exception:
                    pass
                raise ValueError("Access denied - anti-bot detected")
            
            # Take screenshot
            try:
                await page.screenshot(path='/tmp/ozon_playwright_page.png')
                logger.info('Screenshot saved to /tmp/ozon_playwright_page.png')
            except Exception as e:
                logger.debug(f'Could not take screenshot: {e}')
            
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

    async def _fetch_with_selenium_undetected(self, url: str) -> ProductData:
        """Fetch using Selenium with undetected-chromedriver."""
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium not available")
        
        driver = None
        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument(f"--user-agent={self.user_agent_pool.get_random()}")
            chrome_options.add_argument("--lang=ru-RU")
            
            # Add proxy if available
            if self.proxy_provider and self.proxy_provider.has_proxies():
                proxy_dict = self.proxy_provider.get_random_proxy()
                if proxy_dict:
                    proxy_url = proxy_dict['server']
                    if proxy_dict.get('username') and proxy_dict.get('password'):
                        proxy_url = f"http://{proxy_dict['username']}:{proxy_dict['password']}@{proxy_url.replace('http://', '')}"
                    chrome_options.add_argument(f'--proxy-server={proxy_url}')
                    logger.info(f"🔒 Using proxy: {proxy_dict['server']}")
            
            # Use webdriver-manager to automatically download and manage ChromeDriver
            service = Service(ChromeDriverManager().install())
            
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Apply stealth if available
            if SELENIUM_STEALTH_AVAILABLE:
                stealth(
                    driver,
                    languages=["ru-RU", "ru"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True
                )
            
            driver.implicitly_wait(20)
            driver.set_page_load_timeout(60)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Navigate
            logger.info(f"Navigating to: {url}")
            driver.get(url)
            
            time.sleep(random.uniform(3, 5))
            
            # Check for blocking
            page_text = driver.page_source[:1000].lower()
            if "cloudflare" in page_text or "access denied" in page_text or "challenge" in page_text:
                raise ValueError("Cloudflare protection detected")
            
            # Wait for page load
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # Extract data
            return await self._extract_product_data_from_html(driver.page_source, url)
            
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    async def _fetch_with_mobile_version(self, url: str) -> ProductData:
        """Fetch using mobile version of Ozon."""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright not available")
        
        # Convert to mobile URL
        match = re.search(r'/product/.*?-?(\d+)/?$', url)
        if match:
            product_id = match.group(1)
            mobile_url = f'https://m.ozon.ru/product/-{product_id}/'
        else:
            mobile_url = url.replace('www.ozon.ru', 'm.ozon.ru')
        
        playwright = None
        browser = None
        page = None
        
        try:
            playwright = await async_playwright().start()
            
            browser = await playwright.chromium.launch(
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
            
            # Mobile context
            context = await browser.new_context(
                viewport={'width': 375, 'height': 667},
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
            
            page = await context.new_page()
            # Apply stealth (commented out as it's for Selenium, not Playwright)
            # await stealth(page)
            
            # Mobile-specific anti-detection
            await page.add_init_script("""
                Object.defineProperty(navigator, 'platform', { get: () => 'iPhone' });
                Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
                Object.defineProperty(screen, 'width', { get: () => 375 });
                Object.defineProperty(screen, 'height', { get: () => 667 });
                window.chrome = undefined;
            """)
            
            logger.info(f"Navigating to mobile version: {mobile_url}")
            await page.goto(mobile_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(random.uniform(2, 4))
            
            # Check for blocking
            page_text = await page.evaluate('() => document.body.innerText')
            if 'Доступ ограничен' in page_text or 'Access denied' in page_text:
                raise ValueError("Mobile version blocked")
            
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
        logger.info(f'Extracting data from HTML content of length: {len(html_content)}')
        
        # First, try to extract price "по карте Озон" from aspects data
        try:
            import re
            # Look for price in aspects data (this is the "по карте Озон" price)
            # Pattern: "price":"654 ₽" in aspects data - look for the one that's not in JSON-LD
            # First find all price patterns, then filter out JSON-LD ones
            all_price_matches = re.findall(r'"price":"(\d+)\s*₽"', html_content)
            logger.info(f'Found all price matches: {all_price_matches}')
            if all_price_matches:
                # Get the first price that's not 724 (which is the regular price)
                for price_str in all_price_matches:
                    price_val = int(price_str)
                    logger.info(f'Checking price: {price_val}')
                    if price_val != 724:  # Skip the regular price
                        logger.info(f'Found non-regular price: {price_val}')
                        card_price = Decimal(price_str)
                        logger.info(f'Found Ozon Card price: {card_price}')
                        
                        # Also try to find regular price for comparison
                        regular_price = None
                        json_ld_match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_content, re.DOTALL)
                        if json_ld_match:
                            try:
                                json_data = json.loads(json_ld_match.group(1))
                                if isinstance(json_data, dict) and 'offers' in json_data:
                                    offers = json_data['offers']
                                    if isinstance(offers, dict) and 'price' in offers:
                                        regular_price = Decimal(str(offers['price']))
                                    elif isinstance(offers, list) and len(offers) > 0 and 'price' in offers[0]:
                                        regular_price = Decimal(str(offers[0]['price']))
                            except Exception:
                                pass
                        
                        # Extract title
                        title = self._extract_title_from_html(html_content)
                        
                        # Use Ozon Card price as main price, regular price in parentheses
                        if regular_price and regular_price != card_price:
                            formatted_price = f"{card_price} (без карты Озон - {regular_price} руб)"
                        else:
                            formatted_price = str(card_price)
                        
                        return ProductData(title=title, price=card_price, currency='RUB', url=url, raw_html=html_content)
                else:
                    logger.info('No non-regular price found')
            else:
                logger.info('No price matches found')
        except Exception as e:
            logger.debug(f'Failed to extract Ozon Card price: {e}')
        
        # Fallback to JSON-LD extraction (regular price)
        try:
            import re
            json_ld_match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_content, re.DOTALL)
            if json_ld_match:
                logger.info('Found JSON-LD data, attempting to parse...')
                json_data = json.loads(json_ld_match.group(1))
                if isinstance(json_data, dict) and 'offers' in json_data:
                    offers = json_data['offers']
                    if isinstance(offers, dict) and 'price' in offers:
                        price = Decimal(str(offers['price']))
                        title = json_data.get('name', 'Unknown Product')
                        return ProductData(title=title, price=price, currency='RUB', url=url, raw_html=html_content)
                    elif isinstance(offers, list) and len(offers) > 0 and 'price' in offers[0]:
                        price = Decimal(str(offers[0]['price']))
                        title = json_data.get('name', 'Unknown Product')
                        return ProductData(title=title, price=price, currency='RUB', url=url, raw_html=html_content)
        except Exception:
            pass
        
        # Fallback to regex extraction
        logger.info('JSON-LD extraction failed, trying regex patterns...')
        title = None
        price = None
        
        # Extract title with more comprehensive patterns
        title_patterns = [
            # Ozon-specific selectors
            r'<h1[^>]*data-widget="webProductHeading"[^>]*>(.*?)</h1>',
            r'<div[^>]*data-widget="webProductHeading"[^>]*>.*?<h1[^>]*>(.*?)</h1>',
            r'<h1[^>]*class="[^"]*ProductHeading[^"]*"[^>]*>(.*?)</h1>',
            r'<h1[^>]*class="[^"]*tsHeadline[^"]*"[^>]*>(.*?)</h1>',
            # Generic patterns
            r'<h1[^>]*>(.*?)</h1>',
            r'<title[^>]*>(.*?)</title>',
            # JSON patterns
            r'"name":\s*"([^"]+)"',
            r'"title":\s*"([^"]+)"',
            r'"productName":\s*"([^"]+)"',
            # Meta tags
            r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
            r'<meta[^>]*name="title"[^>]*content="([^"]+)"',
        ]
        
        for i, pattern in enumerate(title_patterns):
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                title = match.group(1).strip()
                # Clean up HTML entities and tags
                title = re.sub(r'<[^>]+>', '', title)  # Remove HTML tags
                title = re.sub(r'&[a-zA-Z0-9#]+;', ' ', title)  # Replace HTML entities
                title = title.strip()
                if title and len(title) > 3:
                    logger.info(f'Found title with pattern {i+1}: {title[:100]}...')
                    break
            else:
                logger.debug(f'Title pattern {i+1} failed: {pattern[:50]}...')
        
        # Extract price with more comprehensive patterns
        price_patterns = [
            # Ozon-specific patterns
            r'(\d{1,3}(?:\s\d{3})*)\s*₽',
            r'(\d{1,3}(?:\s\d{3})*)\s*руб',
            r'(\d{1,3}(?:\s\d{3})*)\s*рублей',
            r'(\d{1,3}(?:\s\d{3})*)\s*р\.',
            # JSON patterns
            r'"price":\s*"?(\d+)"?',
            r'"cardPrice":\s*"?(\d+)"?',
            r'"currentPrice":\s*"?(\d+)"?',
            r'"priceValue":\s*"?(\d+)"?',
            # Generic patterns
            r'(\d+)\s*₽',
            r'(\d+)\s*руб',
            # Price ranges
            r'от\s+(\d{1,3}(?:\s\d{3})*)',
            r'от\s+(\d+)',
        ]
        
        for i, pattern in enumerate(price_patterns):
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            logger.debug(f'Price pattern {i+1} found {len(matches)} matches: {pattern[:50]}...')
            for match in matches:
                try:
                    price_str = match.replace(' ', '').replace('\xa0', '').replace(',', '.')
                    test_price = Decimal(price_str)
                    if 10 < test_price < 100000000:  # Extended price range for expensive items
                        price = test_price
                        logger.info(f'Found price with pattern {i+1}: {price}')
                        break
                except Exception as e:
                    logger.debug(f'Failed to parse price "{match}": {e}')
                    continue
            if price:
                break
        
        if not title:
            title = "Unknown Product"
        
        if not price:
            raise ValueError("Could not extract price from page")
        
        return ProductData(title=title, price=price, currency='RUB', url=url, raw_html=html_content)
    
    def _extract_title_from_html(self, html_content: str) -> str:
        """Extract product title from HTML content."""
        import re
        
        # Extract title with more comprehensive patterns
        title_patterns = [
            # Ozon-specific selectors
            r'<h1[^>]*data-widget="webProductHeading"[^>]*>(.*?)</h1>',
            r'<div[^>]*data-widget="webProductHeading"[^>]*>.*?<h1[^>]*>(.*?)</h1>',
            r'<h1[^>]*class="[^"]*ProductHeading[^"]*"[^>]*>(.*?)</h1>',
            r'<h1[^>]*class="[^"]*tsHeadline[^"]*"[^>]*>(.*?)</h1>',
            # Generic patterns
            r'<h1[^>]*>(.*?)</h1>',
            r'<title[^>]*>(.*?)</title>',
            # JSON patterns
            r'"name":\s*"([^"]+)"',
            r'"title":\s*"([^"]+)"',
            r'"productName":\s*"([^"]+)"',
            # Meta tags
            r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
            r'<meta[^>]*name="title"[^>]*content="([^"]+)"',
        ]
        
        for i, pattern in enumerate(title_patterns):
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                title = match.group(1).strip()
                # Clean up HTML entities and tags
                title = re.sub(r'<[^>]+>', '', title)  # Remove HTML tags
                title = re.sub(r'&[a-zA-Z0-9#]+;', ' ', title)  # Replace HTML entities
                title = title.strip()
                if title and len(title) > 3:
                    logger.info(f'Found title with pattern {i+1}: {title[:100]}...')
                    return title
        
        return "Unknown Product"

