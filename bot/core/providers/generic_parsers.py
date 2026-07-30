"""Site-agnostic ways to read a price out of a product page.

None of these know anything about a particular shop. They read the conventions
shops share — schema.org JSON-LD, schema.org microdata, Open Graph tags, and the
JSON blobs a front end hydrates itself from — so the same readers work on a site
nobody has written a provider for.

That is deliberate: these are the foundation of the automatic price detection the
project is built around, and each provider composes the subset that applies to it
rather than reimplementing the parsing.

Ordering across readers is not fixed here. It belongs to the caller's
:class:`~bot.core.providers.strategies.StrategyChain`, which reorders by what
last worked.
"""

import html as html_module
import json
import re
from decimal import Decimal, InvalidOperation

from bot.core.providers.strategies import PageMaterial, PriceCandidate

# Digits in a rendered price are separated by thin / non-breaking spaces.
_SPACES = dict.fromkeys(map(ord, '    '), None)

# A price outside this range is a parsing accident: a review count, an article
# number, or a value in kopecks.
MIN_PRICE = Decimal(1)
MAX_PRICE = Decimal(100_000_000)

# Unit rates that sit next to the real price and must not be mistaken for it:
# "218 ₽ за 100 гр", "1 200 ₽/шт".
PER_UNIT_RE = re.compile(r'(\bза\b|/\s*(шт|кг|г|л|мл|м|pcs)\b|[₽$€]\s*/)', re.IGNORECASE)

MONEY_RE = re.compile(r'([\d    ]{2,15})\s*(?:₽|руб|RUB)', re.IGNORECASE)

_JSON_LD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

_DATA_STATE_RE = re.compile(r'data-state="([^"]{2,})"')

_MICRODATA_RE = re.compile(
    r'<[^>]*itemprop="price"[^>]*content="([^"]+)"|<[^>]*content="([^"]+)"[^>]*itemprop="price"',
    re.IGNORECASE,
)

# Keys shops use for the payable price, most specific first. Bare 'price' is last
# because it also turns up on unrelated nested objects.
PRICE_KEYS = ('cardPrice', 'finalPrice', 'currentPrice', 'salePrice', 'priceValue', 'price')

_CURRENCY_BY_SYMBOL = {'₽': 'RUB', '$': 'USD', '€': 'EUR'}


