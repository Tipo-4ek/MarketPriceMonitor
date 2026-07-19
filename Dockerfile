FROM python:3.12-slim

WORKDIR /app

# System deps: Postgres client for the entrypoint wait-loop. Chromium and its
# libraries are installed by `playwright install --with-deps` further down.
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client && \
    rm -rf /var/lib/apt/lists/*

# Upgrade pip and install Poetry
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir poetry==1.8.3

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Configure Poetry
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-root --no-interaction --no-ansi

# Install Playwright browsers with system dependencies
RUN playwright install --with-deps chromium

# Copy application code
COPY . .

# Create entrypoint script
RUN echo '#!/bin/bash\n\
set -e\n\
echo "Waiting for database..."\n\
while ! pg_isready -h db -U postgres; do\n\
  sleep 1\n\
done\n\
echo "Running migrations..."\n\
alembic upgrade head\n\
echo "Starting bot..."\n\
exec "$@"\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "bot.core.startup"]

