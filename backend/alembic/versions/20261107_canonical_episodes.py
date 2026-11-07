"""Persist canonical destination episodes and full clarification questions."""
from pathlib import Path

from alembic import op
from alembic.util import CommandError

revision = '20261107_canonical_episodes'
down_revision = '20261107_clarification_round_kinds'
branch_labels = None
depends_on = None


def migration_sql():
    source = (Path(__file__).resolve().parents[2] / 'supabase' / 'migrations' /
              '20261107_canonical_episodes.sql').read_text(encoding='utf-8')
    # One SQL implementation, two transaction owners; parity cannot drift.
    return source.split('BEGIN;\n', 1)[1].rsplit('COMMIT;', 1)[0]


def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as cursor:
        cursor.execute(migration_sql())


def downgrade():
    raise CommandError('Canonical clarification history cannot be discarded by downgrade')
