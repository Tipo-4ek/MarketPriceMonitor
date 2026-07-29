"""Single source of "now".

Every timestamp in this project is timezone-aware UTC. Routing them through one
helper keeps model defaults, the provider error window and the alert cooldown on
the same clock: mixing naive and aware datetimes does not fail loudly at the
boundary, it fails later at the comparison, which is a miserable bug to chase.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)
