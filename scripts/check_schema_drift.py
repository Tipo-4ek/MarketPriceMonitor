#!/usr/bin/env python3
"""Assert that `alembic upgrade head` produces exactly the schema the models declare.

The unit suite builds its schema with ``Base.metadata.create_all`` on SQLite, so
it can never notice a migration that has drifted from the models — and SQLite
has no timezone-aware timestamp type, so it cannot notice that class of drift at
all. This runs the real migrations against a real PostgreSQL and asks Alembic
itself whether anything differs.

    DATABASE_URL=postgresql+asyncpg://... python scripts/check_schema_drift.py

Exits 0 when the schema matches, 1 with the list of differences when it does not.
"""

import asyncio
import os
import sys

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

import bot.models  # noqa: F401  # imported for the side effect of registering every model
from bot.models.base import Base


def report(message: str) -> None:
    """This script's output is its report, so printing is the point."""
    print(message)  # noqa: T201


async def find_drift(database_url: str) -> list:
    """Ask Alembic what differs between the live schema and the models."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: compare_metadata(
                    # compare_type mirrors migrations/env.py, so this sees the
                    # same differences a real autogenerate would.
                    MigrationContext.configure(sync_connection, opts={'compare_type': True}),
                    Base.metadata,
                )
            )
    finally:
        await engine.dispose()


def main() -> int:
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        report('DATABASE_URL is not set')
        return 2

    command.upgrade(Config('alembic.ini'), 'head')

    differences = asyncio.run(find_drift(database_url))
    if differences:
        report(f'Schema drift between the migrations and the models ({len(differences)}):')
        for difference in differences:
            report(f'  {difference}')
        return 1

    report('Migrations and models agree.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
