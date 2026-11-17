"""Add server-issued anonymous sessions for persisted guest chat."""
from pathlib import Path

from alembic import op
from alembic.util import CommandError

revision = '20261117_anonymous_chat_sessions'
down_revision = '20261117_five_intent_destination_policy'
branch_labels = None
depends_on = None


def upgrade():
    source = (Path(__file__).resolve().parents[2] / 'supabase' / 'migrations' /
              '20261117_anonymous_chat_sessions.sql').read_text(encoding='utf-8')
    sql = source.split('BEGIN;\n', 1)[1].rsplit('COMMIT;', 1)[0]
    with op.get_bind().connection.driver_connection.cursor() as cursor:
        cursor.execute(sql)


def downgrade():
    raise CommandError('Anonymous chat history cannot be safely discarded by downgrade')
