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
import sys
import asyncio
import hashlib
from functools import wraps
from time import monotonic
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from pydantic import BaseModel

DEFAULT_TRACE_ROOT = Path(__file__).resolve().parent / 'logs' / 'conversations'
TRACE_SCHEMA_VERSION = 3
# Retained as a compatibility knob for integrations that import it. Diagnostic
# records are intentionally never compacted by size.
MAX_EVENT_BYTES = None
_lock = RLock()
_identity: ContextVar[dict | None] = ContextVar('diagnostic_trace_identity', default=None)
_runtime: ContextVar[dict | None] = ContextVar('runtime_trace', default=None)
_span: ContextVar[str | None] = ContextVar('trace_span', default=None)
_span_parent: ContextVar[str | None] = ContextVar('trace_span_parent', default=None)
_last_sequences = {}
_SENSITIVE_KEY = re.compile(
    r'(?i)(?:password|passphrase|secret|api.?key|authorization|cookie|'
    r'client_secret|private_key|credential)'
    r'|^(?:token|access_token|refresh_token|id_token|session_token|auth_token|'
    r'email|phone|phone_number|passport_number|national_id|credit_card|card_number|cvv)$')
_DATABASE_URL_CREDENTIAL = re.compile(
    r'(?ix)\b(?P<scheme>postgres(?:ql)?|mysql)://(?P<user>[^\s:/@]+):'
    r'(?P<password>[^\s@/]+)@')
_SECRET_IN_TEXT = re.compile(
    r'(?ix)\b(?:bearer|basic)\s+[-._~+/=a-z0-9]+|\bsk-(?:proj-)?[a-z0-9_-]+|'
    r'\b(?:eyJ[a-z0-9_-]+\.)[a-z0-9_.-]+|\bAKIA[0-9A-Z]{16}|'
    r'\b(?:api[_-]?key|client_secret|password)\s*[:=]\s*[^\s,;]+')
_EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
_settings = {'trace_root': DEFAULT_TRACE_ROOT}


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
    """Redact secrets and explicit personal identifiers before hashing or storage."""
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
        # Provider messages and SQL JSON parameters can contain serialized objects.
        # Apply key-based redaction inside them, preserving unchanged text exactly.
        if value.lstrip().startswith(('{', '[')):
            try:
                parsed = json.loads(value)
                redacted = mask(parsed)
                if parsed != redacted:
                    value = json.dumps(redacted, ensure_ascii=False)
            except (ValueError, RecursionError):
                pass
        # Keep the non-secret portions of a connection URL useful for
        # diagnosis (driver, account, host, and database), while masking only
        # its password.
        value = _DATABASE_URL_CREDENTIAL.sub(
            lambda match: f"{match.group('scheme')}://{match.group('user')}:"
            '[REDACTED_SECRET]@', value)
        return _EMAIL.sub('[REDACTED_EMAIL]', _SECRET_IN_TEXT.sub('[REDACTED_SECRET]', value))
    return value


def _redacted(value):
    return '[REDACTED_SECRET]'


def diagnostic_snapshot(value):
    return mask(json_value(value))


def configure_ai_logging(path=None, *, max_bytes=5_242_880, backups=5, level='INFO', retention_days=30):
    # Legacy rotation/retention arguments are accepted but never remove evidence.
    if testing_process():
        return logging.getLogger('travel.ai')
    target = Path(path) if path else DEFAULT_TRACE_ROOT
    if not target.is_absolute():
        target = DEFAULT_TRACE_ROOT.parent.parent / target
    trace_root = target.parent / 'conversations' if target.suffix == '.jsonl' else target
    logger = logging.getLogger('travel.ai')
    try:
        with _lock:
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()
            logger.propagate = False
            _settings.update(trace_root=trace_root)
    except Exception:
        pass  # A broken diagnostics destination must not break startup.
    return logger


def testing_process():
    return ('pytest' in sys.modules or 'unittest' in sys.modules
            or bool(os.environ.get('PYTEST_CURRENT_TEST'))
            or os.environ.get('TRAVELIO_TRACE_MODE', '').lower() in {'off', 'test', 'testing'})


def trace_enabled():
    return _runtime.get() is not None and not testing_process()


def current_span_id():
    return _span.get()


def runtime_request_allowed(scope):
    """Only the HTTP boundary may grant write access; reject in-process transports."""
    if testing_process() or (scope.get('client') or ('',))[0] == 'testclient':
        return False
    frame = sys._getframe()
    while frame:
        if frame.f_globals.get('__name__') in {'starlette.testclient', 'httpx._transports.asgi'}:
            return False
        frame = frame.f_back
    return scope.get('type') == 'http'


@contextmanager
def runtime_trace(*, enabled):
    token = _runtime.set({'trace_id': str(uuid4()), 'started': monotonic(),
                          'llm_calls': 0, 'tokens': {}, 'db_operations': 0,
                          'db_statements': 0, 'pending': [],
                          'status': None, 'stop_reason': None} if enabled else None)
    try:
        yield
    finally:
        _runtime.reset(token)


