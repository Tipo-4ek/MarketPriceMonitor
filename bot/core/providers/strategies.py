"""Several ways to read one price, tried in turn.

A marketplace page carries its price in more than one place: structured data for
search engines, an internal JSON blob for its own front end, the rendered DOM,
the page title. Each of those breaks on a different kind of redesign, and none of
them breaks on all of them — so a parser that only knows one is a parser that
dies on the next deploy.

The chain below tries each strategy until one produces a plausible price, and
remembers which one worked so the next fetch starts there. That ordering matters
in practice: the first strategy is usually the cheapest and most precise, but
once a site changes shape the chain settles onto whatever still works instead of
paying for the broken path every time.

This is about surviving redesigns, not about getting past a refusal. If the site
declines to serve the page at all, every strategy sees the same closed door and
the chain reports it as blocked.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from bot.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PriceCandidate:
    """What one strategy managed to read.

    Only ``price`` decides whether the reader succeeded. Title and currency are
    opportunistic: a reader that finds a price but no title is still a win, and
    the provider fills the gaps from elsewhere on the page.
    """

    price: Decimal | None
    title: str | None = None
    currency: str | None = None

    @property
    def usable(self) -> bool:
        return self.price is not None


# A strategy is any callable over already-fetched page material. Strategies do no
# I/O of their own: the transport fetches once, and every strategy reads the same
# bytes. That keeps the number of requests to the marketplace at exactly one.
Strategy = Callable[['PageMaterial'], PriceCandidate | Awaitable[PriceCandidate]]


@dataclass
class PageMaterial:
    """Everything a strategy is allowed to look at, fetched once."""

    url: str
    html: str = ''
    widget_text: str = ''
    api_payload: dict | None = None
    page_title: str = ''


@dataclass
class ChainResult:
    """The winning candidate and how the attempt went."""

    candidate: PriceCandidate
    winner: str
    attempts: list[tuple[str, str]]


class StrategyChain:
    """Ordered strategies with a memory of which one last worked."""

    def __init__(self, strategies: Mapping[str, Strategy]) -> None:
        if not strategies:
            raise ValueError('a strategy chain needs at least one strategy')
        self._strategies = dict(strategies)
        self._order = list(strategies)

    @property
    def order(self) -> list[str]:
        """Current try order — first entry is whatever last succeeded."""
        return list(self._order)

    async def run(self, material: PageMaterial) -> ChainResult | None:
        """Try each strategy until one returns a usable price."""
        attempts: list[tuple[str, str]] = []

        for name in list(self._order):
            strategy = self._strategies[name]
            try:
                result = strategy(material)
                candidate = await result if isinstance(result, Awaitable) else result
            except Exception as exc:
                # One strategy throwing is not a failure of the fetch: a regex
                # that no longer matches, or JSON that changed shape, is exactly
                # the case the other strategies exist for.
                attempts.append((name, f'error: {type(exc).__name__}'))
                continue

            if candidate.usable:
                attempts.append((name, f'ok: {candidate.price}'))
                self._promote(name)
                logger.info(
                    'Price read',
                    extra={'strategy': name, 'price': str(candidate.price), 'attempts': len(attempts)},
                )
                return ChainResult(candidate=candidate, winner=name, attempts=attempts)

            attempts.append((name, 'no price'))

        logger.info(
            'No strategy found a price',
            extra={'url': material.url, 'attempts': [f'{n}={r}' for n, r in attempts]},
        )
        return None

    def _promote(self, name: str) -> None:
        """Move the winner to the front so the next fetch tries it first."""
        if self._order[0] == name:
            return
        self._order.remove(name)
        self._order.insert(0, name)
        logger.debug('Strategy order changed', extra={'order': self._order})
