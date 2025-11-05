FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including Playwright requirements and Chrome for Selenium
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    postgresql-client \
    wget \
    gnupg \
    # Chrome dependencies for Selenium
    chromium \
    chromium-driver \
    # Additional dependencies for undetected-chromedriver
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

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

# Use Docker-specific configuration
RUN cp bot_config_docker.py bot_config.py

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

