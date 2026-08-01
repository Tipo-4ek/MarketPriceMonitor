"""The JSON log formatter — the sink for every extra= dict in the codebase."""

import json
import logging

from bot.core.logging import JsonFormatter


def _record(msg='hello', level=logging.INFO, **extra):
    record = logging.LogRecord('bot.test', level, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formats_a_record_as_one_json_object():
    payload = json.loads(JsonFormatter().format(_record('done', provider='wildberries', count=3)))
    assert payload['message'] == 'done'
    assert payload['level'] == 'INFO'
    assert payload['logger'] == 'bot.test'
    assert payload['provider'] == 'wildberries'
    assert payload['count'] == 3
    assert 'ts' in payload


def test_a_caller_extra_cannot_overwrite_the_envelope():
    # A stray extra={'logger': ...} must not rewrite the record's real fields.
    record = _record('x', level=logging.WARNING)
    record.logger = 'sneaky'  # collide with an envelope key
    payload = json.loads(JsonFormatter().format(record))
    assert payload['level'] == 'WARNING'
    assert payload['logger'] == 'bot.test'


def test_exception_info_is_attached_as_a_field():
    try:
        raise ValueError('boom')
    except ValueError:
        import sys

        record = logging.LogRecord('bot.test', logging.ERROR, __file__, 1, 'failed', None, sys.exc_info())
    payload = json.loads(JsonFormatter().format(record))
    assert 'ValueError: boom' in payload['exc_info']


def test_non_serialisable_extras_do_not_crash_the_formatter():
    payload = json.loads(JsonFormatter().format(_record('x', obj=object())))
    assert isinstance(payload['obj'], str)  # default=str keeps it a valid line
