"""Tests for the per-marketplace request throttle."""

import asyncio
import time

from bot.core.providers.throttle import Throttle
from bot.models.enums import ProviderEnum


async def test_first_request_is_not_delayed():
    throttle = Throttle(min_interval_seconds=10)

    started = time.monotonic()
    await throttle.wait(ProviderEnum.WILDBERRIES)

    assert time.monotonic() - started < 0.5


async def test_second_request_waits_out_the_interval():
    throttle = Throttle(min_interval_seconds=0.3)

    await throttle.wait(ProviderEnum.WILDBERRIES)
    started = time.monotonic()
    await throttle.wait(ProviderEnum.WILDBERRIES)

    assert time.monotonic() - started >= 0.3


async def test_hosts_are_throttled_independently():
    # A slow poll of one marketplace must not hold up another: the limit protects
    # each host from us, it is not a global speed limit.
    throttle = Throttle(min_interval_seconds=5)

    await throttle.wait('wildberries.ru')
    started = time.monotonic()
    await throttle.wait('dns-shop.ru')

    assert time.monotonic() - started < 0.5


async def test_concurrent_requests_to_one_marketplace_are_serialised():
    throttle = Throttle(min_interval_seconds=0.2)

    started = time.monotonic()
    await asyncio.gather(*(throttle.wait(ProviderEnum.WILDBERRIES) for _ in range(3)))

    # Three requests means two enforced gaps.
    assert time.monotonic() - started >= 0.4
