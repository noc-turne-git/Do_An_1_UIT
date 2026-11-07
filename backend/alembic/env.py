from alembic import context
from sqlalchemy import create_engine, pool, text

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
                # Historical revision IDs exceed Alembic's default varchar(32).
                # Keep those committed IDs intact for existing databases.
                connection.execute(text('CREATE TABLE IF NOT EXISTS alembic_version (version_num varchar(128) NOT NULL PRIMARY KEY)'))
                connection.execute(text('ALTER TABLE alembic_version ALTER COLUMN version_num TYPE varchar(128)'))
                context.run_migrations()
    finally:
        engine.dispose()