def traced(name, *, metadata=None):
    """Async span wrapper; no changes to the wrapped component's contract."""
    def decorate(function):
        @wraps(function)
        async def invoke(*args, **kwargs):
            if not trace_enabled():
                return await function(*args, **kwargs)
            with diagnostic_scope(**(metadata(*args, **kwargs) if metadata else {})):
                with trace_span(name) as outcome:
                    result = await function(*args, **kwargs)
                    status = getattr(result, 'status', None)
                    if isinstance(result, dict) and 'run' in result:
                        status = result['run'].state.status
                    if status is not None:
                        outcome['status'] = getattr(status, 'value', status)
                    return result
        return invoke
    return decorate


@contextmanager
def trace_span(name):
    parent, span_id, tick = _span.get(), str(uuid4()), monotonic()
    token = _span.set(span_id)
    parent_token = _span_parent.set(parent)
    log_execution(step=name, event_type='span', phase='started', parent_span_id=parent)
    outcome = {}
    try:
        yield outcome
    except BaseException as exc:
        log_execution(step=name, event_type='span', phase='cancelled' if isinstance(exc, asyncio.CancelledError) else 'failed',
                      error=exc, parent_span_id=parent, duration_ms=(monotonic()-tick)*1000)
        raise
    else:
        log_execution(step=name, event_type='span', phase=outcome.get('status', 'completed'), parent_span_id=parent,
                      duration_ms=(monotonic()-tick)*1000)
    finally:
        _span.reset(token)
        _span_parent.reset(parent_token)


def state_diff(before, after, prefix=''):
    changes = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        path = f'{prefix}.{key}' if prefix else key
        if isinstance(old, dict) and isinstance(new, dict):
            changes.extend(state_diff(old, new, path))
        elif old != new:
            changes.append({'field': path, 'old_value': old, 'new_value': new})
    return changes


def log_state_update(run, before, *, source):
    """Observe validated updates without supplying business reasons not in code."""
    try:
        after = diagnostic_snapshot({'state': run.state, 'pending_questions': run.pending_questions,
            'answers_history': run.answers_history, 'attempts': run.attempts, 'errors': run.errors})
        changes = state_diff(before, after)
        if changes:
            log_execution(workflow_id=run.state.request_id, trip_id=run.state.trip_id,
                step=run.state.current_step, event_type='state.update', phase='completed', result={
                    'component': run.state.current_step, 'source': source,
                    'reason': 'validated StateMachine.update from ' + source,
                    'changes': changes, 'artifacts': run.state.artifacts})
    except Exception:
        pass


def state_snapshot(run):
    if not trace_enabled():
        return None
    try:
        return diagnostic_snapshot({'state': run.state, 'pending_questions': run.pending_questions,
            'answers_history': run.answers_history, 'attempts': run.attempts, 'errors': run.errors})
    except Exception:
        return None


