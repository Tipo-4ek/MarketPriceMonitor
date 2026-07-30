"""Tests for the provider health state machine."""

from datetime import timedelta

import pytest

from bot.core.clock import utcnow
from bot.core.providers.health import HealthMonitor
from bot.models.enums import ProviderEnum, ProviderStatus

WB = ProviderEnum.WILDBERRIES


@pytest.fixture
def monitor():
    return HealthMonitor()


def test_a_fresh_provider_is_ok(monitor):
    assert monitor.get_status(WB) is ProviderStatus.OK


def test_errors_escalate_through_degraded_to_down(monitor, isolated_settings):
    # threshold 5 => DEGRADED at 2 (threshold // 2), DOWN at 5
    monitor.record_error(WB, 'blocked')
    assert monitor.get_status(WB) is ProviderStatus.OK

    monitor.record_error(WB, 'blocked')
    assert monitor.get_status(WB) is ProviderStatus.DEGRADED

    for _ in range(3):
        monitor.record_error(WB, 'blocked')
    assert monitor.get_status(WB) is ProviderStatus.DOWN


def test_a_success_clears_the_status(monitor, isolated_settings):
    for _ in range(5):
        monitor.record_error(WB, 'blocked')
    assert monitor.get_status(WB) is ProviderStatus.DOWN

    monitor.errors[WB].clear()
    monitor.record_success(WB)
    assert monitor.get_status(WB) is ProviderStatus.OK


def test_expiring_errors_alone_does_not_announce_a_recovery(monitor, isolated_settings):
    """The regression that made 'provider restored' fire for a dead provider.

    A provider that has only ever failed must not be reported OK just because
    its errors aged out of the sliding window — otherwise every window rollover
    looks like a recovery and admins are told the marketplace came back when it
    has never worked once.
    """
    for _ in range(5):
        monitor.record_error(WB, 'blocked')
    assert monitor.get_status(WB) is ProviderStatus.DOWN

    # Age every recorded error out of the window without any success.
    old = utcnow() - timedelta(seconds=isolated_settings.provider_error_window_seconds + 60)
    monitor.errors[WB] = type(monitor.errors[WB])((old, 'blocked') for _ in range(5))

    assert monitor.get_status(WB) is ProviderStatus.DOWN

    # Only an actual success returns it to OK.
    monitor.record_success(WB)
    assert monitor.get_status(WB) is ProviderStatus.OK


def test_reset_clears_everything(monitor, isolated_settings):
    for _ in range(5):
        monitor.record_error(WB, 'blocked')
    monitor.set_previous_status(WB, ProviderStatus.DOWN)

    monitor.reset()

    assert monitor.get_status(WB) is ProviderStatus.OK
    assert monitor.get_previous_status(WB) is None


def test_status_is_looked_up_per_provider(monitor, isolated_settings):
    """Health is kept per provider, keyed by the enum.

    Isolation between two providers cannot be asserted while only one
    marketplace has a working implementation; this test grows a second
    assertion when the next provider lands.
    """
    for _ in range(5):
        monitor.record_error(WB, 'blocked')

    assert monitor.get_status(WB) is ProviderStatus.DOWN
    assert set(monitor.get_all_statuses()) == set(ProviderEnum)
