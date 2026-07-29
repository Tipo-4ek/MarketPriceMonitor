"""Provider health monitoring."""

from collections import deque
from datetime import datetime, timedelta

from bot.core.clock import utcnow
from bot.core.config import settings
from bot.models.enums import ProviderEnum, ProviderStatus


class HealthMonitor:
    """Monitor provider health based on success/error rates."""

    def __init__(self):
        self.errors: dict[ProviderEnum, deque] = {provider: deque() for provider in ProviderEnum}
        self.last_success: dict[ProviderEnum, datetime] = {}
        self.previous_status: dict[ProviderEnum, ProviderStatus] = {}

    def record_success(self, provider: ProviderEnum) -> None:
        """Record a successful provider call."""
        self.last_success[provider] = utcnow()

    def record_error(self, provider: ProviderEnum, error: str) -> None:
        """Record a provider error."""
        self.errors[provider].append((utcnow(), error))
        self._clean_old_errors(provider)

    def get_status(self, provider: ProviderEnum) -> ProviderStatus:
        """Get current provider health status."""
        self._clean_old_errors(provider)
        error_count = len(self.errors[provider])

        if error_count == 0:
            return ProviderStatus.OK

        if error_count >= settings.provider_error_threshold:
            return ProviderStatus.DOWN

        if error_count >= settings.provider_error_threshold // 2:
            return ProviderStatus.DEGRADED

        return ProviderStatus.OK

    def get_previous_status(self, provider: ProviderEnum) -> ProviderStatus | None:
        """Get previous status."""
        return self.previous_status.get(provider)

    def set_previous_status(self, provider: ProviderEnum, status: ProviderStatus) -> None:
        """Set previous status."""
        self.previous_status[provider] = status

    def _clean_old_errors(self, provider: ProviderEnum) -> None:
        """Remove errors outside the time window."""
        window = timedelta(seconds=settings.provider_error_window_seconds)
        cutoff = utcnow() - window

        while self.errors[provider] and self.errors[provider][0][0] < cutoff:
            self.errors[provider].popleft()

    def get_all_statuses(self) -> dict[ProviderEnum, ProviderStatus]:
        """Get status for all providers."""
        return {provider: self.get_status(provider) for provider in ProviderEnum}

    def reset(self) -> None:
        """Reset all health data."""
        for provider in ProviderEnum:
            self.errors[provider].clear()
        self.last_success.clear()
        self.previous_status.clear()


# Global health monitor instance
health_monitor = HealthMonitor()
