"""The startup configuration guard: fail fast, and legibly."""

import pytest

from bot.core.config import ConfigError, settings, validate_runtime_settings


@pytest.fixture
def valid_settings(monkeypatch):
    """A configuration that passes, as a baseline for the negative cases."""
    monkeypatch.setattr(settings, 'bot_token', '123:abc')
    monkeypatch.setattr(settings, 'admin_tg_ids', '1,2,3')
    monkeypatch.setattr(settings, 'poll_interval_seconds', 900)
    monkeypatch.setattr(settings, 'provider_error_threshold', 5)
    monkeypatch.setattr(settings, 'provider_error_window_seconds', 7200)
    return settings


def test_passes_with_a_valid_configuration(valid_settings):
    validate_runtime_settings()  # does not raise


def test_missing_bot_token_is_rejected(valid_settings, monkeypatch):
    monkeypatch.setattr(settings, 'bot_token', '')
    with pytest.raises(ConfigError, match='BOT_TOKEN'):
        validate_runtime_settings()


def test_non_numeric_admin_ids_are_rejected_at_startup(valid_settings, monkeypatch):
    monkeypatch.setattr(settings, 'admin_tg_ids', '1,notanumber,3')
    with pytest.raises(ConfigError, match='ADMIN_TG_IDS'):
        validate_runtime_settings()


def test_error_window_must_outlast_the_accumulation_time(valid_settings, monkeypatch):
    # threshold 5, interval 900 -> need > 3600; 3600 is the boundary and fails.
    monkeypatch.setattr(settings, 'provider_error_window_seconds', 3600)
    with pytest.raises(ConfigError, match='PROVIDER_ERROR_WINDOW_SECONDS'):
        validate_runtime_settings()


def test_empty_admin_ids_is_allowed(valid_settings, monkeypatch):
    monkeypatch.setattr(settings, 'admin_tg_ids', '')
    validate_runtime_settings()  # no admins is a valid, if quiet, configuration
    assert settings.admin_ids == []
