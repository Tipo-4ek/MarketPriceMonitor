"""URL parsing utilities."""

import re
from urllib.parse import urlparse


def extract_product_id(url: str) -> str | None:
    """Extract product ID from URL if possible."""
    # Try various patterns
    patterns = [
        r'/product/[^/]+-(\d+)',  # Ozon
        r'_(\d+)$',  # Wildberries
        r'/(\d+)$',  # Generic
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def is_valid_url(url: str) -> bool:
    """Check if string is a valid URL."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False
