#!/usr/bin/env python3
"""Local provider test script.

This script tests the provider functionality when running locally (not in Docker).
It works correctly when executed directly on the host system.

Usage:
    python run_provider_test_local.py
"""

import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.core.providers.ozon import OzonProvider


async def test_provider_local():
    """Test provider parsing locally - works when NOT running in Docker."""
    # Example product URL
    url = 'https://www.ozon.ru/product/3d-printer-bambu-lab-p1s-combo-with-ams-evropeyskaya-versiya-1966858370/'
    
    print("Provider Test (Local Execution)")
    print("=" * 60)
    print(f"URL: {url}")
    print()
    
    try:
        provider = OzonProvider()
        print("🔄 Fetching product data...")
        result = await provider.fetch_product(url)
        
        print(f"✅ Success!")
        print(f"  Title: {result.title}")
        print(f"  Price: {result.price} {result.currency}")
        
        if result.screenshot_path:
            print(f"  Screenshot: {result.screenshot_path}")
        
        if result.debug_info:
            print(f"  Debug info: {result.debug_info}")
        
        # Check if screenshots exist
        screenshots = [
            '/tmp/ozon_main_page.png',
            '/tmp/ozon_product_page.png',
            '/tmp/ozon_final_with_price.png'
        ]
        
        print("\n📸 Screenshot status:")
        for screenshot in screenshots:
            if os.path.exists(screenshot):
                size = os.path.getsize(screenshot)
                print(f"  ✅ {screenshot} ({size} bytes)")
            else:
                print(f"  ❌ {screenshot} (not found)")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_provider_local())
