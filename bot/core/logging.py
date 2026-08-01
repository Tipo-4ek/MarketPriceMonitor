"""Structured JSON logging to stdout.

One line of JSON per record, written to stdout only. That is what a container
runtime, journald or a log shipper expects: the process should not decide where
its logs are stored, and it should not have to be re-parsed with a regex to be
queryable. Exceptions are attached as a formatted ``exc_info`` field rather than
spilling a raw traceback across many unrelated lines.
"""

import json
import logging
import sys

from bot.core.clock import utcnow

# Attributes LogRecord always carries; anything else was passed by the caller
# via `extra=` and is worth emitting.
_RESERVED = frozenset(logging.LogRecord('', 0, '', 0, '', None, None).__dict__) | {
    'message',
    'asctime',
    'taskName',
}


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'ts': utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        if record.exc_info:
            payload['exc_info'] = self.formatException(record.exc_info)

        # Caller-supplied extras, but never at the cost of the envelope: a
        # logger.info(..., extra={'level': ...}) must not rewrite the record's
        # real level or timestamp.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(log_level: str = 'INFO') -> None:
    """Send structured logs to stdout at the requested level."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        handlers=[handler],
        force=True,
    )

    # Third-party libraries are chatty at INFO and drown out our own records.
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get logger for a module."""
    return logging.getLogger(name)
