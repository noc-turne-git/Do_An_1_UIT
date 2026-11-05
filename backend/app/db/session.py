from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import ApplicationError


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
            with session.begin():
                yield session

    def dispose(self) -> None:
        if self.engine is not None:
            self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database.session()
