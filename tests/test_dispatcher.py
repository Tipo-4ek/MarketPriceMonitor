"""End-to-end handler tests: real Update objects through a real Dispatcher.

Nothing here mocks aiogram's routing. A fake Bot records the API calls a handler
makes, and updates are fed through ``dp.feed_update`` exactly as polling would,
so command routing, callback routing and the FSM guards are all under test —
the surface that had no behavioural coverage at all.
"""

import itertools
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from aiogram import Dispatcher
from aiogram.types import Chat, Message, Update, User
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bot.models import base
from bot.models.base import Base

# A distinct chat per test, so FSM state kept in the shared dispatcher's storage
# never leaks from one test into the next.
_chat_ids = itertools.count(5000)


class FakeBot:
    """Records outgoing API calls instead of touching Telegram."""

    id = 1

    def __init__(self):
        self.sent: list[dict] = []

    async def __call__(self, method, *args, **kwargs):
        self.sent.append({'method': type(method).__name__, 'text': getattr(method, 'text', '')})
        return

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append({'method': 'SendMessage', 'chat_id': chat_id, 'text': text})
        return


@pytest_asyncio.fixture
async def wired_db(monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(base, 'async_session_maker', async_sessionmaker(engine, expire_on_commit=False))
    yield
    await engine.dispose()


@pytest.fixture
def chat_id() -> int:
    return next(_chat_ids)


def _message(text: str, chat_id: int) -> Message:
    user = User(id=chat_id, is_bot=False, first_name='Test')
    chat = Chat(id=chat_id, type='private')
    return Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=user, text=text)


async def feed(dp: Dispatcher, bot: FakeBot, text: str, chat_id: int) -> None:
    await dp.feed_update(bot, Update(update_id=1, message=_message(text, chat_id)))


def _texts(bot: FakeBot) -> str:
    return '\n'.join(str(call.get('text', '')) for call in bot.sent)


# --- the blocker: the dispatcher must want callback_query -------------------


def test_dispatcher_resolves_callback_query_as_a_used_update(configured_dispatcher):
    # startup.py must not narrow this to ['message'] — that is what killed every
    # inline button in production.
    assert 'callback_query' in configured_dispatcher.resolve_used_update_types()
    assert 'message' in configured_dispatcher.resolve_used_update_types()


# --- command routing --------------------------------------------------------


async def test_start_answers_and_creates_the_user(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await feed(configured_dispatcher, bot, '/start', chat_id)
    assert bot.sent, 'no reply was sent'
    assert any('слежу' in str(c.get('text', '')).lower() for c in bot.sent)


async def test_list_when_empty_says_nothing_tracked(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await feed(configured_dispatcher, bot, '/list', chat_id)
    assert 'ничего не отслеживается' in _texts(bot).lower()


async def test_a_non_link_message_in_the_idle_state_is_ignored(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await feed(configured_dispatcher, bot, 'just chatting', chat_id)
    # No handler matches a plain message with no FSM state and no link.
    assert bot.sent == []


# --- the FSM command-exclusion guard (M13/M14) ------------------------------


async def test_a_command_typed_mid_add_runs_the_command_not_the_url_step(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    # Enter the add-URL step.
    await feed(configured_dispatcher, bot, '/add', chat_id)
    assert 'ссылку' in _texts(bot).lower()

    # Now type /list while waiting for a URL. It must run /list, not be read as
    # a (bad) link and answered with "that is not a link".
    bot.sent.clear()
    await feed(configured_dispatcher, bot, '/list', chat_id)
    body = _texts(bot).lower()
    assert 'не похоже на ссылку' not in body
    assert 'ничего не отслеживается' in body
