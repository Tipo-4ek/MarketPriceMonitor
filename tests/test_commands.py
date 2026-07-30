"""The command menu, the /help text and the handlers must agree.

Telegram shows users the menu from `setMyCommands`. If that list, the `/help`
body and the registered handlers are maintained separately they drift, and the
user is offered a command that does nothing or never told about one that works.
These tests make the drift a failing build instead of a support question.
"""

from functools import cache

from aiogram import Dispatcher
from aiogram.filters import Command

from bot.core.commands import ADMIN_COMMANDS, ALL_COMMANDS, USER_COMMANDS, command_reference
from bot.core.i18n import TRANSLATIONS
from bot.handlers import setup_handlers
from bot.handlers.common import help_text

LOCALES = tuple(TRANSLATIONS)


@cache
def registered_commands() -> frozenset[str]:
    """Every command string the bot actually has a handler for.

    Cached because the routers are module-level singletons: aiogram refuses to
    attach one to a second Dispatcher, so this may only run once per process.
    Going through setup_handlers keeps it honest — the set comes from the same
    wiring the bot itself uses, not from a list repeated here.
    """
    dispatcher = Dispatcher()
    setup_handlers(dispatcher)

    found: set[str] = set()
    routers = [dispatcher, *dispatcher.sub_routers]
    while routers:
        router = routers.pop()
        routers.extend(getattr(router, 'sub_routers', []))
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
