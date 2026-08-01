"""Full command and button flows, driven through the real Dispatcher.

The provider is stubbed so the real ProductService and TrackingService run —
covering the persistence path — without launching a browser. Both message and
callback updates are fed, so the inline keyboards (dead in production until the
allowed_updates fix) are exercised here too.
"""

import itertools
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from aiogram import Dispatcher
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bot.core.providers.base import ProductData
from bot.models import Product, Tracking, base
from bot.models import User as UserModel
from bot.models.base import Base
from bot.models.enums import ProviderEnum

URL = 'https://www.wildberries.ru/catalog/219279898/detail.aspx'
_ids = itertools.count(6000)
_update_ids = itertools.count(1)


class FakeBot:
    id = 1

    def __init__(self):
        self.sent: list[dict] = []

    async def __call__(self, method, *args, **kwargs):
        self.sent.append({'method': type(method).__name__, 'text': getattr(method, 'text', '')})
        return

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append({'method': 'SendMessage', 'chat_id': chat_id, 'text': text})
        return


class StubProvider:
    provider_type = ProviderEnum.WILDBERRIES

    def supports(self, url):
        return True

    async def normalize(self, url):
        return URL

    async def fetch_product(self, url):
        return ProductData(title='ETNA Кофе', price=Decimal('558'), currency='RUB', url=URL)


class StubRegistry:
    def find_provider(self, url):
        return StubProvider()

    def get_provider(self, provider_type):
        return StubProvider()


