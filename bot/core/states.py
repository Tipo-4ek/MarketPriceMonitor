"""Conversation states for commands that ask for their arguments.

Tapping a command in Telegram's menu sends it with no arguments, so a bot that
only understands `/monitor set 3 10` is unusable from the menu it publishes.
Each such command instead asks for what it needs and waits for the next message,
while still accepting the whole thing on one line for anyone who prefers typing.
"""

from aiogram.fsm.state import State, StatesGroup


class Flow(StatesGroup):
    """Steps where the bot is waiting for one piece of input."""

    add_url = State()
    remove_id = State()
    threshold_product = State()
    threshold_value = State()
    locale_choice = State()
