"""Accept canonical parser-confirmed destination responses without option spoofing."""
from pathlib import Path

from alembic import op
from alembic.util import CommandError

revision = '20261108_destination_responses'
down_revision = '20261107_canonical_episodes'
branch_labels = None
depends_on = None


def migration_sql():
    source = (Path(__file__).resolve().parents[2] / 'supabase' / 'migrations' /
              '20261108_destination_responses.sql').read_text(encoding='utf-8')
    return source.split('BEGIN;\n', 1)[1].rsplit('COMMIT;', 1)[0]


def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as cursor:
        cursor.execute(migration_sql())


def downgrade():
    raise CommandError('Canonical destination response history cannot be discarded by downgrade')
