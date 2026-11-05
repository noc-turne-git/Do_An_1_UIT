"""JSONL execution records. Raw prompts, outputs and exception messages are excluded."""
import json
import logging
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import RLock
from uuid import UUID

DEFAULT_LOG = Path(__file__).resolve().parent / 'logs' / 'execution.jsonl'
_lock = RLock()


def mask(value):
    if isinstance(value, dict):
        return {str(k): '[redacted]' if re.search(r'(?i)password|secret|token|api.?key|prompt|content|authorization', str(k)) else mask(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask(v) for v in value]
    if isinstance(value, str):
        try:
            UUID(value)
            return value
        except ValueError:
            pass
    if isinstance(value, str) and (len(value) > 120 or re.search(
            r'(?i)bearer|sk-|eyJ|@|\b\d{9,}\b|password|secret|token|api.?key', value)):
        return '[redacted]'
    return value


def configure_ai_logging(path=None, *, max_bytes=5_242_880, backups=5, level='INFO'):
    logger = logging.getLogger('travel.ai')
    target = Path(path) if path else DEFAULT_LOG
    if not target.is_absolute():
        target = DEFAULT_LOG.parent.parent / target
    target.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
        handler = RotatingFileHandler(target, maxBytes=max_bytes, backupCount=backups, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = True
    return logger


def log_execution(*, run_id, trip_id=None, step, result=None, error=None):
    with _lock:
        logger = logging.getLogger('travel.ai')
        if not logger.handlers:
            configure_ai_logging()
        logger.info(json.dumps(mask(dict(timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=str(run_id) if run_id is not None else None,
            trip_id=str(trip_id) if trip_id is not None else None,
            step=step, result=result, error=error)), ensure_ascii=False))
