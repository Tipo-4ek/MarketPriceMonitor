"""Tests for internationalization."""

import re
import string

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.i18n import TRANSLATIONS, get_text
from bot.core.services.tracking_service import TrackingService
from bot.models import User


def test_ru_and_en_define_exactly_the_same_keys():
    """A key present in one locale but not the other silently degrades to the
    key name for users of the missing side."""
    assert set(TRANSLATIONS['ru']) == set(TRANSLATIONS['en'])


def test_placeholders_match_across_locales():
    """`price_changed` and friends are .format()-ed with named args; a
    placeholder present in one locale and missing in the other raises KeyError
    at runtime for that language only."""
    for key, ru_text in TRANSLATIONS['ru'].items():
        ru_fields = {name for _, name, _, _ in string.Formatter().parse(ru_text) if name}
        en_fields = {name for _, name, _, _ in string.Formatter().parse(TRANSLATIONS['en'][key]) if name}
        assert ru_fields == en_fields, f'placeholder mismatch in {key!r}: {ru_fields} vs {en_fields}'


def test_no_translation_carries_an_unescaped_ampersand_outside_a_tag():
    """Messages go out with parse_mode='HTML'; a literal & that is not an entity
    would make Telegram reject them."""
    bare_amp = re.compile(r'&(?!amp;|lt;|gt;|#)')
    for locale in ('ru', 'en'):
        for key, text in TRANSLATIONS[locale].items():
            assert not bare_amp.search(text), f'bare & in {locale}/{key}'


def test_get_text_russian():
    """The Russian welcome names the supported marketplace."""
    text = get_text('ru', 'welcome')
    assert 'Wildberries' in text
    assert 'ценами' in text


def test_get_text_english():
    """The English welcome names the supported marketplace."""
    text = get_text('en', 'welcome')
    assert 'Wildberries' in text
    assert 'prices' in text


def test_get_text_with_parameters():
    """Test getting text with parameters."""
    text = get_text('ru', 'product_added', title='Test', price='100', currency='RUB', product_id=1)
    assert 'Test' in text
    assert '100' in text
    assert 'RUB' in text


def test_get_text_fallback():
    """An unsupported locale falls back to Russian rather than failing."""
    assert get_text('fr', 'welcome') == get_text('ru', 'welcome')


@pytest.mark.asyncio
async def test_update_user_locale(db_session: AsyncSession, sample_user: User):
    """Test updating user locale."""
    assert sample_user.locale == 'ru'

    await TrackingService.update_user_locale(db_session, sample_user, 'en')
    await db_session.commit()
    await db_session.refresh(sample_user)

    assert sample_user.locale == 'en'
