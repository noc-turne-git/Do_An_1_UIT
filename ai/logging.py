"""Failure-isolated diagnostic traces for planning executions.

Each turn has one append-only JSONL record in
``conversations/<conversation_id>/runs/<run_id>/events.jsonl``. ContextVars
keep correlations correct for concurrent asyncio tasks without changing every
component signature.
"""
import json
import logging
import math
import os
import re
import shutil
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from pydantic import BaseModel

DEFAULT_TRACE_ROOT = Path(__file__).resolve().parent / 'logs' / 'conversations'
TRACE_SCHEMA_VERSION = 2
# Retained as a compatibility knob for integrations that import it. Diagnostic
# records are intentionally never compacted by size.
MAX_EVENT_BYTES = None
_lock = RLock()
_identity: ContextVar[dict | None] = ContextVar('diagnostic_trace_identity', default=None)
_last_sequences = {}
_SENSITIVE_KEY = re.compile(
    r'(?i)(?:password|passphrase|secret|api.?key|authorization|cookie|'
    r'client_secret|private_key|credential)'
    r'|^(?:token|access_token|refresh_token|id_token|session_token|auth_token)$')
# Deliberately do not treat user/business text, email addresses, locations, or
# prompts as sensitive. Operators need those values to reconstruct a turn.
_DATABASE_URL_CREDENTIAL = re.compile(
    r'(?ix)\b(?P<scheme>postgres(?:ql)?|mysql)://(?P<user>[^\s:/@]+):'
    r'(?P<password>[^\s@/]+)@')
_SECRET_IN_TEXT = re.compile(
    r'(?ix)\bbearer\s+[-._~+/=a-z0-9]+|\bsk-(?:proj-)?[a-z0-9_-]+|'
    r'\b(?:eyJ[a-z0-9_-]+\.)[a-z0-9_.-]+|\bAKIA[0-9A-Z]{16}|'
    r'\b(?:api[_-]?key|client_secret|password)\s*[:=]\s*[^\s,;]+')
_settings = {'trace_root': DEFAULT_TRACE_ROOT, 'retention_days': 30,
             'last_prune': None}


