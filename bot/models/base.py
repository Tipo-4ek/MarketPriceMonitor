"""Base database model."""

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""


# Global engine and session maker, initialised by init_db() at startup.
engine: AsyncEngine | None = None
async_session_maker: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str) -> None:
    """Initialise the database engine and session maker.

    expire_on_commit is off deliberately: handlers read attributes off an object
    after committing (the id of a just-created row, a user's locale), and the
    default would expire them and trigger a lazy load — MissingGreenlet under
    async — on the next access.
    """
    global engine, async_session_maker
    engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


def new_session() -> AsyncSession:
    """Open a session, or fail loudly if the database was never initialised.

    Returning a live session (rather than the Optional module global) keeps the
    call sites free of a None check the type checker would otherwise demand at
    every one of them.
    """
    if async_session_maker is None:
        raise RuntimeError('Database is not initialised; call init_db() first')
    return async_session_maker()
