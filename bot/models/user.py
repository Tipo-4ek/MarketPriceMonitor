"""User model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.core.clock import utcnow
from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.tracking import Tracking


class User(Base):
    """Telegram user."""

    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    locale: Mapped[str] = mapped_column(String(10), default='ru', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    trackings: Mapped[list['Tracking']] = relationship('Tracking', back_populates='user', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<User(id={self.id}, tg_user_id={self.tg_user_id}, locale={self.locale})>'
