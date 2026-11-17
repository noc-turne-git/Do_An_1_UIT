"""Associate conversations with canonical workflows and durable turn receipts."""
from pathlib import Path
from alembic import op
from alembic.util import CommandError

revision = '20261108_conversation_lifecycle'
down_revision = '20261108_destination_responses'
branch_labels = None
depends_on = None


def migration_sql():
    source = (Path(__file__).resolve().parents[2] / 'supabase' / 'migrations' /
              '20261108_conversation_lifecycle.sql').read_text(encoding='utf-8')
    return source.split('BEGIN;\n', 1)[1].rsplit('COMMIT;', 1)[0]


def upgrade():
    with op.get_bind().connection.driver_connection.cursor() as cursor:
        cursor.execute(migration_sql())


def downgrade():
    raise CommandError('Conversation lifecycle and turn history cannot be discarded by downgrade')
