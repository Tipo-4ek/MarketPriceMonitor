"""Tests for Ozon provider."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from bot.core.providers.ozon import OzonProvider
from bot.core.providers.base import ProductData


@pytest.mark.asyncio
async def test_ozon_supports():
    """Test Ozon URL detection."""
    provider = OzonProvider()

    assert provider.supports('https://www.ozon.ru/product/test-123456/') is True
    assert provider.supports('https://ozon.ru/product/test-123456/') is True
    assert provider.supports('https://www.avito.ru/test') is False


@pytest.mark.asyncio
async def test_ozon_normalize():
    """Test Ozon URL normalization."""
    provider = OzonProvider()

    url = 'https://www.ozon.ru/product/test-product-name-123456/?some=params'
    normalized = await provider.normalize(url)

    assert normalized == 'https://www.ozon.ru/product/-123456/'


@pytest.mark.asyncio
async def test_ozon_fetch_product_mocked():
    """Test fetching product from Ozon with mocked Playwright."""
    provider = OzonProvider()
    
    # Mock Playwright components
    mock_page = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_playwright = AsyncMock()
    
    # Mock page navigation and selectors
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.evaluate = AsyncMock()
    mock_page.screenshot = AsyncMock()
    mock_page.content = AsyncMock(return_value='<html>test</html>')
    mock_page.close = AsyncMock()
    
    # Mock title element
    mock_title_element = AsyncMock()
    mock_title_element.inner_text = AsyncMock(return_value='Test iPhone 15 128GB')
    
    # Mock price element
    mock_price_element = AsyncMock()
    mock_price_element.inner_text = AsyncMock(return_value='79 990 ₽')
    
    # Setup query_selector to return title
    async def mock_query_selector(selector):
        if 'ProductHeading' in selector or 'h1' in selector:
            return mock_title_element
        return None
    
    # Setup query_selector_all to return price
    async def mock_query_selector_all(selector):
        if 'price' in selector.lower() or 'Price' in selector:
            return [mock_price_element]
        return []
    
    mock_page.query_selector = mock_query_selector
    mock_page.query_selector_all = mock_query_selector_all
    
    # Setup browser context
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    
    # Setup playwright
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_playwright.stop = AsyncMock()
    
    # Mock async_playwright
    with patch('bot.core.providers.ozon.async_playwright') as mock_async_pw:
        mock_pw_context = AsyncMock()
        mock_pw_context.start = AsyncMock(return_value=mock_playwright)
        mock_async_pw.return_value = mock_pw_context
        
        # Test fetch_product
        product_data = await provider.fetch_product('https://www.ozon.ru/product/-123456/')
        
        assert product_data.title == 'Test iPhone 15 128GB'
        assert product_data.price == Decimal('79990')
        assert product_data.currency == 'RUB'


@pytest.mark.asyncio
async def test_ozon_fetch_product_error_no_title():
    """Test error handling when title is not found."""
    provider = OzonProvider()
    
    # Mock Playwright components
    mock_page = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_playwright = AsyncMock()
    
    # Mock page navigation
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.evaluate = AsyncMock()
    mock_page.screenshot = AsyncMock()
    mock_page.content = AsyncMock(return_value='<html>test</html>')
    mock_page.close = AsyncMock()
    
    # Return None for title (not found)
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_page.query_selector_all = AsyncMock(return_value=[])
    
    # Setup browser context
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    
    # Setup playwright
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_playwright.stop = AsyncMock()
    
    # Mock async_playwright
    with patch('bot.core.providers.ozon.async_playwright') as mock_async_pw:
        mock_pw_context = AsyncMock()
        mock_pw_context.start = AsyncMock(return_value=mock_playwright)
        mock_async_pw.return_value = mock_pw_context
        
        # Test should raise ValueError
        with pytest.raises(ValueError, match='Could not parse product title'):
            await provider.fetch_product('https://www.ozon.ru/product/-123456/')


