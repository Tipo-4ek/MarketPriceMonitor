#!/bin/sh
# Container entrypoint: bring the schema up to date, then hand over to the CMD.
#
# There is no wait-for-postgres loop here on purpose: docker-compose gates this
# container on the database's healthcheck (`depends_on: condition:
# service_healthy`), so by the time we run, Postgres is already accepting
# connections. Retrying here would only paper over a broken compose file.
set -eu

echo "Applying database migrations..."
alembic upgrade head

echo "Starting: $*"
exec "$@"