def money(raw: object) -> Decimal | None:
    """Parse '2 414 ₽', '2414', '1499.00', 2414.0 — or give up.

    Giving up is a normal outcome, not an error: a reader that cannot find a
    plausible number hands over to the next one.
    """
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float, Decimal)):
        text = str(raw)
    elif isinstance(raw, str):
        text = raw
    else:
        return None

    cleaned = text.translate(_SPACES)
    cleaned = re.sub(r'[₽$€]|руб\.?|RUB|USD|EUR', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace(',', '.').strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
    return value if MIN_PRICE <= value <= MAX_PRICE else None


def json_ld_blocks(html: str) -> list[dict]:
    """Every parseable schema.org block on the page, flattened."""
    blocks: list[dict] = []
    for raw in _JSON_LD_RE.findall(html):
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if isinstance(candidate, dict):
                blocks.append(candidate)
                graph = candidate.get('@graph')
                if isinstance(graph, list):
                    blocks.extend(node for node in graph if isinstance(node, dict))
    return blocks


def json_ld(material: PageMaterial) -> PriceCandidate:
    """schema.org Product/offers — the cleanest source when a shop publishes it."""
    title = None
    price = None
    currency = None

    for block in json_ld_blocks(material.html):
        if block.get('name') and not title:
            title = str(block['name']).strip()

        offers = block.get('offers')
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if isinstance(offers, dict) and price is None:
            price = money(offers.get('price'))
            currency = offers.get('priceCurrency') or currency

    return PriceCandidate(price=price, title=title, currency=currency)


def microdata(material: PageMaterial) -> PriceCandidate:
    """schema.org microdata: itemprop="price" on a meta or span."""
    match = _MICRODATA_RE.search(material.html)
    if not match:
        return PriceCandidate(price=None)
    raw = next((group for group in match.groups() if group), None)
    return PriceCandidate(price=money(raw))


def og_meta(material: PageMaterial) -> PriceCandidate:
    """Open Graph / product meta tags — usually the last thing a redesign drops."""
    title = None
    match = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', material.html, re.IGNORECASE)
    if match:
        title = html_module.unescape(match.group(1)).strip() or None

    price = None
    currency = None
    for prop in ('product:price:amount', 'og:price:amount'):
        found = re.search(rf'<meta[^>]*property="{prop}"[^>]*content="([^"]+)"', material.html, re.IGNORECASE)
        if found:
            price = money(found.group(1))
            if price is not None:
                break
    for prop in ('product:price:currency', 'og:price:currency'):
        found = re.search(rf'<meta[^>]*property="{prop}"[^>]*content="([^"]+)"', material.html, re.IGNORECASE)
        if found:
            currency = found.group(1).strip()
            break

    return PriceCandidate(price=price, title=title, currency=currency)


def walk_for_price(node: object, depth: int = 0) -> Decimal | None:
    """Depth-first search for a price-shaped value under a price-shaped key.

    Front ends hydrate from deeply nested JSON whose shape changes freely, so
    looking for the key anywhere is more durable than hard-coding a path.
    """
    if depth > 6:
        return None

    if isinstance(node, dict):
        for key in PRICE_KEYS:
            if key in node:
                found = money(node[key])
                if found is not None:
                    return found
        for value in node.values():
            found = walk_for_price(value, depth + 1)
            if found is not None:
                return found

    elif isinstance(node, list):
        for value in node[:40]:
            found = walk_for_price(value, depth + 1)
            if found is not None:
                return found

    return None


def hydration_state(material: PageMaterial) -> PriceCandidate:
    """Read the JSON a front end hydrates its widgets from.

    Two shapes are covered: ``data-state="{...}"`` attributes, and any inline
    script whose body is a JSON object mentioning a price.
    """
    for raw in _DATA_STATE_RE.findall(material.html):
        unescaped = html_module.unescape(raw)
        if 'rice' not in unescaped:  # matches price / Price in one pass
            continue
        try:
            state = json.loads(unescaped)
        except (json.JSONDecodeError, ValueError):
            continue
        price = walk_for_price(state)
        if price is not None:
            return PriceCandidate(price=price)

    return PriceCandidate(price=None)


def rendered_text(material: PageMaterial) -> PriceCandidate:
    """Read money out of the rendered price element, or refuse to guess.

    Shops render several figures together: a discounted price, the regular one,
    a struck-through old one, and often a unit rate. Unit rates are dropped
    outright. Of what is left, one figure is unambiguous and three follow the
    common discount / regular / was ordering, so the middle one is the price.
    Two figures could be either pair, and choosing wrong stores a price out by a
    large factor and fires a false alert — so nothing is returned.
    """
    prices: list[Decimal] = []
    for line in material.widget_text.splitlines():
        if PER_UNIT_RE.search(line):
            continue
        for raw in MONEY_RE.findall(line):
            value = money(raw)
            if value is not None:
                prices.append(value)

    if len(prices) == 3:
        return PriceCandidate(price=prices[1])
    if len(prices) == 1:
        return PriceCandidate(price=prices[0])
    return PriceCandidate(price=None)


def title_from_html(html: str) -> str | None:
    """A product title from whatever the page offers, best source first."""
    for pattern in (
        r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
        r'<h1[^>]*>(.*?)</h1>',
        r'<title[^>]*>(.*?)</title>',
    ):
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            text = re.sub(r'<[^>]+>', '', html_module.unescape(match.group(1))).strip()
            if len(text) > 3:
                return text
    return None


def currency_from_text(text: str, default: str = 'RUB') -> str:
    """Guess the currency from a symbol in rendered text."""
    for symbol, code in _CURRENCY_BY_SYMBOL.items():
        if symbol in text:
            return code
    return default


# Readers that need only the page HTML, in the order that is cheapest and most
# precise first. A provider with extra material (an intercepted API response,
# rendered widget text) prepends its own.
HTML_STRATEGIES = {
    'json_ld': json_ld,
    'hydration_state': hydration_state,
    'microdata': microdata,
    'og_meta': og_meta,
}