def json_value(value, *, _depth=0):
    """Convert diagnostic values without discarding business inputs or outputs."""
    if isinstance(value, BaseModel):
        return json_value(value.model_dump(mode='json'), _depth=_depth + 1)
    if isinstance(value, Mapping):
        return {str(k): json_value(v, _depth=_depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_value(item, _depth=_depth + 1) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return {'type': 'nonfinite_float'}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, BaseException):
        return {'type': type(value).__name__, 'message': str(value)}
    return str(value)


def mask(value, *, key=None):
    """Redact credentials only; retain all actual business diagnostic data."""
    if isinstance(value, dict):
        result = {}
        for raw_key, item in value.items():
            name = str(raw_key)
            sensitive = bool(_SENSITIVE_KEY.search(name))
            if sensitive:
                result[name] = _redacted(item)
            else:
                result[name] = mask(item, key=name)
        return result
    if isinstance(value, list):
        return [mask(v, key=key) for v in value]
    if isinstance(value, str):
        # Keep the non-secret portions of a connection URL useful for
        # diagnosis (driver, account, host, and database), while masking only
        # its password.
        value = _DATABASE_URL_CREDENTIAL.sub(
            lambda match: f"{match.group('scheme')}://{match.group('user')}:"
            '[REDACTED_SECRET]@', value)
        return _SECRET_IN_TEXT.sub('[REDACTED_SECRET]', value)
    return value


def _redacted(value):
    return '[REDACTED_SECRET]'


def diagnostic_snapshot(value):
    return mask(json_value(value))


def configure_ai_logging(path=None, *, max_bytes=5_242_880, backups=5, level='INFO', retention_days=30):
    target = Path(path) if path else DEFAULT_TRACE_ROOT
    if not target.is_absolute():
        target = DEFAULT_TRACE_ROOT.parent.parent / target
    trace_root = target.parent / 'conversations' if target.suffix == '.jsonl' else target
    logger = logging.getLogger('travel.ai')
    try:
        trace_root.mkdir(parents=True, exist_ok=True)
        with _lock:
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()
            logger.propagate = False
            _settings.update(trace_root=trace_root, retention_days=retention_days, last_prune=None)
        _prune_old_traces(trace_root, retention_days)
        _settings['last_prune'] = datetime.now(timezone.utc).date()
    except Exception:
        pass  # A broken diagnostics destination must not break startup.
    return logger


def _prune_old_traces(root: Path, retention_days: int):
    if retention_days < 1:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    base = root.resolve()
    for path in root.glob('*/runs/*'):
        try:
            resolved = path.resolve()
            if (path.is_dir() and not path.is_symlink() and base in resolved.parents
                    and path.parent.name == 'runs' and (path / 'events.jsonl').is_file()
                    and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff):
                shutil.rmtree(path)
        except OSError:
            continue


@contextmanager
def diagnostic_scope(*, conversation_id=None, run_id=None, workflow_id=None, trip_id=None, request_id=None, **metadata):
    """Bind one run's IDs to all nested workflow/LLM/database log events."""
    parent = _identity.get() or {}
    try:
        safe_metadata = diagnostic_snapshot({**parent.get('metadata', {}), **metadata})
    except Exception:
        safe_metadata = {}
    identity = {**parent, **{key: str(value) for key, value in {
        'conversation_id': conversation_id, 'run_id': run_id, 'workflow_id': workflow_id,
        'trip_id': trip_id, 'request_id': request_id}.items() if value is not None},
        'metadata': safe_metadata}
    token = _identity.set(identity)
    try:
        yield identity
    finally:
        _identity.reset(token)


def current_diagnostic_identity():
    return dict(_identity.get() or {})


def update_diagnostic_identity(**identifiers):
    """Attach a conversation/workflow discovered after the HTTP request began."""
    current = _identity.get() or {}
    if 'run_id' not in current:
        return
    _identity.set({**current, **{key: str(value) for key, value in identifiers.items()
                                 if value is not None}})


def log_execution(*, run_id=None, trip_id=None, step=None, input=None, result=None, output=None, error=None,
                  event_type=None, phase=None, conversation_id=None, workflow_id=None,
                  request_id=None, **details):
    """Best-effort event writer. Logging errors intentionally never escape."""
    try:
        identity = current_diagnostic_identity()
        workflow = workflow_id or identity.get('workflow_id') or (
            run_id if not (identity.get('run_id') or conversation_id) else None)
        actual_run = identity.get('run_id') or (str(run_id) if run_id is not None else None)
        if actual_run is None:
            return  # Never create uncorrelatable random one-event run folders.
        conversation = conversation_id or identity.get('conversation_id') or 'standalone'
        payload = {
            'schema_version': TRACE_SCHEMA_VERSION, 'event_id': str(uuid4()), 'sequence': None,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event_type': event_type or step or 'execution', 'phase': phase,
            'conversation_id': str(conversation), 'run_id': actual_run,
            'workflow_id': str(workflow) if workflow is not None else None,
            'trip_id': str(trip_id or identity.get('trip_id')) if (trip_id or identity.get('trip_id')) else None,
            'request_id': str(request_id or identity.get('request_id')) if (request_id or identity.get('request_id')) else None,
            'step': step, 'input': diagnostic_snapshot(input),
            # ``result`` remains for compatibility. ``output`` makes stage
            # boundaries explicit for new diagnostic consumers.
            'result': diagnostic_snapshot(output if output is not None else result),
            'error': diagnostic_snapshot(error),
            'details': diagnostic_snapshot(details) if details else None,
        }
        _write_trace(payload)
    except Exception:
        return


def _write_trace(payload):
    path = (_settings['trace_root'] / _path_part(payload['conversation_id']) / 'runs' /
            _path_part(payload['run_id']) / 'events.jsonl')
    with _lock:
        today = datetime.now(timezone.utc).date()
        if _settings['last_prune'] != today:
            _prune_old_traces(_settings['trace_root'], _settings['retention_days'])
            _settings['last_prune'] = today
        path.parent.mkdir(parents=True, exist_ok=True)
        payload['sequence'] = _next_sequence(path)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        # These traces are diagnostic evidence, not telemetry. Do not compact
        # payloads: a partial prompt/state makes a lifecycle unreconstructable.
        text = (encoded + '\n').encode('utf-8')
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, text)
        finally:
            os.close(descriptor)


def _next_sequence(path: Path):
    if path in _last_sequences:
        number = _last_sequences[path] + 1
    elif path.exists():
        # A single complete diagnostic event can be larger than a megabyte.
        # Reading the file here avoids guessing at a line boundary and keeps
        # ordering correct after a worker restart.
        with path.open('rb') as source:
            lines = source.read().splitlines()
        number = json.loads(lines[-1])['sequence'] + 1 if lines else 1
    else:
        number = 1
    if len(_last_sequences) >= 4096:
        _last_sequences.pop(next(iter(_last_sequences)))
    _last_sequences[path] = number
    return number


def _path_part(value):
    part = re.sub(r'[^A-Za-z0-9_.-]', '_', str(value))[:128]
    return part if part not in {'', '.', '..'} else 'standalone'


def trace_paths(*, conversation_id=None, run_id=None, root=None):
    """Locate trace files by either durable correlation ID without a DB query."""
    directory = Path(root) if root else _settings['trace_root']
    if conversation_id is not None and run_id is not None:
        paths = [directory / _path_part(conversation_id) / 'runs' /
                 _path_part(run_id) / 'events.jsonl']
    elif conversation_id is not None:
        paths = directory.glob(f'{_path_part(conversation_id)}/runs/*/events.jsonl')
    elif run_id is not None:
        paths = directory.glob(f'*/runs/{_path_part(run_id)}/events.jsonl')
    else:
        raise ValueError('Provide a conversation_id or run_id')
    return sorted(path for path in paths if path.is_file())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Find per-run diagnostic JSONL files')
    parser.add_argument('--conversation-id')
    parser.add_argument('--run-id')
    parser.add_argument('--root', type=Path, default=DEFAULT_TRACE_ROOT)
    arguments = parser.parse_args()
    if not arguments.conversation_id and not arguments.run_id:
        parser.error('Provide --conversation-id or --run-id')
    for trace in trace_paths(conversation_id=arguments.conversation_id,
                             run_id=arguments.run_id, root=arguments.root):
        print(trace)
