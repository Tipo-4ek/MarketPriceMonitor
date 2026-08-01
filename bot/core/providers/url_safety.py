"""What the bot is allowed to fetch.

The generic provider opens links from anyone, so a link is fetched only if it
points at an ordinary public website — never at the host's own network. Two
checks:

* :func:`is_safe_url` — cheap and non-resolving: the scheme is http(s), and the
  host is not localhost, a ``.local`` / ``.internal`` name, or a literal address
  in a private, loopback, link-local, reserved, multicast or unspecified range.
  Used as an early reject and as a provider's ``supports`` check.

* :func:`is_fetchable` — the gate on the fetch path: the cheap checks plus DNS.
  The host is resolved and every resolved address is held to the same rules, so a
  name cannot stand in for an internal address. A deployment's own domains and
  public IP (``BLOCKED_HOSTS``) are refused too, and a name that will not resolve
  is not fetched.

The generic provider re-runs :func:`is_fetchable` on every fetch and against the
address the page actually reached; the Wildberries provider only ever fetches its
own host.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Collection
from urllib.parse import urlparse

_BLOCKED_SUFFIXES = ('.local', '.internal', '.localhost')
_BLOCKED_NAMES = frozenset({'localhost'})
_RESOLVE_TIMEOUT_SECONDS = 5.0


def _host_of(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ('http', 'https'):
        return None
    return parsed.hostname.lower() if parsed.hostname else None


def _ip_is_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Collapse an IPv4-mapped IPv6 address (``::ffff:10.0.0.1``) to its IPv4 form
    # first, or it slips past the v4 range checks on some Python versions.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def is_safe_url(url: str) -> bool:
    """Cheap, non-resolving check: scheme, obvious names, literal-IP ranges."""
    host = _host_of(url)
    if host is None:
        return False
    if host in _BLOCKED_NAMES or host.endswith(_BLOCKED_SUFFIXES):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # a hostname — resolution is left to is_fetchable
    return not _ip_is_internal(ip)


def is_blocked_host(url: str, blocked: Collection[str]) -> bool:
    """True if the URL's host is in the deployment block list, or a subdomain of one."""
    host = _host_of(url)
    if host is None:
        return False
    if host in blocked:
        return True
    return any(isinstance(entry, str) and host.endswith(f'.{entry}') for entry in blocked)


async def _resolved_ips(host: str) -> list[str]:
    """Every address ``host`` resolves to (A and AAAA). Factored out so tests can stub it."""
    loop = asyncio.get_running_loop()
    infos = await asyncio.wait_for(
        loop.getaddrinfo(host, None, proto=socket.IPPROTO_TCP),
        timeout=_RESOLVE_TIMEOUT_SECONDS,
    )
    return [info[4][0].split('%')[0] for info in infos]  # drop any IPv6 scope id


async def is_fetchable(url: str, blocked: Collection[str]) -> bool:
    """Authoritative fetch-path check: the cheap checks, plus DNS resolution.

    Resolution failure is treated as unsafe: a name that cannot be vetted is not
    fetched.
    """
    if not is_safe_url(url) or is_blocked_host(url, blocked):
        return False
    host = _host_of(url)
    if host is None:
        return False
    try:
        ipaddress.ip_address(host)
        return True  # a literal address, already vetted by is_safe_url
    except ValueError:
        pass

    try:
        addresses = await _resolved_ips(host)
    except (TimeoutError, OSError, UnicodeError):
        return False
    if not addresses:
        return False
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if _ip_is_internal(ip) or addr in blocked or str(ip) in blocked:
            return False
    return True
