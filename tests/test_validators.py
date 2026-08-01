"""The input validators and URL parsing — pure functions guarding the handlers."""

import pytest

from bot.utils.parsing import is_valid_url
from bot.utils.validators import validate_locale, validate_product_id, validate_threshold


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('1', 1),
        ('100', 100),
        ('50', 50),
        ('0', None),  # below the 1..100 range
        ('101', None),  # above it
        ('-5', None),
        ('5.5', None),  # not an int
        ('', None),
        ('abc', None),
        ('  7  ', 7),  # int() tolerates surrounding space
    ],
)
def test_validate_threshold(raw, expected):
    assert validate_threshold(raw) == expected


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('1', 1),
        ('2147483647', 2147483647),  # the 32-bit INTEGER ceiling
        ('2147483648', None),  # one past it: would overflow Postgres int4
        ('99999999999999999999', None),  # a 20-digit id — the reported crash
        ('0', None),
        ('-1', None),
        ('x', None),
        ('', None),
    ],
)
def test_validate_product_id(raw, expected):
    assert validate_product_id(raw) == expected


@pytest.mark.parametrize(
    ('locale', 'expected'),
    [('ru', True), ('en', True), ('de', False), ('', False), ('RU', False)],
)
def test_validate_locale(locale, expected):
    assert validate_locale(locale) is expected


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('https://www.wildberries.ru/catalog/1/detail.aspx', True),
        ('http://example.com', True),
        ('ftp://host/file', True),  # scheme + netloc is all is_valid_url promises
        ('not a url', False),
        ('http://', False),  # scheme but no host
        ('/relative/path', False),
        ('', False),
    ],
)
def test_is_valid_url(url, expected):
    assert is_valid_url(url) is expected
