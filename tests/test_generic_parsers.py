"""Tests for the site-agnostic price readers."""

from decimal import Decimal

from bot.core.providers.generic_parsers import (
    HTML_STRATEGIES,
    json_ld,
    microdata,
    money,
    og_meta,
    rendered_text,
    title_from_html,
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


def test_money_rejects_implausible_values():
    assert money('0') is None
    assert money('999999999999') is None
    assert money('1 490 \u20bd') == Decimal(1490)
    assert money('1490,50') == Decimal('1490.50')
    assert money(None) is None
    assert money(True) is None


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
