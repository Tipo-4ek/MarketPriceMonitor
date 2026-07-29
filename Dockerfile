# syntax=docker/dockerfile:1

# --- build stage: resolve and install the locked dependencies ----------------
FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.4.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /app

# Only the dependency manifests, so this layer is cached until they change.
# poetry.lock is committed, so the build is reproducible.
COPY pyproject.toml poetry.lock README.md ./

RUN poetry install --only main --no-root

# --- runtime stage ----------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

WORKDIR /app

# The venv lives at the same path as in the builder, so no relocation is needed.
COPY --from=builder /app/.venv /app/.venv

# Chromium plus the system libraries it needs. Done as root, before dropping
# privileges; the browsers directory is world-readable afterwards.
RUN playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*

COPY bot ./bot
COPY migrations ./migrations
# poetry.lock travels with pyproject.toml so the dev stage below installs the
# same pinned versions as the runtime stage rather than re-resolving them.
COPY alembic.ini pyproject.toml poetry.lock README.md ./
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh && \
    useradd --create-home --uid 10001 app && \
    chown -R app:app /app

USER app

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "-m", "bot.core.startup"]

# --- dev stage: runtime plus the test toolchain -----------------------------
# Used by `docker compose --profile test run --rm tests`. Kept as a separate
# target so the shipped image carries no test dependencies.
FROM runtime AS dev

USER root
RUN pip install --no-cache-dir "poetry==2.4.1" && \
    POETRY_VIRTUALENVS_IN_PROJECT=1 poetry install --no-root --no-interaction
COPY tests ./tests
RUN chown -R app:app /app
USER app

ENTRYPOINT []
CMD ["pytest", "-v"]
