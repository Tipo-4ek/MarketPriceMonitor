"""Tracking model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.core.clock import utcnow
from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.product import Product
    from bot.models.user import User


class Tracking(Base):
    """User-product tracking relationship."""

    __tablename__ = 'trackings'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    custom_threshold_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    user: Mapped['User'] = relationship('User', back_populates='trackings')
    product: Mapped['Product'] = relationship('Product', back_populates='trackings')

    def __repr__(self) -> str:
        return f'<Tracking(id={self.id}, user_id={self.user_id}, product_id={self.product_id})>'
