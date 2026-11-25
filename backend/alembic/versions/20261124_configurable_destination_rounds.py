"""Let application configuration own destination information limits."""
from pathlib import Path

from alembic import op
from alembic.util import CommandError

revision = '20261124_destination_rounds'
down_revision = '20261120_destination_consultation'
branch_labels = None
depends_on = None


def upgrade():
    source = (Path(__file__).resolve().parents[2] / 'supabase' / 'migrations' /
              '20261124_configurable_destination_rounds.sql').read_text(encoding='utf-8')
    sql = source.split('BEGIN;\n', 1)[1].rsplit('COMMIT;', 1)[0]
    with op.get_bind().connection.driver_connection.cursor() as cursor:
        cursor.execute(sql)


def downgrade():
    raise CommandError('A fixed SQL default would restore a second configuration source')
