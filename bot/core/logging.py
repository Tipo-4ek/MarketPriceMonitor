"""Logging configuration."""

import logging
import sys
from datetime import datetime


def setup_logging(log_level: str = 'INFO') -> None:
    """Configure structured logging."""

    class StructuredFormatter(logging.Formatter):
        """Custom formatter for structured logs."""

        def format(self, record: logging.LogRecord) -> str:
            timestamp = datetime.utcnow().isoformat()
            level = record.levelname
            message = record.getMessage()
            return f'[{timestamp}] [{level}] {message}'

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(StructuredFormatter())

    # File handler
    file_handler = logging.FileHandler('bot.log', encoding='utf-8')
    file_handler.setFormatter(StructuredFormatter())

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        handlers=[console_handler, file_handler],
        force=True,
    )

    # Suppress noisy loggers
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get logger for a module."""
    return logging.getLogger(name)
