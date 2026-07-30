"""Tests for the strategy chain: order, fall-through and self-reordering."""

from decimal import Decimal

import pytest

from bot.core.providers.strategies import PageMaterial, PriceCandidate, StrategyChain

MATERIAL = PageMaterial(url='https://example.com/p/1')


def yields(price):
    def strategy(_material):
        return PriceCandidate(price=price)

    return strategy


def explodes(_material):
    raise RuntimeError('the page shape changed under us')


def test_a_chain_needs_at_least_one_strategy():
    with pytest.raises(ValueError):
        StrategyChain({})


async def test_the_first_usable_strategy_wins():
    chain = StrategyChain({'a': yields(Decimal(10)), 'b': yields(Decimal(20))})

    result = await chain.run(MATERIAL)

    assert result.winner == 'a'
    assert result.candidate.price == Decimal(10)


async def test_falls_through_to_a_later_strategy():
    chain = StrategyChain({'a': yields(None), 'b': yields(None), 'c': yields(Decimal(7))})

    result = await chain.run(MATERIAL)

    assert result.winner == 'c'
    # Every attempt is recorded, so the log says what was tried and why it failed.
    assert [name for name, _ in result.attempts] == ['a', 'b', 'c']


async def test_a_strategy_that_raises_does_not_stop_the_chain():
    """A regex that no longer matches is exactly what the other readers are for."""
    chain = StrategyChain({'broken': explodes, 'good': yields(Decimal(5))})

    result = await chain.run(MATERIAL)

    assert result.winner == 'good'
    assert result.attempts[0][1].startswith('error: RuntimeError')


async def test_returns_none_when_nothing_finds_a_price():
    chain = StrategyChain({'a': yields(None), 'b': explodes})

    assert await chain.run(MATERIAL) is None


async def test_the_winner_is_tried_first_next_time():
    """This is what makes one product resolve one way and another differently."""
    chain = StrategyChain({'a': yields(None), 'b': yields(None), 'c': yields(Decimal(1))})
    assert chain.order == ['a', 'b', 'c']

    await chain.run(MATERIAL)

    assert chain.order[0] == 'c'

    # And the second run reaches it immediately instead of paying for a and b.
    result = await chain.run(MATERIAL)
    assert result.attempts == [('c', 'ok: 1')]


async def test_order_is_stable_while_the_same_strategy_keeps_working():
    chain = StrategyChain({'a': yields(Decimal(3)), 'b': yields(Decimal(4))})

    await chain.run(MATERIAL)
    await chain.run(MATERIAL)

    assert chain.order == ['a', 'b']


async def test_async_strategies_are_supported():
    async def slow(_material):
        return PriceCandidate(price=Decimal(42))

    chain = StrategyChain({'slow': slow})

    result = await chain.run(MATERIAL)

    assert result.candidate.price == Decimal(42)


def test_a_candidate_without_a_price_is_not_usable():
    assert PriceCandidate(price=None).usable is False
    assert PriceCandidate(price=Decimal(1)).usable is True
