"""The command menu, the /help text and the handlers must agree.

Telegram shows users the menu from `setMyCommands`. If that list, the `/help`
body and the registered handlers are maintained separately they drift, and the
user is offered a command that does nothing or never told about one that works.
These tests make the drift a failing build instead of a support question.
"""

from functools import cache

from aiogram.filters import Command

from bot.core.commands import ADMIN_COMMANDS, ALL_COMMANDS, USER_COMMANDS, command_reference
from bot.core.i18n import TRANSLATIONS
from bot.handlers import admin, common, monitor, tracking
from bot.handlers.common import help_text

LOCALES = tuple(TRANSLATIONS)

# The module-level routers the bot wires together. Inspected directly rather
# than through a Dispatcher: a router is a singleton that can be attached to
# exactly one Dispatcher per process, and building one here would collide with
# the shared dispatcher the integration tests use.
_ROUTERS = (common.router, tracking.router, monitor.router, admin.router)


@cache
def registered_commands() -> frozenset[str]:
    """Every command string the bot actually has a handler for.

    Read from the same routers the bot itself includes, so it stays honest — the
    set comes from the real wiring, not from a list repeated here.
    """
    found: set[str] = set()
    for router in _ROUTERS:
        for handler in router.message.handlers:
            for handler_filter in handler.filters or ():
                callback = getattr(handler_filter, 'callback', None)
                if isinstance(callback, Command):
                    found.update(str(command) for command in callback.commands)
    return frozenset(found)


def test_every_declared_command_has_a_handler():
    declared = {spec.command for spec in ALL_COMMANDS}
    missing = declared - registered_commands()
    assert not missing, f'declared in commands.py but no handler exists: {sorted(missing)}'


def test_every_handled_command_is_declared():
    declared = {spec.command for spec in ALL_COMMANDS}
    undeclared = registered_commands() - declared
    assert not undeclared, f'a handler exists but the command is not declared: {sorted(undeclared)}'


def test_user_and_admin_lists_do_not_overlap():
    user = {spec.command for spec in USER_COMMANDS}
    admin = {spec.command for spec in ADMIN_COMMANDS}
    assert not (user & admin)


def test_every_command_is_described_in_every_locale():
    for spec in ALL_COMMANDS:
        for locale in LOCALES:
            description = spec.description(locale)
            assert description, f'{spec.command} has no description for {locale}'
            # Telegram rejects command descriptions longer than 256 characters.
            assert len(description) <= 256


def test_help_lists_exactly_the_user_commands():
    body = command_reference('ru', include_admin=False)
    for spec in USER_COMMANDS:
        assert f'/{spec.command}' in body
    for spec in ADMIN_COMMANDS:
        assert f'/{spec.command}' not in body


def test_help_for_admins_adds_the_admin_commands():
    body = command_reference('ru', include_admin=True)
    for spec in ALL_COMMANDS:
        assert f'/{spec.command}' in body


def test_help_text_is_assembled_for_both_locales():
    for locale in LOCALES:
        text = help_text(locale, include_admin=False)
        assert TRANSLATIONS[locale]['help_header'] in text
        assert TRANSLATIONS[locale]['help_footer'] in text
        assert '/add [url]' in text


def test_usage_shows_the_arguments_a_command_takes():
    usages = {spec.command: spec.usage() for spec in ALL_COMMANDS}
    assert usages['add'] == '/add [url]'
    assert usages['monitor'] == '/monitor [set <id> <delta>]'
    # A command with no arguments must not render a trailing space.
    assert usages['list'] == '/list'


class _RecordingBot:
    """Records set_my_commands calls the way register_bot_commands makes them."""

    def __init__(self):
        self.calls: list[dict] = []

    async def set_my_commands(self, commands, scope=None, language_code=None):
        self.calls.append({'scope': type(scope).__name__, 'language_code': language_code, 'n': len(commands)})


async def test_register_bot_commands_publishes_every_scope(isolated_settings):
    from bot.core.commands import register_bot_commands

    bot = _RecordingBot()
    await register_bot_commands(bot)

    # Two default-scope publications (en + ru), and per admin two more.
    default_calls = [c for c in bot.calls if c['scope'] == 'BotCommandScopeDefault']
    admin_calls = [c for c in bot.calls if c['scope'] == 'BotCommandScopeChat']
    assert len(default_calls) == 2
    assert len(admin_calls) == 2 * len(isolated_settings.admin_ids)
    # The admin scope carries the full command set, the default only the user one.
    assert all(c['n'] == len(ALL_COMMANDS) for c in admin_calls)
    assert all(c['n'] == len(USER_COMMANDS) for c in default_calls)


async def test_register_bot_commands_survives_a_telegram_failure(isolated_settings, monkeypatch):
    import bot.core.commands as commands_module

    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr(commands_module.asyncio, 'sleep', _instant_sleep)

    class BrokenBot:
        async def set_my_commands(self, *a, **k):
            raise RuntimeError('telegram down')

    # It retries and swallows: publishing the menu is a nicety, not a reason to
    # fail startup. The call returns without raising.
    await commands_module.register_bot_commands(BrokenBot())
