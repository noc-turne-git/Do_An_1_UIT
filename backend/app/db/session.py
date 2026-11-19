from collections.abc import Iterator
import logging
import re
from time import monotonic
from uuid import uuid4

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from shared.errors import ApplicationError
from app.core.logging import log_message
from ai.logging import log_execution, trace_enabled, current_span_id
from app.db.models import MessageRecord

logger = logging.getLogger(__name__)
_TABLE = re.compile(r'\b(?:FROM|JOIN|INTO|UPDATE)\s+"?([A-Za-z_][A-Za-z_0-9]*)"?', re.IGNORECASE)
_PRIVATE_COLUMN = re.compile(r'password|secret|api.?key|authorization|credential|passport|national_id|card_number', re.IGNORECASE)


def _statement_info(statement):
    verb = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else 'UNKNOWN'
    return {'operation': verb, 'tables': sorted(set(_TABLE.findall(statement)))[:20],
            'statement': statement}


def _before_statement(conn, cursor, statement, parameters, context, executemany):
    try:
        if trace_enabled():
            # Positional binds carry no key for central redaction. If a private
            # column is involved, conservatively hide that statement's binds.
            safe_parameters = '[REDACTED_PRIVATE_BINDS]' if _PRIVATE_COLUMN.search(statement) else parameters
            record = {'started': monotonic(), 'statement': statement,
                      'parameters': safe_parameters, 'executemany': executemany,
                      'span_id': str(uuid4()), 'parent_span_id': current_span_id()}
            conn.info.setdefault('diagnostic_statement_times', []).append(record)
            log_execution(step='database.statement', event_type='database.statement', phase='started',
                          span_id=record['span_id'], parent_span_id=record['parent_span_id'],
                          input={**_statement_info(statement), 'parameters': safe_parameters,
                                 'executemany': executemany},
                          result={k: v for k, v in _statement_info(statement).items()
                                  if k in {'operation', 'tables'}})
    except Exception:
        pass


def _after_statement(conn, cursor, statement, parameters, context, executemany):
    try:
        times = conn.info.get('diagnostic_statement_times', [])
        if not times:
            return
        record = times.pop()
        rowcount = cursor.rowcount
        log_execution(step='database.statement', event_type='database.statement', phase='completed',
                      span_id=record['span_id'], parent_span_id=record['parent_span_id'],
                      input={**_statement_info(record['statement']), 'parameters': record['parameters'],
                             'executemany': record['executemany']},
                      result={**{k: v for k, v in _statement_info(record['statement']).items()
                                 if k in {'operation', 'tables'}},
                              'duration_ms': round((monotonic() - record['started']) * 1000, 3),
                              'rowcount': rowcount if rowcount >= 0 else None, 'executemany': executemany})
    except Exception:
        pass


def _statement_error(context):
    try:
        conn = context.connection
        times = conn.info.get('diagnostic_statement_times', []) if conn is not None else []
        if not times:
            return
        record = times.pop()
        log_execution(step='database.statement', event_type='database.statement', phase='failed',
                      span_id=record['span_id'], parent_span_id=record['parent_span_id'],
                      input={**_statement_info(record['statement']), 'parameters': record['parameters'],
                             'executemany': record['executemany']},
                      result={**{k: v for k, v in _statement_info(record['statement']).items()
                                 if k in {'operation', 'tables'}},
                              'duration_ms': round((monotonic() - record['started']) * 1000, 3)},
                      error=context.original_exception)
    except Exception:
        pass


def collect_messages(session, flush_context):
    for row in session.new:
        if isinstance(row, MessageRecord):
            session.info.setdefault('conversation_messages', []).append(dict(
                message_id=row.message_id, trip_id=row.trip_id,
                conversation_id=row.conversation_id,
                role=row.role, content=row.content))


def postgres_url(value: str):
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL URL required")
    return url.set(drivername="postgresql+psycopg")


class Database:
    def __init__(self, settings: Settings):
        self.engine = None
        self.sessions = None
        if settings.database_url:
            self.engine = create_engine(postgres_url(settings.database_url.get_secret_value()),
                                        pool_pre_ping=True, connect_args={"connect_timeout": 5})
            event.listen(self.engine, 'before_cursor_execute', _before_statement)
            event.listen(self.engine, 'after_cursor_execute', _after_statement)
            event.listen(self.engine, 'handle_error', _statement_error)
            self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Iterator[Session]:
        if self.sessions is None:
            raise ApplicationError("database_not_configured", "DATABASE_URL is not configured")
        with self.sessions() as session:
            event.listen(session, 'after_flush', collect_messages)
            try:
                # Workflow final-resolution checkpoints may commit a claim before
                # a provider call. The session starts the next transaction lazily.
                yield session
                session.commit()
                identity = session.info.get('diagnostic_identity', {})
                if identity:
                    log_execution(step='database.transaction', event_type='database.transaction', phase='committed',
                        conversation_id=identity.get('conversation_id'), run_id=identity.get('run_id'),
                        workflow_id=identity.get('workflow_id'), trip_id=identity.get('trip_id'),
                        request_id=identity.get('request_id'), result={'operation': 'request_transaction'})
                if session.info.get('chat_message_id'):
                    logger.info('chat.message_committed message_id=%s', session.info['chat_message_id'])
                for message in session.info.pop('conversation_messages', []):
                    log_message(**message)
            except Exception as exc:
                session.rollback()
                identity = session.info.get('diagnostic_identity', {})
                if identity:
                    log_execution(step='database.transaction', event_type='database.transaction', phase='rolled_back',
                        conversation_id=identity.get('conversation_id'), run_id=identity.get('run_id'),
                        workflow_id=identity.get('workflow_id'), trip_id=identity.get('trip_id'),
                        request_id=identity.get('request_id'), result={'operation': 'request_transaction'},
                        error=exc)
                if session.info.get('chat_message_id'):
                    logger.warning('chat.message_rolled_back message_id=%s', session.info['chat_message_id'])
                raise

    def dispose(self) -> None:
        if self.engine is not None:
            self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database.session()
