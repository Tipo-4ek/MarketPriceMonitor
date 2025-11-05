"""Base database model."""
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""

    pass


# Global engine and session maker (initialized in startup)
engine = None
async_session_maker: async_sessionmaker | None = None


def init_db(database_url: str):
    """Initialize database engine and session maker."""
    global engine, async_session_maker
    engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


