"""URL parsing utilities."""

from urllib.parse import urlparse


def is_valid_url(url: str) -> bool:
    """Check if string is a valid URL."""
    try:
        result = urlparse(url)
    except ValueError:
        return False
    return bool(result.scheme and result.netloc)
