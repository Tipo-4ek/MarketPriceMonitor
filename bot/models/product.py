"""Product model."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Enum, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base
from bot.models.enums import ProviderEnum


class Product(Base):
    """Tracked product from a marketplace."""

    __tablename__ = 'products'
    __table_args__ = (UniqueConstraint('url', 'provider', name='uq_product_url_provider'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[ProviderEnum] = mapped_column(Enum(ProviderEnum), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    last_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    trackings: Mapped[list['Tracking']] = relationship('Tracking', back_populates='product', cascade='all, delete-orphan')
    price_history: Mapped[list['PriceHistory']] = relationship(
        'PriceHistory', back_populates='product', cascade='all, delete-orphan'
    )

    def __repr__(self) -> str:
        return f'<Product(id={self.id}, provider={self.provider.value}, title={self.title[:30]})>'


