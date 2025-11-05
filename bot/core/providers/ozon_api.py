"""Ozon provider implementation using undetected-chromedriver and JSON API."""
import asyncio
import json
import random
import re
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException

try:
    from selenium_stealth import stealth
except ImportError:
    stealth = None

try:
    import undetected_chromedriver as uc
except ImportError:
    uc = None

from bot.core.config import settings
from bot.core.logging import get_logger
from bot.core.providers.base import Provider, ProductData
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)


class OzonAPIProvider(Provider):
    """
    Ozon marketplace provider using direct API access with undetected-chromedriver.
    
    This implementation bypasses Ozon anti-bot protection by:
    1. Using undetected-chromedriver instead of regular Playwright
    2. Accessing Ozon's internal JSON API directly
    3. Using selenium-stealth for additional masking
    4. Using mobile viewport to appear as a mobile user
    """

    def __init__(self):
        self.driver = None
        
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
        # Match patterns like:
        # /product/158761892/ (just number)
        # /product/-1383823095/ (dash + number)
        # /product/product-name-1383823095/ (name-number)
        match = re.search(r'/product/.*?-?(\d+)/?$', url)
        if match:
            return int(match.group(1))
        return None

    def _build_ozon_api_url(self, article: int) -> str:
        """Build Ozon internal JSON API URL."""
        base_url = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"
        product_url = f"/product/{article}/"
        return f"{base_url}?url={product_url}"

    async def _setup_driver(self):
        """Setup undetected Chrome driver with anti-detection measures."""
        if self.driver:
            return
            
        try:
            from selenium.webdriver.chrome.service import Service
            
            chrome_options = Options()
            
            # Anti-detection arguments
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            
            # Run in headless mode
            chrome_options.add_argument("--headless=new")
            
            # Mobile viewport (appears as mobile user)
            chrome_options.add_argument("--window-size=375,667")
            
            # Use system chromium (installed in Docker)
            chrome_options.binary_location = "/usr/bin/chromium"
            
            # Use chromium-driver from system
            service = Service(executable_path="/usr/bin/chromedriver")
            
            # Use regular Chrome driver with system chromium
            logger.info("Using Selenium with system Chromium and chromedriver")
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Apply selenium-stealth if available
            if stealth and self.driver:
                stealth(
                    self.driver,
                    languages=["ru-RU", "ru"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True
                )
                logger.info("Applied selenium-stealth")
            
            # Set timeouts
            self.driver.implicitly_wait(20)
            self.driver.set_page_load_timeout(60)
            
            # Override webdriver property
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("✅ Chrome driver initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise

    def _extract_json_from_html(self, html_content: str) -> Optional[str]:
        """Extract JSON from HTML response."""
        try:
            # Look for JSON in <pre> tag
            pre_pattern = r'<pre[^>]*>(.*?)</pre>'
            pre_match = re.search(pre_pattern, html_content, re.DOTALL | re.IGNORECASE)
            
            if pre_match:
                json_content = pre_match.group(1).strip()
                logger.debug("Found JSON in <pre> tag")
                return json_content
            
            # Fallback: find JSON by braces
            first_brace = html_content.find('{')
            last_brace = html_content.rfind('}')
            
            if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
                json_content = html_content[first_brace:last_brace + 1]
                logger.debug("Found JSON by brace search")
                return json_content
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting JSON from HTML: {e}")
            return None

    def _find_web_price_property(self, widget_states: dict) -> Optional[str]:
        """Find webPrice property in widget states."""
        for key, value in widget_states.items():
            if key.startswith('webPrice-') and isinstance(value, str):
                return value
        return None

    def _find_product_title(self, widget_states: dict) -> Optional[str]:
        """Find product title in widget states."""
        for key, value in widget_states.items():
            if key.startswith('webProductHeading-') and isinstance(value, str):
                try:
                    heading_data = json.loads(value)
                    title = heading_data.get('title')
                    if title:
                        return title
                except (json.JSONDecodeError, KeyError):
                    continue
        return None

    def _extract_price_from_string(self, price_str: str) -> Optional[Decimal]:
        """Extract price from string, removing all non-numeric characters."""
        if not price_str:
            return None
        
        cleaned = re.sub(r'[^\d]', '', price_str)
        
        try:
            return Decimal(cleaned) if cleaned else None
        except Exception:
            return None

    async def fetch_product(self, url: str) -> ProductData:
        """Fetch product data from Ozon using JSON API."""
        try:
            # Extract article number
            article = self._extract_article_from_url(url)
            if not article:
                raise ValueError(f"Could not extract article number from URL: {url}")
            
            logger.info(f"Fetching Ozon product {article} via JSON API")
            
            # Setup driver
            await self._setup_driver()
            
            # Build API URL
            api_url = self._build_ozon_api_url(article)
            logger.info(f"API URL: {api_url}")
            
            # Navigate to API URL in a separate thread (Selenium is blocking)
            loop = asyncio.get_event_loop()
            page_source = await loop.run_in_executor(None, self._fetch_page, api_url)
            
            # Extract JSON from response
            json_content = self._extract_json_from_html(page_source)
            if not json_content:
                raise ValueError("Could not extract JSON from API response")
            
            logger.debug(f"JSON content length: {len(json_content)}")
            logger.debug(f"JSON first 500 chars: {json_content[:500]}")
            
            # Parse JSON
            try:
                data = json.loads(json_content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                logger.error(f"JSON content sample: {json_content[:1000]}")
                raise ValueError(f"Invalid JSON response: {e}")
            
            widget_states = data.get('widgetStates', {})
            
            if not widget_states:
                raise ValueError("No widgetStates in JSON response")
            
            logger.info(f"Found {len(widget_states)} widgets in response")
            
            # Extract price
            web_price_value = self._find_web_price_property(widget_states)
            if not web_price_value:
                raise ValueError("Could not find webPrice property in widgetStates")
            
            price_json = json.loads(web_price_value)
            is_available = price_json.get('isAvailable', False)
            
            if not is_available:
                raise ValueError("Product is not available")
            
            # Parse prices
            card_price = self._extract_price_from_string(price_json.get('cardPrice', ''))
            price = self._extract_price_from_string(price_json.get('price', ''))
            original_price = self._extract_price_from_string(price_json.get('originalPrice', ''))
            
            # Use cardPrice if available, otherwise price
            final_price = card_price or price
            if not final_price:
                raise ValueError("Could not extract price from response")
            
            logger.info(f"Price extracted: {final_price} (cardPrice: {card_price}, price: {price})")
            
            # Extract title
            title = self._find_product_title(widget_states)
            if not title:
                raise ValueError("Could not find product title")
            
            logger.info(f"Successfully parsed: {title}, {final_price} RUB")
            
            return ProductData(
                title=title,
                price=final_price,
                currency='RUB',
                url=url
            )
            
        except Exception as e:
            logger.error(f"Error fetching product from Ozon: {e}", exc_info=True)
            raise
        finally:
            await self._close_driver()

    def _fetch_page(self, url: str) -> str:
        """Fetch page using Selenium (blocking operation)."""
        try:
            logger.info(f"Navigating to: {url}")
            self.driver.get(url)
            
            # Small random delay
            import time
            time.sleep(random.uniform(2, 4))
            
            # Check if blocked
            page_title = self.driver.title
            page_text = self.driver.page_source[:1000].lower()
            
            if "cloudflare" in page_text or "access denied" in page_text or "challenge" in page_text:
                logger.error(f"Detected blocking: page title={page_title}")
                logger.error("Cloudflare or anti-bot protection detected")
                
                # Wait longer to see if challenge resolves
                logger.info("Waiting 10 seconds for challenge resolution...")
                time.sleep(10)
                
                # Check again
                page_text = self.driver.page_source[:1000].lower()
                if "cloudflare" in page_text or "access denied" in page_text or "challenge" in page_text:
                    raise ValueError("Anti-bot protection detected - could not bypass")
            
            # Wait for page to load
            WebDriverWait(self.driver, 15).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            return self.driver.page_source
            
        except TimeoutException:
            raise ValueError(f"Timeout while loading URL")
        except WebDriverException as e:
            raise ValueError(f"WebDriver error: {e}")

    async def _close_driver(self):
        """Close driver and cleanup."""
        if self.driver:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.driver.quit)
                logger.info("Driver closed successfully")
            except Exception as e:
                logger.error(f"Error closing driver: {e}")
            finally:
                self.driver = None

