"""Tests for the site-agnostic price readers."""

from decimal import Decimal

import pytest

from bot.core.providers.generic_parsers import (
    HTML_STRATEGIES,
    currency_from_text,
    hydration_state,
    json_ld,
    microdata,
    money,
    og_meta,
    rendered_text,
    title_from_html,
    walk_for_price,
)
from bot.core.providers.strategies import PageMaterial, StrategyChain

# A shop emits its own Organization/WebSite block alongside the Product one.
# Taking the first name on offer titled every product after the shop itself,
# which is how this was caught on live pages.
SHOP_PLUS_PRODUCT = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Organization","name":"\u0420\u0435\u0433\u0430\u0440\u0434"}
</script>
<script type="application/ld+json">
{"@type":"Product","name":"Processor AMD Ryzen 7 7800X3D",
 "offers":{"@type":"Offer","price":"27870.00","priceCurrency":"RUB"}}
</script>
</head><body></body></html>
"""

GRAPH_PAGE = """
<html><head><script type="application/ld+json">
{"@graph":[{"@type":"WebSite","name":"Shop"},
           {"@type":["Product","Thing"],"name":"Boxed thing",
            "offers":{"price":1490,"priceCurrency":"RUB"}}]}
</script></head><body></body></html>
"""

MICRODATA_PAGE = '<html><body><meta itemprop="price" content="879"></body></html>'

OG_PAGE = (
    '<html><head><meta property="og:title" content="Thing">'
    '<meta property="product:price:amount" content="1199.50">'
    '<meta property="product:price:currency" content="RUB"></head><body></body></html>'
)


def material(html='', widget_text=''):
    return PageMaterial(url='https://shop.example/p/1', html=html, widget_text=widget_text)


def test_json_ld_takes_the_name_from_the_product_not_the_shop():
    candidate = json_ld(material(html=SHOP_PLUS_PRODUCT))
    assert candidate.price == Decimal('27870.00')
    assert candidate.title == 'Processor AMD Ryzen 7 7800X3D'
    assert candidate.currency == 'RUB'


def test_json_ld_reads_a_graph_and_a_list_typed_product():
    candidate = json_ld(material(html=GRAPH_PAGE))
    assert candidate.price == Decimal(1490)
    assert candidate.title == 'Boxed thing'


def test_microdata_reads_itemprop_price():
    assert microdata(material(html=MICRODATA_PAGE)).price == Decimal(879)


def test_og_meta_reads_amount_and_currency():
    candidate = og_meta(material(html=OG_PAGE))
    assert candidate.price == Decimal('1199.50')
    assert candidate.currency == 'RUB'


def test_rendered_text_skips_unit_rates():
    assert rendered_text(material(widget_text='218 \u20bd \u0437\u0430 100 \u0433\u0440')).price is None


def test_rendered_text_refuses_an_ambiguous_pair():
    assert rendered_text(material(widget_text='2 414 \u20bd\n4 557 \u20bd')).price is None


def test_rendered_text_takes_a_single_figure():
    assert rendered_text(material(widget_text='1 490 \u20bd')).price == Decimal(1490)


def test_rendered_text_reads_the_middle_of_three():
    # discount / regular / struck-through \u2014 the middle is the payable price.
    assert rendered_text(material(widget_text='1 490 \u20bd\n1 990 \u20bd\n2 490 \u20bd')).price == Decimal(1990)


def test_currency_from_text_detects_the_symbol_and_falls_back():
    assert currency_from_text('1 490 \u20bd') == 'RUB'
    assert currency_from_text('$19.99') == 'USD'
    assert currency_from_text('19.99 \u20ac') == 'EUR'
    assert currency_from_text('no symbol here') == 'RUB'  # default


def test_title_from_html_prefers_the_og_title():
    html = '<meta property="og:title" content="OG name"><h1>Heading</h1>'
    assert title_from_html(html) == 'OG name'


def test_og_meta_without_a_price_returns_none():
    assert og_meta(material(html='<meta property="og:title" content="Thing">')).price is None


def test_money_rejects_implausible_values():
    assert money('0') is None
    assert money('999999999999') is None
    assert money('1 490 \u20bd') == Decimal(1490)
    assert money('1490,50') == Decimal('1490.50')
    assert money(None) is None
    assert money(True) is None


@pytest.mark.parametrize(
    'separator',
    ['\u0020', '\u00a0', '\u2009', '\u202f'],
    ids=['ascii-space', 'nbsp', 'thin-space', 'narrow-nbsp'],
)
def test_money_reads_every_thousands_separator(separator):
    # A 42 990 price rendered with any of these separators must read as 42990,
    # not collapse to 990 because the separator went unstripped.
    assert money(f'42{separator}990 \u20bd') == Decimal(42990)


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('12,990', Decimal(12990)),  # comma grouping, no decimals
        ('1,234.56', Decimal('1234.56')),  # comma grouping + dot decimal
        ('27870.00', Decimal('27870.00')),  # dot decimal, no grouping
        ('1490,50', Decimal('1490.50')),  # lone comma is the decimal point
        ('nan', None),  # non-finite must not crash the range check
        ('inf', None),
        ('-inf', None),
    ],
)
def test_money_grouping_and_non_finite(raw, expected):
    assert money(raw) == expected


def test_walk_for_price_prefers_specific_keys_within_a_dict():
    # Within one object the most specific key wins: cardPrice over a bare price.
    assert walk_for_price({'price': 999, 'cardPrice': 1490}) == Decimal(1490)


def test_walk_for_price_gives_up_past_the_depth_limit():
    node: object = {'price': 1490}
    for _ in range(8):
        node = {'wrap': node}
    assert walk_for_price(node) is None


def test_hydration_state_reads_a_data_state_attribute():
    import html
    import json

    blob = html.escape(json.dumps({'product': {'salePrice': 1490}}), quote=True)
    material = PageMaterial(url='u', html=f'<div data-state="{blob}"></div>')
    assert hydration_state(material).price == Decimal(1490)


def test_hydration_state_reads_an_inline_script():
    material = PageMaterial(url='u', html='<script>window.__NUXT__ = {"currentPrice": 1490};</script>')
    assert hydration_state(material).price == Decimal(1490)


def test_microdata_reads_a_span_body_not_only_a_content_attribute():
    material = PageMaterial(url='u', html='<span itemprop="price">1090</span>')
    assert microdata(material).price == Decimal(1090)


def test_json_ld_binds_the_title_to_the_priced_block():
    # Two Product blocks; the price comes from the second, and its name \u2014 not the
    # first block's \u2014 must travel with it.
    page = """
    <script type="application/ld+json">
    {"@type":"Product","name":"Unpriced accessory"}
    </script>
    <script type="application/ld+json">
    {"@type":"Product","name":"The main product","offers":{"price":"1490","priceCurrency":"RUB"}}
    </script>
    """
    candidate = json_ld(material(html=page))
    assert candidate.price == Decimal(1490)
    assert candidate.title == 'The main product'


def test_title_falls_back_through_the_page():
    assert title_from_html('<h1>Only a heading</h1>') == 'Only a heading'
    assert title_from_html('<title>Only a title</title>') == 'Only a title'
    assert title_from_html('<html></html>') is None


async def test_the_chain_falls_through_json_ld_to_microdata():
    """The live run needed exactly this: book24 has no JSON-LD price."""
    chain = StrategyChain(HTML_STRATEGIES)

    result = await chain.run(material(html=MICRODATA_PAGE))

    assert result.winner == 'microdata'
    assert result.candidate.price == Decimal(879)
