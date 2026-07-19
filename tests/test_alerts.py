"""Tests for alert system."""

from datetime import datetime, timedelta

from bot.core.alerts import AlertManager
from bot.models.enums import ProviderEnum, ProviderStatus


def test_alert_cooldown():
    """Test alert cooldown mechanism."""
    alert_manager = AlertManager()
    provider = ProviderEnum.OZON
    status = ProviderStatus.DOWN

    # First alert should be sent
    assert alert_manager.should_send_alert(provider, status) is True

    # Record the alert
    alert_manager.record_alert(provider, status)

    # Second alert should be suppressed (within cooldown)
    assert alert_manager.should_send_alert(provider, status) is False


def test_alert_different_status():
    """Test alerts for different statuses."""
    alert_manager = AlertManager()
    provider = ProviderEnum.OZON

    # Send DOWN alert
    alert_manager.record_alert(provider, ProviderStatus.DOWN)

    # DEGRADED alert should still be sent (different status)
    assert alert_manager.should_send_alert(provider, ProviderStatus.DEGRADED) is True


def test_alert_enable_disable():
    """Test enabling and disabling alerts."""
    alert_manager = AlertManager()
    provider = ProviderEnum.OZON
    status = ProviderStatus.DOWN

    # Disable alerts
    alert_manager.disable_alerts()
    assert alert_manager.should_send_alert(provider, status) is False

    # Enable alerts
    alert_manager.enable_alerts()
    assert alert_manager.should_send_alert(provider, status) is True


def test_alert_reset():
    """Test resetting alert history."""
    alert_manager = AlertManager()
    provider = ProviderEnum.OZON
    status = ProviderStatus.DOWN

    # Record alert
    alert_manager.record_alert(provider, status)
    assert alert_manager.should_send_alert(provider, status) is False

    # Reset
    alert_manager.reset()
    assert alert_manager.should_send_alert(provider, status) is True


def test_alert_cooldown_expired():
    """Test alert after cooldown expires."""
    alert_manager = AlertManager()
    alert_manager.alert_cooldown_hours = 0  # Set to 0 for testing
    provider = ProviderEnum.OZON
    status = ProviderStatus.DOWN

    # Record alert with old timestamp
    alert_manager.last_alerts[(provider, status)] = datetime.utcnow() - timedelta(hours=25)

    # Alert should be sent (cooldown expired)
    assert alert_manager.should_send_alert(provider, status) is True