@pytest_asyncio.fixture
async def wired_db(monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(base, 'async_session_maker', async_sessionmaker(engine, expire_on_commit=False))
    # Real services, stubbed marketplace — no browser.
    monkeypatch.setattr('bot.core.services.product_service.provider_registry', StubRegistry())
    yield
    await engine.dispose()


@pytest.fixture
def chat_id() -> int:
    return next(_ids)


def _msg(text: str, chat_id: int) -> Message:
    user = User(id=chat_id, is_bot=False, first_name='Test')
    return Message(
        message_id=1, date=datetime.now(UTC), chat=Chat(id=chat_id, type='private'), from_user=user, text=text
    )


async def send(dp: Dispatcher, bot: FakeBot, text: str, chat_id: int) -> None:
    await dp.feed_update(bot, Update(update_id=next(_update_ids), message=_msg(text, chat_id)))


async def tap(dp: Dispatcher, bot: FakeBot, data: str, chat_id: int) -> None:
    user = User(id=chat_id, is_bot=False, first_name='Test')
    message = Message(
        message_id=2, date=datetime.now(UTC), chat=Chat(id=chat_id, type='private'), from_user=user, text='.'
    )
    callback = CallbackQuery(id='cb1', from_user=user, chat_instance='ci', message=message, data=data)
    await dp.feed_update(bot, Update(update_id=next(_update_ids), callback_query=callback))


def _texts(bot: FakeBot) -> str:
    return '\n'.join(str(c.get('text', '')) for c in bot.sent)


# --- the add / list / remove / monitor lifecycle ---------------------------


async def test_add_then_list_then_remove(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, f'/add {URL}', chat_id)
    assert 'ETNA' in _texts(bot)

    bot.sent.clear()
    await send(configured_dispatcher, bot, '/list', chat_id)
    body = _texts(bot)
    assert 'ETNA' in body
    assert '558' in body

    bot.sent.clear()
    await send(configured_dispatcher, bot, '/remove 1', chat_id)
    assert 'Убрал' in _texts(bot)


async def test_a_bare_link_tracks_without_a_command(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, URL, chat_id)
    assert 'ETNA' in _texts(bot)


async def test_adding_the_same_product_twice_reports_it_exists(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, f'/add {URL}', chat_id)
    bot.sent.clear()
    await send(configured_dispatcher, bot, f'/add {URL}', chat_id)
    assert 'уже отслеживается' in _texts(bot)


async def test_monitor_set_updates_the_threshold(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, f'/add {URL}', chat_id)
    bot.sent.clear()
    await send(configured_dispatcher, bot, '/monitor set 1 20', chat_id)
    assert '20' in _texts(bot)


async def test_monitor_with_a_bad_form_shows_usage(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, '/monitor set', chat_id)
    assert '/monitor set' in _texts(bot)


# --- language ---------------------------------------------------------------


async def test_lang_switches_and_persists(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, '/lang en', chat_id)
    assert 'English' in _texts(bot)
    bot.sent.clear()
    await send(configured_dispatcher, bot, '/help', chat_id)
    assert 'Commands' in _texts(bot)  # /help now renders in English


async def test_lang_rejects_an_unknown_code(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, '/lang de', chat_id)
    assert 'ru' in _texts(bot).lower()


# --- inline buttons (callback_query) ---------------------------------------


async def test_the_my_products_button_renders_the_list(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, f'/add {URL}', chat_id)
    bot.sent.clear()
    await tap(configured_dispatcher, bot, 'menu:list', chat_id)
    assert 'ETNA' in _texts(bot)


async def test_the_remove_button_drops_the_product(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, f'/add {URL}', chat_id)
    bot.sent.clear()
    await tap(configured_dispatcher, bot, 'rm:1', chat_id)
    # After removal the list is re-rendered as empty.
    assert 'ничего не отслеживается' in _texts(bot).lower()


# --- admin ------------------------------------------------------------------


async def test_provider_status_is_refused_to_non_admins(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, '/provider_status', chat_id)
    assert 'администратор' in _texts(bot).lower()


async def test_provider_status_answers_an_admin(wired_db, configured_dispatcher, isolated_settings):
    # isolated_settings makes 123456789 the admin.
    admin_id = 123456789
    bot = FakeBot()
    await send(configured_dispatcher, bot, '/provider_status', admin_id)
    assert 'wildberries' in _texts(bot).lower()


async def test_admin_alerts_on_and_off_and_reset(wired_db, configured_dispatcher, isolated_settings):
    admin_id = 123456789
    bot = FakeBot()
    for command, expected in (
        ('/alerts_off', 'выключены'),
        ('/alerts_on', 'включены'),
        ('/health_reset', 'сброшено'),
    ):
        bot.sent.clear()
        await send(configured_dispatcher, bot, command, admin_id)
        assert expected in _texts(bot).lower()


# --- interactive (menu-driven) flows ---------------------------------------


async def test_interactive_add_via_prompt(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, '/add', chat_id)  # enters add_url state
    assert 'ссылку' in _texts(bot).lower()
    bot.sent.clear()
    await send(configured_dispatcher, bot, URL, chat_id)  # the awaited link
    assert 'ETNA' in _texts(bot)


async def test_add_url_step_rejects_a_non_link(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, '/add', chat_id)
    bot.sent.clear()
    await send(configured_dispatcher, bot, 'not a link', chat_id)
    assert 'не похоже на ссылку' in _texts(bot).lower()


async def test_add_button_then_cancel_button(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await tap(configured_dispatcher, bot, 'menu:add', chat_id)  # cb_add -> prompt
    assert 'ссылку' in _texts(bot).lower()
    bot.sent.clear()
    await tap(configured_dispatcher, bot, 'cancel', chat_id)  # cb_cancel
    assert 'отменил' in _texts(bot).lower()


async def test_interactive_monitor_by_buttons(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, f'/add {URL}', chat_id)
    bot.sent.clear()
    await send(configured_dispatcher, bot, '/monitor', chat_id)  # picker
    assert 'товар' in _texts(bot).lower()
    await tap(configured_dispatcher, bot, 'th:1', chat_id)  # pick product -> percentages
    bot.sent.clear()
    await tap(configured_dispatcher, bot, 'set:1:10', chat_id)  # pick 10%
    # The threshold is now stored; a re-render of the list follows.
    async with base.async_session_maker() as session:
        tracking = (await session.execute(select(Tracking))).scalars().one()
        assert tracking.custom_threshold_delta == 10


async def test_interactive_monitor_by_typing(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, f'/add {URL}', chat_id)
    await send(configured_dispatcher, bot, '/monitor', chat_id)
    await send(configured_dispatcher, bot, '1', chat_id)  # typed product id
    bot.sent.clear()
    await send(configured_dispatcher, bot, '15', chat_id)  # typed percentage
    assert '15' in _texts(bot)


async def test_interactive_remove_via_picker(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await send(configured_dispatcher, bot, f'/add {URL}', chat_id)
    bot.sent.clear()
    await send(configured_dispatcher, bot, '/remove', chat_id)  # picker
    assert 'убрать' in _texts(bot).lower()
    await send(configured_dispatcher, bot, '1', chat_id)  # typed id at the picker
    assert 'убрал' in _texts(bot).lower()


async def test_help_and_language_buttons(wired_db, configured_dispatcher, chat_id):
    bot = FakeBot()
    await tap(configured_dispatcher, bot, 'menu:help', chat_id)
    assert 'команды' in _texts(bot).lower()
    bot.sent.clear()
    await tap(configured_dispatcher, bot, 'lang:en', chat_id)
    assert 'english' in _texts(bot).lower()


async def test_list_is_capped_at_the_telegram_limit(wired_db, configured_dispatcher, chat_id):
    from bot.handlers.tracking import render_list

    async with base.async_session_maker() as session:
        user = UserModel(tg_user_id=chat_id, locale='ru')
        session.add(user)
        await session.flush()
        for i in range(40):
            product = Product(
                provider=ProviderEnum.WILDBERRIES,
                url=f'{URL}?{i}',
                title='ETNA COFFEE Кофе в зернах 250 гр, Суль-де-Минас',
                currency='RUB',
                last_price=Decimal('661.00'),
            )
            session.add(product)
            await session.flush()
            session.add(Tracking(user_id=user.id, product_id=product.id))
        await session.commit()

    body, _keyboard = await render_list(chat_id)
    assert len(body) <= 4096
    assert 'ещё' in body  # the truncation note appears
