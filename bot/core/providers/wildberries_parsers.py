"""The several places a Wildberries product page keeps its price.

Three independent readers, ordered cheapest-and-most-precise first:

1. ``card_api`` — the JSON the page fetches for itself from
   ``/__internal/u-card/cards/v4/detail``. Structured, exact, in kopecks, and it
   carries the brand and name too.
2. ``dom_price`` — the rendered price block. Survives an API version bump.
3. ``page_title`` — Wildberries puts the price in the document title
   ("… 219279898 купить за 558 ₽ в интернет-магазине Wildberries"), which is the
   one place that keeps working when both the API and the markup have moved.
"""

import re
from decimal import Decimal

from bot.core.providers.generic_parsers import money
from bot.core.providers.strategies import PageMaterial, PriceCandidate

_KOPECKS = Decimal(100)

# "… купить за 558 ₽ в интернет-магазине" — the price inside the document title.
_TITLE_PRICE_RE = re.compile(r'купить\s+за\s+([\d\u00a0\u2009\u202f ]{2,15})\s*₽', re.IGNORECASE)

_DOM_PRICE_RE = re.compile(r'([\d\u00a0\u2009\u202f ]{2,15})\s*₽')


def card_api(material: PageMaterial) -> PriceCandidate:
    """Read the card payload the page fetched for itself.

    Prices arrive in kopecks. ``product`` is what the buyer pays; ``basic`` is
    the pre-discount figure shown struck through. Multi-size items can price
    variants differently — the first priced variant is what the page opens on.
    """
    payload = material.api_payload
    if not payload:
        return PriceCandidate(price=None)

    products = (payload.get('data') or {}).get('products') or payload.get('products') or []
    if not products:
        return PriceCandidate(price=None)

    product = products[0]
    title = ' '.join(part for part in (product.get('brand'), product.get('name')) if part).strip() or None

    for size in product.get('sizes') or []:
        raw = (size.get('price') or {}).get('product')
        if raw:
            kopecks = money(raw)
            if kopecks is not None:
                return PriceCandidate(price=kopecks / _KOPECKS, title=title)

    return PriceCandidate(price=None, title=title)


def dom_price(material: PageMaterial) -> PriceCandidate:
    """The rendered price block, for when the API shape has moved."""
    matches = [money(raw) for raw in _DOM_PRICE_RE.findall(material.widget_text)]
    prices = [value for value in matches if value is not None]
    if not prices:
        return PriceCandidate(price=None)
    # The block shows the payable price first, then the struck-through one.
    return PriceCandidate(price=prices[0])


def page_title(material: PageMaterial) -> PriceCandidate:
    """Wildberries writes the price into the document title."""
    match = _TITLE_PRICE_RE.search(material.page_title)
    if not match:
        return PriceCandidate(price=None)
    return PriceCandidate(price=money(match.group(1)))


WILDBERRIES_STRATEGIES = {
    'card_api': card_api,
    'dom_price': dom_price,
    'page_title': page_title,
}
