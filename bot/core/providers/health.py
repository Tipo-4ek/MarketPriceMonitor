"""Provider health monitoring."""

from collections import deque
from datetime import datetime, timedelta

from bot.core.clock import utcnow
from bot.core.config import settings
from bot.models.enums import ProviderEnum, ProviderStatus


class HealthMonitor:
    """Track provider failures over a sliding window and derive a status."""

    def __init__(self):
        self.errors: dict[ProviderEnum, deque] = {provider: deque() for provider in ProviderEnum}
        self.last_success: dict[ProviderEnum, datetime] = {}
        self.last_error: dict[ProviderEnum, datetime] = {}
        self.previous_status: dict[ProviderEnum, ProviderStatus] = {}
        self._reported: dict[ProviderEnum, ProviderStatus] = {}

    def record_success(self, provider: ProviderEnum) -> None:
        """Record a successful provider call."""
        self.last_success[provider] = utcnow()

    def record_error(self, provider: ProviderEnum, error: str) -> None:
        """Record a provider error."""
        now = utcnow()
        self.errors[provider].append((now, error))
        self.last_error[provider] = now
        self._clean_old_errors(provider)

    def get_status(self, provider: ProviderEnum) -> ProviderStatus:
        """Get current provider health status."""
        self._clean_old_errors(provider)
        error_count = len(self.errors[provider])

        if error_count >= settings.provider_error_threshold:
            status = ProviderStatus.DOWN
        elif error_count >= max(1, settings.provider_error_threshold // 2):
            status = ProviderStatus.DEGRADED
        else:
            status = ProviderStatus.OK

        if status is ProviderStatus.OK and not self._has_recovered(provider):
            # The window emptied because the errors aged out, not because
            # anything worked. Reporting OK here would announce a recovery for a
            # provider that may never have succeeded once.
            return self._reported.get(provider, ProviderStatus.OK)

        self._reported[provider] = status
        return status

    def _has_recovered(self, provider: ProviderEnum) -> bool:
        """True when a success is more recent than the last recorded failure."""
        last_error = self.last_error.get(provider)
        if last_error is None:
            return True
        last_success = self.last_success.get(provider)
        return last_success is not None and last_success > last_error

    def get_previous_status(self, provider: ProviderEnum) -> ProviderStatus | None:
        """Get previous status."""
        return self.previous_status.get(provider)

    def set_previous_status(self, provider: ProviderEnum, status: ProviderStatus) -> None:
        """Set previous status."""
        self.previous_status[provider] = status

    def _clean_old_errors(self, provider: ProviderEnum) -> None:
        """Remove errors outside the time window."""
        cutoff = utcnow() - timedelta(seconds=settings.provider_error_window_seconds)

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
        self.last_error.clear()
        self.previous_status.clear()
        self._reported.clear()


# Global health monitor instance
health_monitor = HealthMonitor()
