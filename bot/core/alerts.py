"""Alert management with deduplication and cooldown."""

from datetime import datetime, timedelta

from bot.core.clock import utcnow
from bot.core.config import settings
from bot.core.logging import get_logger
from bot.models.enums import ProviderEnum, ProviderStatus

logger = get_logger(__name__)


class AlertManager:
    """Manages provider health alerts with cooldown and deduplication."""

    def __init__(self) -> None:
        self.alerts_enabled = True
        self.last_alerts: dict[tuple[ProviderEnum, ProviderStatus], datetime] = {}

    def should_send_alert(self, provider: ProviderEnum, status: ProviderStatus) -> bool:
        """Check if alert should be sent based on cooldown."""
        if not self.alerts_enabled:
            return False

        key = (provider, status)
        last_alert_time = self.last_alerts.get(key)

        if last_alert_time is None:
            return True

        cooldown = timedelta(hours=settings.alert_cooldown_hours)
        return utcnow() - last_alert_time > cooldown

    def record_alert(self, provider: ProviderEnum, status: ProviderStatus) -> None:
        """Record that an alert was sent."""
        key = (provider, status)
        self.last_alerts[key] = utcnow()
        logger.info('Alert recorded', extra={'provider': provider.value, 'status': status.value})

    def enable_alerts(self) -> None:
        """Enable alerts."""
        self.alerts_enabled = True
        logger.info('Alerts enabled')

    def disable_alerts(self) -> None:
        """Disable alerts."""
        self.alerts_enabled = False
        logger.info('Alerts disabled')

    def reset(self) -> None:
        """Reset all alert history."""
        self.last_alerts.clear()
        logger.info('Alert history reset')


# Global alert manager instance
alert_manager = AlertManager()
