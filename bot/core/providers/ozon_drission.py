"""Ozon provider using DrissionPage for Cloudflare bypass."""
import asyncio
import json
import random
import re
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    DRISSION_AVAILABLE = True
except ImportError:
    DRISSION_AVAILABLE = False

from bot.core.config import settings
from bot.core.logging import get_logger
from bot.core.providers.base import Provider, ProductData
from bot.models.enums import ProviderEnum

logger = get_logger(__name__)


class OzonDrissionProvider(Provider):
    """
    Ozon provider using DrissionPage for better Cloudflare bypass.
    
    DrissionPage is specifically designed to bypass anti-bot systems
    including Cloudflare protection.
    """

    def __init__(self):
        self.page = None
        
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

    def _build_ozon_api_url(self, article: int) -> str:
        """Build Ozon internal JSON API URL."""
        base_url = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"
        product_url = f"/product/{article}/"
        return f"{base_url}?url={product_url}"

    async def _setup_page(self):
        """Setup DrissionPage with anti-detection measures."""
        if self.page:
            return
            
        if not DRISSION_AVAILABLE:
            raise ImportError("DrissionPage not available. Install with: pip install DrissionPage")
            
        try:
            # Configure Chromium options for anti-detection
            options = ChromiumOptions()
            
            # Anti-detection arguments
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-plugins")
            options.add_argument("--disable-web-security")
            options.add_argument("--disable-features=IsolateOrigins,site-per-process")
            
            # Run in headless mode
            options.headless(True)
            
            # Mobile viewport (appears as mobile user)
            options.set_window_size(375, 667)
            
            # Set user agent to mobile
            mobile_user_agent = (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            )
            options.set_user_agent(mobile_user_agent)
            
            # Create page
            self.page = ChromiumPage(addr_or_opts=options)
            
            # Set timeouts
            self.page.set.timeouts(page_load=30, script=20)
            
            logger.info("✅ DrissionPage initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize DrissionPage: {e}")
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
        """Fetch product data from Ozon using DrissionPage."""
        try:
            # Extract article number
            article = self._extract_article_from_url(url)
            if not article:
                raise ValueError(f"Could not extract article number from URL: {url}")
            
            logger.info(f"Fetching Ozon product {article} via DrissionPage")
            
            # Setup page
            await self._setup_page()
            
            # Build API URL
            api_url = self._build_ozon_api_url(article)
            logger.info(f"API URL: {api_url}")
            
            # Navigate to API URL
            loop = asyncio.get_event_loop()
            page_source = await loop.run_in_executor(None, self._fetch_page, api_url)
            
            # Extract JSON from response
            json_content = self._extract_json_from_html(page_source)
            if not json_content:
                raise ValueError("Could not extract JSON from API response")
            
            logger.debug(f"JSON content length: {len(json_content)}")
            
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
            await self._close_page()

    def _fetch_page(self, url: str) -> str:
        """Fetch page using DrissionPage (blocking operation)."""
        import time
        
        try:
            logger.info(f"Navigating to: {url}")
            
            # Navigate with human-like behavior
            self.page.get(url)
            
            # Random delay
            time.sleep(random.uniform(2, 4))
            
            # Check if blocked
            page_title = self.page.title
            page_text = self.page.html[:1000].lower()
            
            if "cloudflare" in page_text or "access denied" in page_text or "challenge" in page_text:
                logger.error(f"Detected blocking: page title={page_title}")
                logger.error("Cloudflare or anti-bot protection detected")
                
                # Wait longer to see if challenge resolves
                logger.info("Waiting 15 seconds for challenge resolution...")
                time.sleep(15)
                
                # Check again
                page_text = self.page.html[:1000].lower()
                if "cloudflare" in page_text or "access denied" in page_text or "challenge" in page_text:
                    raise ValueError("Anti-bot protection detected - could not bypass")
            
            # Wait for page to load
            self.page.wait.load_start()
            
            return self.page.html
            
        except Exception as e:
            logger.error(f"Error fetching page: {e}")
            raise ValueError(f"Failed to fetch page: {e}")

    async def _close_page(self):
        """Close page and cleanup."""
        if self.page:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.page.quit)
                logger.info("DrissionPage closed successfully")
            except Exception as e:
                logger.error(f"Error closing DrissionPage: {e}")
            finally:
                self.page = None
