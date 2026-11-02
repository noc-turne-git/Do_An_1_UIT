from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import postgres_url

target_metadata = Base.metadata
override = context.config.attributes.get("database_url")
secret = get_settings().database_url
if not override and not secret:
    raise RuntimeError("Set DATABASE_URL before running Alembic (including offline SQL generation)")
url = postgres_url(override or secret.get_secret_value())

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
