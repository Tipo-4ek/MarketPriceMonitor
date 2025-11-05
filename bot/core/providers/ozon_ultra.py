"""Ultra-advanced Ozon provider with latest bypass techniques."""
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

# Try to import different browser automation libraries
try:
    from playwright.async_api import async_playwright
    from playwright_stealth import stealth_async
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

try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False


class OzonUltraProvider(Provider):
    """
    Ultra-advanced Ozon provider with latest bypass techniques.
    
    This provider uses the most advanced methods to bypass Ozon's anti-bot protection:
    1. Undetected ChromeDriver with advanced stealth
    2. Direct API access with proper headers
    3. Mobile emulation with realistic behavior
    4. Proxy rotation with session management
    5. Advanced fingerprint masking
    """

    def __init__(self):
        self.proxy_provider = None
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
        """Normalize Ozon URL."""
        # Extract product ID and return clean URL
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
        """Fetch product data using ultra-advanced bypass techniques."""
        strategies = [
            ("Undetected ChromeDriver", self._fetch_with_undetected_chrome),
            ("Direct API Access", self._fetch_with_direct_api),
            ("Mobile Emulation", self._fetch_with_mobile_emulation),
            ("Stealth Playwright", self._fetch_with_stealth_playwright),
        ]
        
        # Filter available strategies
        available_strategies = []
        for name, method in strategies:
            if name == "Undetected ChromeDriver" and UNDETECTED_AVAILABLE:
                available_strategies.append((name, method))
            elif name == "Direct API Access":
                available_strategies.append((name, method))
            elif name == "Mobile Emulation" and PLAYWRIGHT_AVAILABLE:
                available_strategies.append((name, method))
            elif name == "Stealth Playwright" and PLAYWRIGHT_AVAILABLE:
                available_strategies.append((name, method))
        
        if not available_strategies:
            raise ValueError("No browser automation libraries available.")
        
        logger.info(f"Available strategies: {[s[0] for s in available_strategies]}")
        
        # Try each strategy until one succeeds
        last_error = None
        for strategy_name, strategy_method in available_strategies:
            try:
                logger.info(f"🔄 Trying strategy: {strategy_name}")
                result = await strategy_method(url)
                logger.info(f"✅ Success with strategy: {strategy_name}")
                return result
            except Exception as e:
                logger.warning(f"❌ Strategy {strategy_name} failed: {e}")
                last_error = e
                continue
        
        # If all strategies failed
        raise ValueError(f"All strategies failed. Last error: {last_error}")

    async def _fetch_with_undetected_chrome(self, url: str) -> ProductData:
        """Fetch using undetected-chromedriver with advanced stealth."""
        if not UNDETECTED_AVAILABLE:
            raise ImportError("undetected-chromedriver not available")
        
        driver = None
        try:
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
            
            # Configure undetected Chrome options
            options = uc.ChromeOptions()
            
            # Advanced anti-detection arguments
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-plugins")
            options.add_argument("--disable-web-security")
            options.add_argument("--disable-features=IsolateOrigins,site-per-process")
            options.add_argument("--disable-background-timer-throttling")
            options.add_argument("--disable-backgrounding-occluded-windows")
            options.add_argument("--disable-renderer-backgrounding")
            options.add_argument("--disable-field-trial-config")
            options.add_argument("--disable-ipc-flooding-protection")
            options.add_argument("--disable-hang-monitor")
            options.add_argument("--disable-prompt-on-repost")
            options.add_argument("--disable-sync")
            options.add_argument("--disable-translate")
            options.add_argument("--disable-logging")
            options.add_argument("--disable-gpu-logging")
            options.add_argument("--silent")
            options.add_argument("--log-level=3")
            options.add_argument("--disable-default-apps")
            options.add_argument("--disable-component-extensions-with-background-pages")
            options.add_argument("--disable-background-networking")
            options.add_argument("--disable-sync-preferences")
            options.add_argument("--disable-default-apps")
            options.add_argument("--disable-component-update")
            options.add_argument("--disable-domain-reliability")
            options.add_argument("--disable-features=TranslateUI")
            options.add_argument("--disable-ipc-flooding-protection")
            options.add_argument("--disable-hang-monitor")
            options.add_argument("--disable-prompt-on-repost")
            options.add_argument("--disable-sync")
            options.add_argument("--disable-translate")
            options.add_argument("--disable-logging")
            options.add_argument("--disable-gpu-logging")
            options.add_argument("--silent")
            options.add_argument("--log-level=3")
            options.add_argument("--disable-default-apps")
            options.add_argument("--disable-component-extensions-with-background-pages")
            options.add_argument("--disable-background-networking")
            options.add_argument("--disable-sync-preferences")
            options.add_argument("--disable-default-apps")
            options.add_argument("--disable-component-update")
            options.add_argument("--disable-domain-reliability")
            options.add_argument("--disable-features=TranslateUI")
            
            # Mobile viewport
            options.add_argument("--window-size=375,667")
            
            # Set mobile user agent
            mobile_user_agent = (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            )
            options.add_argument(f"--user-agent={mobile_user_agent}")
            
            # Add proxy if configured
            if proxy_config:
                proxy_url = proxy_config['server']
                if proxy_config.get('username') and proxy_config.get('password'):
                    proxy_url = f"http://{proxy_config['username']}:{proxy_config['password']}@{proxy_url.replace('http://', '')}"
                options.add_argument(f"--proxy-server={proxy_url}")
            
            # Create undetected Chrome driver
            driver = uc.Chrome(options=options, version_main=None)
            
            # Set timeouts
            driver.implicitly_wait(20)
            driver.set_page_load_timeout(60)
            
            # Advanced fingerprint masking
            driver.execute_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US', 'en']});
                Object.defineProperty(navigator, 'platform', {get: () => 'iPhone'});
                Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});
                Object.defineProperty(screen, 'width', {get: () => 375});
                Object.defineProperty(screen, 'height', {get: () => 667});
                Object.defineProperty(screen, 'availWidth', {get: () => 375});
                Object.defineProperty(screen, 'availHeight', {get: () => 667});
                Object.defineProperty(screen, 'colorDepth', {get: () => 24});
                Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
                window.chrome = undefined;
                window.navigator.chrome = undefined;
            """)
            
            # Navigate with human-like behavior
            logger.info(f"Navigating to: {url}")
            driver.get(url)
            
            # Human-like delays
            time.sleep(random.uniform(3, 6))
            
            # Check for blocking
            page_text = driver.page_source[:1000].lower()
            if "cloudflare" in page_text or "access denied" in page_text or "challenge" in page_text:
                raise ValueError("Anti-bot protection detected")
            
            # Wait for page to load
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # Additional human-like behavior
            driver.execute_script("window.scrollTo(0, 100);")
            time.sleep(random.uniform(1, 2))
            driver.execute_script("window.scrollTo(0, 200);")
            time.sleep(random.uniform(1, 2))
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(random.uniform(1, 2))
            
            # Extract data
            return await self._extract_product_data_from_html(driver.page_source, url)
            
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    async def _fetch_with_direct_api(self, url: str) -> ProductData:
        """Fetch using direct API access with proper headers."""
        import aiohttp
        
        # Extract article number
        article = self._extract_article_from_url(url)
        if not article:
            raise ValueError(f"Could not extract article number from URL: {url}")
        
        # Build API URL
        api_url = f"https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{article}/"
        
        # Get proxy for this request
        proxy_url = None
        if self.proxy_provider and self.proxy_provider.has_proxies():
            proxy_dict = self.proxy_provider.get_random_proxy()
            if proxy_dict:
                proxy_url = proxy_dict['server']
                if proxy_dict.get('username') and proxy_dict.get('password'):
                    proxy_url = f"http://{proxy_dict['username']}:{proxy_dict['password']}@{proxy_url.replace('http://', '')}"
                logger.info(f"🔒 Using proxy: {proxy_dict['server']}")
        
        # Advanced headers to mimic real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.ozon.ru/',
            'Origin': 'https://www.ozon.ru',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'DNT': '1',
            'Sec-CH-UA': '"Not_A Brand";v="8", "Chromium";v="120", "Safari";v="16"',
            'Sec-CH-UA-Mobile': '?1',
            'Sec-CH-UA-Platform': '"iOS"',
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url,
                    headers=headers,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"API returned status {response.status}")
                    
                    data = await response.json()
                    
                    # Extract data from API response
                    widget_states = data.get('widgetStates', {})
                    if not widget_states:
                        raise ValueError("No widgetStates in API response")
                    
                    # Extract price
                    price = None
                    for key, value in widget_states.items():
                        if key.startswith('webPrice-') and isinstance(value, str):
                            try:
                                price_data = json.loads(value)
                                if price_data.get('isAvailable', False):
                                    card_price = price_data.get('cardPrice', '')
                                    if card_price:
                                        price = Decimal(re.sub(r'[^\d]', '', card_price))
                                        break
                            except (json.JSONDecodeError, ValueError):
                                continue
                    
                    if not price:
                        raise ValueError("Could not extract price from API response")
                    
                    # Extract title
                    title = None
                    for key, value in widget_states.items():
                        if key.startswith('webProductHeading-') and isinstance(value, str):
                            try:
                                heading_data = json.loads(value)
                                title = heading_data.get('title')
                                if title:
                                    break
                            except (json.JSONDecodeError, KeyError):
                                continue
                    
                    if not title:
                        title = f"Product {article}"
                    
                    logger.info(f"Successfully parsed via API: {title}, {price} RUB")
                    
                    return ProductData(
                        title=title,
                        price=price,
                        currency='RUB',
                        url=url
                    )
                    
        except Exception as e:
            logger.error(f"Direct API fetch failed: {e}")
            raise

    async def _fetch_with_mobile_emulation(self, url: str) -> ProductData:
        """Fetch using mobile emulation with realistic behavior."""
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
            
            # Launch browser with mobile emulation
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extensions',
                    '--disable-plugins',
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
                ],
            )
            
            # Create mobile context
            context_options = {
                'viewport': {'width': 375, 'height': 667},
                'user_agent': (
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
                ),
                'locale': 'ru-RU',
                'timezone_id': 'Europe/Moscow',
                'extra_http_headers': {
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                },
            }
            
            if proxy_config:
                context_options['proxy'] = proxy_config
            
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            # Apply stealth
            await stealth_async(page)
            
            # Advanced mobile fingerprint masking
            await page.add_init_script("""
                Object.defineProperty(navigator, 'platform', { get: () => 'iPhone' });
                Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
                Object.defineProperty(screen, 'width', { get: () => 375 });
                Object.defineProperty(screen, 'height', { get: () => 667 });
                Object.defineProperty(screen, 'availWidth', { get: () => 375 });
                Object.defineProperty(screen, 'availHeight', { get: () => 667 });
                Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
                Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
                window.chrome = undefined;
                window.navigator.chrome = undefined;
            """)
            
            # Navigate with human-like behavior
            logger.info(f"Navigating to mobile version: {url}")
            
            # First visit main page to establish session
            try:
                await page.goto('https://www.ozon.ru/', wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(random.uniform(2, 4))
                await page.evaluate('window.scrollTo(0, 100)')
                await asyncio.sleep(random.uniform(1, 2))
            except Exception:
                pass
            
            # Navigate to product page
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(random.uniform(2, 4))
            
            # Check for blocking
            page_text = await page.evaluate('() => document.body.innerText')
            if 'Доступ ограничен' in page_text or 'Access denied' in page_text:
                raise ValueError("Mobile version blocked")
            
            # Human-like scrolling
            await page.evaluate('window.scrollTo(0, 100)')
            await asyncio.sleep(random.uniform(1, 2))
            await page.evaluate('window.scrollTo(0, 200)')
            await asyncio.sleep(random.uniform(1, 2))
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(random.uniform(1, 2))
            
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

    async def _fetch_with_stealth_playwright(self, url: str) -> ProductData:
        """Fetch using stealth Playwright with advanced techniques."""
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
            
            # Launch browser with advanced stealth
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extensions',
                    '--disable-plugins',
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
                ],
            )
            
            # Create context with realistic settings
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'locale': 'ru-RU',
                'timezone_id': 'Europe/Moscow',
                'extra_http_headers': {
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                },
            }
            
            if proxy_config:
                context_options['proxy'] = proxy_config
            
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            # Apply stealth
            await stealth_async(page)
            
            # Advanced fingerprint masking
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US', 'en']});
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
            
            # First visit main page to establish session
            try:
                await page.goto('https://www.ozon.ru/', wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(random.uniform(3, 5))
                await page.evaluate('window.scrollTo(0, 500)')
                await asyncio.sleep(random.uniform(2, 3))
                await page.evaluate('window.scrollTo(0, 1000)')
                await asyncio.sleep(random.uniform(2, 4))
            except Exception:
                pass
            
            # Navigate to product page
            await page.goto(url, wait_until='networkidle', timeout=40000)
            await asyncio.sleep(random.uniform(2, 4))
            
            # Check for blocking
            page_text = await page.evaluate('() => document.body.innerText')
            if 'Доступ ограничен' in page_text or 'Access denied' in page_text:
                raise ValueError("Access denied - anti-bot detected")
            
            # Human-like scrolling and interaction
            await page.mouse.move(100, 100)
            await asyncio.sleep(random.uniform(0.3, 0.5))
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 3)')
            await asyncio.sleep(random.uniform(1, 2))
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
            await asyncio.sleep(random.uniform(1, 2))
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(random.uniform(1, 2))
            
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
        
        # Fallback to regex extraction
        title = None
        price = None
        
        # Extract title
        title_patterns = [
            r'<h1[^>]*>(.*?)</h1>',
            r'<title[^>]*>(.*?)</title>',
            r'"name":\s*"([^"]+)"',
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                title = match.group(1).strip()
                if title and len(title) > 3:
                    break
        
        # Extract price
        price_patterns = [
            r'(\d+(?:\s*\d*)*)\s*₽',
            r'(\d+(?:\s*\d*)*)\s*руб',
            r'"price":\s*"?(\d+)"?',
            r'"cardPrice":\s*"?(\d+)"?',
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                try:
                    price_str = match.replace(' ', '').replace('\xa0', '')
                    test_price = Decimal(price_str)
                    if 10 < test_price < 10000000:  # Reasonable price range
                        price = test_price
                        break
                except Exception:
                    continue
            if price:
                break
        
        if not title:
            title = "Unknown Product"
        
        if not price:
            raise ValueError("Could not extract price from page")
        
        return ProductData(title=title, price=price, currency='RUB', url=url)
