"""The Wildberries transport: how fetch_product drives one shared page.

These exercise `_gather`, which the reader tests never reach. The regression
that matters most is the shared page: a navigation that fails must not let the
previous product's document be read and returned under the new URL.
"""

from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from playwright.async_api import Error as PlaywrightError

from bot.core.providers.base import ProviderBlockedError
from bot.core.providers.wildberries import WildberriesProvider

URL = 'https://www.wildberries.ru/catalog/219279898/detail.aspx'
ARTICLE = '219279898'

CARD_PAYLOAD = {'data': {'products': [{'name': 'Кофе', 'brand': 'ETNA', 'sizes': [{'price': {'product': 55800}}]}]}}
DOC_TITLE = 'Кофе ETNA 219279898 купить за 558 ₽ в интернет-магазине Wildberries'


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class _ExpectCtx:
    """Stand-in for page.expect_response(...) as an async context manager."""

    def __init__(self, payload, *, miss):
        self._payload = payload
        self._miss = miss

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # A failure inside the body (a goto that raised) propagates unchanged,
        # exactly as Playwright cancels the waiter and re-raises. Only when the
        # body succeeded do we simulate the response being missed.
        if exc_type is not None:
            return False
        if self._miss:
            raise PlaywrightError('Timeout 20000ms exceeded waiting for response')
        return False

    @property
    def value(self):
        async def _get():
            return _FakeResponse(self._payload)

        return _get()


class FakePage:
    def __init__(self, *, title=DOC_TITLE, content='<html></html>', widget='', card_payload=None, goto_raises=False):
        self._title = title
        self._content = content
        self._widget = widget
        self._card_payload = card_payload
        self._goto_raises = goto_raises
        self.url = 'about:blank'
        self.goto_calls: list[str] = []

    async def goto(self, url, **kwargs):
        self.goto_calls.append(url)
        if url == 'about:blank':
            self.url = 'about:blank'
            return
        if self._goto_raises:
            # Raise before advancing self.url, so a failed navigation leaves the
            # page where it was — about:blank here, never the previous product.
            raise PlaywrightError('net::ERR_ABORTED')
        self.url = url
        return

    def expect_response(self, predicate, timeout=None):
        return _ExpectCtx(self._card_payload, miss=self._card_payload is None)

    async def content(self):
        return self._content

    async def title(self):
        return self._title

    async def eval_on_selector(self, selector, script):
        return self._widget

    async def wait_for_timeout(self, ms):
        return None


class FakeSession:
    def __init__(self, page):
        self._page = page

    @asynccontextmanager
    async def page(self):
        yield self._page


async def test_happy_path_reads_the_card_api():
    provider = WildberriesProvider(session=FakeSession(FakePage(card_payload=CARD_PAYLOAD)))
    data = await provider.fetch_product(URL)
    assert data.price == Decimal('558')
    assert data.title == 'ETNA Кофе'


async def test_a_missed_card_api_falls_back_to_the_title():
    # No card payload -> the interception "times out"; the title still carries 558.
    page = FakePage(card_payload=None, title=DOC_TITLE)
    provider = WildberriesProvider(session=FakeSession(page))
    data = await provider.fetch_product(URL)
    assert data.price == Decimal('558')
    # The page was blanked first, then navigated to the product.
    assert page.goto_calls == ['about:blank', URL]


async def test_a_failed_navigation_is_reported_as_blocked_not_a_stale_price():
    # The shared page still shows a previous product (558 in title/markup), and
    # this navigation fails. The old code returned 558 under the new URL; now it
    # must refuse, because the page never reached this article.
    stale = FakePage(
        title=DOC_TITLE,
        content='<span itemprop="price">558</span>',
        widget='558 ₽',
        card_payload=None,
        goto_raises=True,
    )
    provider = WildberriesProvider(session=FakeSession(stale))
    with pytest.raises(ProviderBlockedError):
        await provider.fetch_product(URL)
    # It blanked the page and attempted the product, but never committed to it.
    assert stale.goto_calls == ['about:blank', URL]
    assert stale.url == 'about:blank'