def log_transformation(before, after, *, component, source):
    if not trace_enabled():
        return
    try:
        old, new = diagnostic_snapshot(before), diagnostic_snapshot(after)
        changes = state_diff(old, new) if isinstance(old, dict) and isinstance(new, dict) else (
            [{'field': 'output', 'old_value': old, 'new_value': new}] if old != new else [])
        log_execution(step=component, event_type='code.transformation', phase='completed',
            input={'before': old}, output={'after': new, 'changes': changes, 'source': source})
    except Exception:
        pass


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
    runtime = _runtime.get()
    if runtime is None or testing_process():
        return
    try:
        if phase == 'savepoint_committed':
            phase = 'savepoint_released'
        identity = current_diagnostic_identity()
        actual_run = identity.get('run_id') or (str(run_id) if run_id is not None else None)
        # Older workflow callers pass their workflow ID as run_id. Parser callers
        # pass the HTTP request ID; neither replaces the per-turn run ID.
        legacy_workflow = (run_id if run_id is not None
            and str(run_id) not in {actual_run, identity.get('request_id')} else None)
        workflow = workflow_id or legacy_workflow or identity.get('workflow_id') or runtime.get('workflow_id')
        if actual_run is None:
            return  # Never create uncorrelatable random one-event run folders.
        conversation = conversation_id or identity.get('conversation_id') or runtime.get('conversation_id') or 'standalone'
        payload = {
            'trace_id': runtime['trace_id'], 'span_id': details.pop('span_id', _span.get() or runtime['trace_id']),
            'parent_span_id': details.pop('parent_span_id', _span_parent.get()),
            'step_name': step, 'status': 'failed' if error else phase,
            'agent': identity.get('metadata', {}).get('agent'),
            'execution_mode': identity.get('metadata', {}).get('execution_mode'),
            'duration_ms': details.pop('duration_ms', 0),
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
        if conversation != 'standalone':
            runtime['conversation_id'] = str(conversation)
        for key in ('workflow_id', 'trip_id', 'request_id'):
            if payload[key] is not None:
                runtime[key] = payload[key]
            elif runtime.get(key):
                payload[key] = runtime[key]
        data = payload['result'] if isinstance(payload['result'], dict) else {}
        payload['duration_ms'] = payload['duration_ms'] or data.get('duration_ms', 0)
        if event_type == 'llm.attempt' and phase == 'started':
            runtime['llm_calls'] += 1
        token_usage = {}
        if event_type == 'llm.provider_raw_response':
            response = data.get('response')
            if isinstance(response, dict):
                token_usage = response.get('usage') or {}
        elif event_type == 'llm.response' and identity.get('metadata', {}).get('adapter') != 'OpenAILLMAdapter':
            token_usage = data.get('token_usage') or {}
        if phase == 'received':
            for key, value in token_usage.items():
                if isinstance(value, (int, float)):
                    runtime['tokens'][key] = runtime['tokens'].get(key, 0) + value
        if event_type == 'database.statement' and phase != 'started':
            runtime['db_statements'] += 1
        elif (event_type or '').startswith('database.') and phase != 'started':
            runtime['db_operations'] += 1
        if event_type == 'run_turn' and phase == 'completed':
            if data.get('error'):
                runtime['status'], runtime['stop_reason'] = 'failed', 'failed'
            elif data.get('planning') is False:
                runtime['status'], runtime['stop_reason'] = 'completed', 'completed'
        if event_type == 'workflow.run' and phase == 'completed':
            runtime['status'] = (data.get('state') or {}).get('status')
            runtime['stop_reason'] = data.get('stop_reason')
        if event_type == 'chat.turn' and phase == 'response_staged':
            runtime['status'] = ('failed' if data.get('error_code') else data.get('workflow_status')
                                 or runtime['status'] or data.get('parser_status'))
        if event_type == 'http.turn' and phase != 'started':
            payload['conversation_id'] = runtime.get('conversation_id', str(conversation))
            status = runtime['status']
            stop = runtime['stop_reason'] or ({'clarifying': 'awaiting_user_input',
                'awaiting_relaxation': 'awaiting_user_input', 'completed': 'completed',
                'failed': 'failed'}.get(status))
            payload['result'] = {**data, 'final_status': status,
                'stop_reason': 'cancelled' if phase == 'cancelled' else 'failed' if error or (data.get('http_status') or 200) >= 400 else stop,
                'llm_calls': runtime['llm_calls'], 'tokens': runtime['tokens'],
                'db_operations': runtime['db_operations'],
                'db_statements': runtime['db_statements'],
                'duration_ms': round((monotonic()-runtime['started'])*1000, 3)}
            if phase == 'cancelled' or error or (data.get('http_status') or 200) >= 400:
                payload['result']['final_status'] = 'cancelled' if phase == 'cancelled' else 'failed'
            payload['duration_ms'] = payload['result']['duration_ms']
        if conversation == 'standalone' and not runtime.get('conversation_id') and not (event_type == 'http.turn' and phase != 'started'):
            runtime['pending'].append(payload)
            return
        for pending in runtime['pending']:
            pending['conversation_id'] = runtime.get('conversation_id', str(conversation))
            _write_trace(pending)
        runtime['pending'].clear()
        _write_trace(payload)
    except Exception:
        return


def _write_trace(payload):
    if not trace_enabled():
        return
    path = (_settings['trace_root'] / _path_part(payload['conversation_id']) / 'runs' /
            _path_part(payload['run_id']) / 'events.jsonl')
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        summary_payload = dict(payload)
        # Content addressing deduplicates nested schemas, prompts, requests and states.
        def reference(value):
            if isinstance(value, (dict, list, str)):
                encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')
                if len(encoded) >= 256:
                    digest = hashlib.sha256(encoded).hexdigest()
                    target = path.parent / 'payloads' / (digest + '.json')
                    target.parent.mkdir(exist_ok=True)
                    if not target.exists():
                        compact = ({k: reference(v) for k, v in value.items()} if isinstance(value, dict)
                                   else [reference(v) for v in value] if isinstance(value, list) else value)
                        target.write_text(json.dumps(compact, ensure_ascii=False), encoding='utf-8')
                    return {'$payload': digest}
            return value
        for key in ('input', 'result', 'error', 'details'):
            payload[key] = reference(payload[key])
        payload['sequence'] = _next_sequence(path)
        summary_payload['sequence'] = payload['sequence']
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        # These traces are diagnostic evidence, not telemetry. Do not compact
        # payloads: a partial prompt/state makes a lifecycle unreconstructable.
        text = (encoded + '\n').encode('utf-8')
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, text)
        finally:
            os.close(descriptor)
        with (path.parent / 'summary.md').open('a', encoding='utf-8') as summary:
            from ai.trace_view import summary_line
            line = summary_line(summary_payload)
            if line:
                links = [f"[{key}](payloads/{value['$payload']}.json)" for key, value in payload.items()
                         if isinstance(value, dict) and set(value) == {'$payload'}]
                if links:
                    line += ' · ' + ' '.join(links)
                summary.write(line + '\n')


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
    from ai.trace_view import main
    main()
