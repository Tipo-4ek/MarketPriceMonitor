"""The bot's command list — one definition, three consumers.

Arguments are shown in square brackets because they are optional: tapping a
command in Telegram's menu sends it bare, and the bot then asks for what it
needs. Typing the whole thing on one line still works.

Telegram's command menu, the `/help` text and the handlers all have to agree.
Keeping three hand-written lists in step is exactly the kind of thing that
quietly drifts, so they are all derived from ``USER_COMMANDS`` and
``ADMIN_COMMANDS`` below, and a test asserts that every entry here has a
registered handler and every registered command appears here.

Admin commands are published per-admin using a chat scope, so a normal user's
menu does not advertise commands they will only be refused.
"""

import asyncio
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from bot.core.config import settings
from bot.core.logging import get_logger

logger = get_logger(__name__)

# Publishing the menu is a nicety, so it gets a short leash rather than
# aiogram's 60-second default: a slow Telegram once held startup for a full
# minute before giving up, which is a minute the bot answered nobody.
_PUBLISH_TIMEOUT_SECONDS = 12
_PUBLISH_ATTEMPTS = 3

# Telegram shows this language to clients set to Russian; everything else falls
# back to the default scope, which we publish in English.
_DEFAULT_MENU_LOCALE = 'en'
_MENU_LOCALES = ('en', 'ru')


@dataclass(frozen=True)
class CommandSpec:
    """One bot command, with what it takes and what it does."""

    command: str
    args: str
    descriptions: dict[str, str]

    def usage(self) -> str:
        """`/add <url>` — how the command is typed."""
        return f'/{self.command} {self.args}'.strip()

    def description(self, locale: str) -> str:
        return self.descriptions.get(locale, self.descriptions[_DEFAULT_MENU_LOCALE])


USER_COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec('start', '', {'ru': 'начать работу с ботом', 'en': 'start using the bot'}),
    CommandSpec('add', '[url]', {'ru': 'добавить товар по ссылке', 'en': 'track a product by link'}),
    CommandSpec('list', '', {'ru': 'мои отслеживаемые товары', 'en': 'my tracked products'}),
    CommandSpec('remove', '[id]', {'ru': 'убрать товар из отслеживания', 'en': 'stop tracking a product'}),
    CommandSpec(
        'monitor',
        '[set <id> <delta>]',
        {'ru': 'порог изменения цены для товара, %', 'en': 'price-change threshold for a product, %'},
    ),
    CommandSpec('lang', '[ru|en]', {'ru': 'сменить язык', 'en': 'change language'}),
    CommandSpec('cancel', '', {'ru': 'отменить текущий ввод', 'en': 'cancel the current step'}),
    CommandSpec('help', '', {'ru': 'справка по командам', 'en': 'command reference'}),
)

ADMIN_COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec('provider_status', '', {'ru': 'состояние провайдеров', 'en': 'provider health'}),
    CommandSpec('alerts_on', '', {'ru': 'включить оповещения о сбоях', 'en': 'enable failure alerts'}),
    CommandSpec('alerts_off', '', {'ru': 'выключить оповещения о сбоях', 'en': 'disable failure alerts'}),
    CommandSpec('health_reset', '', {'ru': 'сбросить состояние провайдеров', 'en': 'reset provider health'}),
)

ALL_COMMANDS: tuple[CommandSpec, ...] = USER_COMMANDS + ADMIN_COMMANDS


def command_reference(locale: str, *, include_admin: bool = False) -> str:
    """Render the `/help` body from the same list Telegram's menu is built from."""
    specs = ALL_COMMANDS if include_admin else USER_COMMANDS
    return '\n'.join(f'{spec.usage()} — {spec.description(locale)}' for spec in specs)


def _menu(specs: tuple[CommandSpec, ...], locale: str) -> list[BotCommand]:
    return [BotCommand(command=spec.command, description=spec.description(locale)) for spec in specs]


async def _publish(bot: Bot) -> None:
    """Send every scope Telegram needs to know about."""
    for locale in _MENU_LOCALES:
        language_code = None if locale == _DEFAULT_MENU_LOCALE else locale
        await bot.set_my_commands(
            _menu(USER_COMMANDS, locale),
            scope=BotCommandScopeDefault(),
            language_code=language_code,
        )

    for admin_id in settings.admin_ids:
        for locale in _MENU_LOCALES:
            language_code = None if locale == _DEFAULT_MENU_LOCALE else locale
            await bot.set_my_commands(
                _menu(ALL_COMMANDS, locale),
                scope=BotCommandScopeChat(chat_id=admin_id),
                language_code=language_code,
            )


async def register_bot_commands(bot: Bot) -> None:
    """Publish the command menu to Telegram, in both languages.

    Without this the client's command list is empty and users have to already
    know what to type. It is still only a nicety, so every failure is logged and
    swallowed and the whole thing is time-boxed: a bot that cannot set its menu
    must still answer messages, and must not sit silent while it tries.
    """
    for attempt in range(1, _PUBLISH_ATTEMPTS + 1):
        try:
            await asyncio.wait_for(_publish(bot), timeout=_PUBLISH_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.warning(
                'Could not publish the command menu',
                extra={'attempt': attempt, 'of': _PUBLISH_ATTEMPTS, 'error': str(exc) or type(exc).__name__},
            )
            if attempt < _PUBLISH_ATTEMPTS:
                await asyncio.sleep(2)
            continue

        logger.info(
            'Command menu published',
            extra={
                'user_commands': len(USER_COMMANDS),
                'admin_commands': len(ADMIN_COMMANDS),
                'admins': len(settings.admin_ids),
                'attempt': attempt,
            },
        )
        return
