"""Price history model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.product import Product


class PriceHistory(Base):
    """Historical price records for products."""

    __tablename__ = 'price_history'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    product: Mapped['Product'] = relationship('Product', back_populates='price_history')

    def __repr__(self) -> str:
        return f'<PriceHistory(id={self.id}, product_id={self.product_id}, price={self.price})>'
