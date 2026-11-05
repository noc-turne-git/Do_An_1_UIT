from collections.abc import Iterator
import logging

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from shared.errors import ApplicationError
from app.core.logging import log_message
from app.db.models import MessageRecord

logger = logging.getLogger(__name__)


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
            self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Iterator[Session]:
        if self.sessions is None:
            raise ApplicationError("database_not_configured", "DATABASE_URL is not configured")
        with self.sessions() as session:
            event.listen(session, 'after_flush', collect_messages)
            try:
                with session.begin():
                    yield session
                if session.info.get('chat_message_id'):
                    logger.info('chat.message_committed message_id=%s', session.info['chat_message_id'])
                for message in session.info.pop('conversation_messages', []):
                    log_message(**message)
            except Exception:
                if session.info.get('chat_message_id'):
                    logger.warning('chat.message_rolled_back message_id=%s', session.info['chat_message_id'])
                raise

    def dispose(self) -> None:
        if self.engine is not None:
            self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database.session()
