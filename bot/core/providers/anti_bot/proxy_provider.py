"""Proxy provider with rotation support."""

import random
from pathlib import Path
from typing import Dict

from bot.core.logging import get_logger

logger = get_logger(__name__)


class ProxyProvider:
    """Provider for proxy rotation with pool management."""

    def __init__(self, proxy_url: str | None = None, proxy_file: str | None = None):
        """
        Initialize proxy provider.

        Args:
            proxy_url: Single proxy URL (format: http://user:pass@host:port or host:port:user:pass)
            proxy_file: Path to file with proxy list (one proxy per line)
        """
        self.proxy_url = proxy_url
        self.proxy_file = proxy_file
        self.proxy_pool: list[Dict[str, str]] = []
        self.current_index = 0

        # Load proxy pool if file is provided
        if proxy_file:
            self._load_proxy_pool(proxy_file)
        elif proxy_url:
            # Single proxy - parse and add to pool
            parsed = self._parse_proxy(proxy_url)
            if parsed:
                self.proxy_pool.append(parsed)

    def _parse_proxy(self, proxy_str: str) -> Dict[str, str] | None:
        """
        Parse proxy string to dict.

        Supports formats:
        - host:port:user:pass
        - http://user:pass@host:port
        """
        proxy_str = proxy_str.strip()
        if not proxy_str:
            return None

        try:
            # Format: host:port:user:pass
            if proxy_str.count(':') == 3 and not proxy_str.startswith('http'):
                parts = proxy_str.split(':')
                return {
                    'server': f'http://{parts[0]}:{parts[1]}',
                    'username': parts[2],
                    'password': parts[3],
                }
            # Format: http://user:pass@host:port or https://user:pass@host:port
            elif '@' in proxy_str and (proxy_str.startswith('http://') or proxy_str.startswith('https://')):
                # Extract scheme
                scheme = 'http://' if proxy_str.startswith('http://') else 'https://'
                proxy_str = proxy_str.replace(scheme, '')

                # Split user:pass@host:port
                if '@' in proxy_str:
                    auth, server = proxy_str.split('@', 1)
                    user, password = auth.split(':', 1)
                    return {
                        'server': f'{scheme}{server}',
                        'username': user,
                        'password': password,
                    }
            # Format: http://host:port (no auth)
            elif proxy_str.startswith('http://') or proxy_str.startswith('https://'):
                return {
                    'server': proxy_str,
                    'username': None,
                    'password': None,
                }
        except Exception:
            # Do not log the raw proxy string — it may contain credentials.
            logger.warning('Failed to parse a proxy entry; skipping it')
            return None

        return None

    def _load_proxy_pool(self, proxy_file: str):
        """Load proxy list from file."""
        try:
            proxy_path = Path(proxy_file)
            if not proxy_path.exists():
                logger.warning('Proxy file not found: %s', proxy_file)
                return

            with open(proxy_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parsed = self._parse_proxy(line)
                if parsed:
                    self.proxy_pool.append(parsed)

            logger.info('Loaded %d proxies from %s', len(self.proxy_pool), proxy_file)

        except Exception as e:
            logger.warning('Error loading proxy file: %s', e)

    def get_proxy(self) -> Dict[str, str] | None:
        """
        Get next proxy from pool (round-robin).

        Returns:
            Dict with 'server', 'username', 'password' or None
        """
        if not self.proxy_pool:
            return None

        # Round-robin rotation
        proxy = self.proxy_pool[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxy_pool)

        return proxy

    def get_random_proxy(self) -> Dict[str, str] | None:
        """
        Get random proxy from pool.

        Returns:
            Dict with 'server', 'username', 'password' or None
        """
        if not self.proxy_pool:
            return None

        return random.choice(self.proxy_pool)

    def has_proxies(self) -> bool:
        """Check if proxy pool is not empty."""
        return len(self.proxy_pool) > 0

    def pool_size(self) -> int:
        """Get size of proxy pool."""
        return len(self.proxy_pool)
