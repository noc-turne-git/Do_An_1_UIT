"""Canonical Supabase baseline.

This is a separate Alembic branch from legacy revision 0001.  It provisions an
empty Supabase PostgreSQL database from the immutable canonical baseline SQL.
Existing canonical databases must be schema-verified and stamped manually;
this revision must never be run against a populated database.
"""
from hashlib import sha256
from pathlib import Path

from alembic import op
from alembic.util import CommandError


revision = "20261105_canonical_baseline"
down_revision = None
branch_labels = ("canonical",)
depends_on = None

BASELINE_SHA256 = "82773cdde861b1dfcd7eeb94bafc9ce4a4c2a3539bf8c0d855398d0a4ad64264"


def _baseline_sql() -> str:
    path = Path(__file__).resolve().parents[2] / "supabase" / "schema.sql"
    source = path.read_text(encoding="utf-8")
    if sha256(source.encode("utf-8")).hexdigest() != BASELINE_SHA256:
        raise CommandError("Canonical baseline schema.sql changed; create a new migration instead")
    if not source.startswith("-- Fresh Supabase database only.\n-- Execute as database owner in Supabase SQL Editor; never with a client key.\nBEGIN;\n") or not source.endswith("COMMIT;\n"):
        raise CommandError("Unexpected canonical baseline transaction envelope")
    return source.removeprefix("-- Fresh Supabase database only.\n-- Execute as database owner in Supabase SQL Editor; never with a client key.\nBEGIN;\n").removesuffix("COMMIT;\n")


def upgrade():
    # Execute the same immutable SQL used by the canonical Supabase baseline;
    # Alembic owns the enclosing transaction.
    bind = op.get_bind()
    with bind.connection.driver_connection.cursor() as cursor:
        cursor.execute(_baseline_sql())


def downgrade():
    raise CommandError("Canonical baseline downgrade is intentionally unsupported; it would destroy data")
