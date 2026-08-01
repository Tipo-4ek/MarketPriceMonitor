"""The model __repr__ helpers used in logs and debugging."""

from decimal import Decimal

from bot.models import PriceHistory, Product, Tracking, User
from bot.models.enums import ProviderEnum


def test_reprs_are_informative():
    product = Product(
        id=7, provider=ProviderEnum.WILDBERRIES, url='u', title='A long product title to be clipped', currency='RUB'
    )
    assert 'id=7' in repr(product)
    assert 'wildberries' in repr(product)

    user = User(id=1, tg_user_id=42, locale='ru')
    assert '42' in repr(user)

    tracking = Tracking(id=3, user_id=1, product_id=7)
    assert 'id=3' in repr(tracking)

    history = PriceHistory(id=5, product_id=7, price=Decimal('558'))
    assert '558' in repr(history)
