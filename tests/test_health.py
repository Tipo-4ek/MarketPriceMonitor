"""Tests for the provider health state machine."""

from datetime import timedelta

import pytest

from bot.core.clock import utcnow
from bot.core.providers.health import HealthMonitor
from bot.models.enums import ProviderEnum, ProviderStatus

OZON = ProviderEnum.OZON


@pytest.fixture
def monitor():
    return HealthMonitor()


def test_a_fresh_provider_is_ok(monitor):
    assert monitor.get_status(OZON) is ProviderStatus.OK


def test_errors_escalate_through_degraded_to_down(monitor, isolated_settings):
    # threshold 5 => DEGRADED at 2 (threshold // 2), DOWN at 5
    monitor.record_error(OZON, 'blocked')
    assert monitor.get_status(OZON) is ProviderStatus.OK

    monitor.record_error(OZON, 'blocked')
    assert monitor.get_status(OZON) is ProviderStatus.DEGRADED

    for _ in range(3):
        monitor.record_error(OZON, 'blocked')
    assert monitor.get_status(OZON) is ProviderStatus.DOWN


def test_a_success_clears_the_status(monitor, isolated_settings):
    for _ in range(5):
        monitor.record_error(OZON, 'blocked')
    assert monitor.get_status(OZON) is ProviderStatus.DOWN

    monitor.errors[OZON].clear()
    monitor.record_success(OZON)
    assert monitor.get_status(OZON) is ProviderStatus.OK


def test_expiring_errors_alone_does_not_announce_a_recovery(monitor, isolated_settings):
    """The regression that made 'provider restored' fire for a dead provider.

    A provider that has only ever failed must not be reported OK just because
    its errors aged out of the sliding window — otherwise every window rollover
    looks like a recovery and admins are told the marketplace came back when it
    has never worked once.
    """
    for _ in range(5):
        monitor.record_error(OZON, 'blocked')
    assert monitor.get_status(OZON) is ProviderStatus.DOWN

    # Age every recorded error out of the window without any success.
    old = utcnow() - timedelta(seconds=isolated_settings.provider_error_window_seconds + 60)
    monitor.errors[OZON] = type(monitor.errors[OZON])((old, 'blocked') for _ in range(5))

    assert monitor.get_status(OZON) is ProviderStatus.DOWN

    # Only an actual success returns it to OK.
    monitor.record_success(OZON)
    assert monitor.get_status(OZON) is ProviderStatus.OK


def test_reset_clears_everything(monitor, isolated_settings):
    for _ in range(5):
        monitor.record_error(OZON, 'blocked')
    monitor.set_previous_status(OZON, ProviderStatus.DOWN)

    monitor.reset()

    assert monitor.get_status(OZON) is ProviderStatus.OK
    assert monitor.get_previous_status(OZON) is None


def test_statuses_are_tracked_per_provider(monitor, isolated_settings):
    for _ in range(5):
        monitor.record_error(OZON, 'blocked')

    assert monitor.get_status(OZON) is ProviderStatus.DOWN
    assert monitor.get_status(ProviderEnum.WILDBERRIES) is ProviderStatus.OK
