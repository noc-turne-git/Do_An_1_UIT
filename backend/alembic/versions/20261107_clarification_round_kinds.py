"""Add independent destination clarification limits and round kinds."""
import sqlalchemy as sa
from alembic import op


revision = "20261107_clarification_round_kinds"
down_revision = "20261105_canonical_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workflow_requests", sa.Column(
        "max_destination_rounds", sa.Integer(), nullable=False, server_default=sa.text("2")))
    op.create_check_constraint(
        "workflow_requests_destination_round_limit_check", "workflow_requests",
        "max_destination_rounds >= 0 AND destination_round <= max_destination_rounds")
    op.add_column("clarification_rounds", sa.Column(
        "kind", sa.Text(), nullable=False, server_default=sa.text("'trip_request'")))
    op.drop_constraint("clarification_rounds_request_id_round_key", "clarification_rounds", type_="unique")
    op.create_unique_constraint(
        "clarification_rounds_request_id_kind_round_key", "clarification_rounds",
        ["request_id", "kind", "round"])


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM clarification_rounds WHERE kind <> 'trip_request') THEN
        RAISE EXCEPTION 'Cannot downgrade: destination_choice clarification history exists';
      END IF;
      IF EXISTS (SELECT 1 FROM workflow_requests
                 WHERE destination_round <> 0 OR max_destination_rounds <> 2) THEN
        RAISE EXCEPTION 'Cannot downgrade: destination clarification state exists';
      END IF;
    END $$""")
    op.drop_constraint("clarification_rounds_request_id_kind_round_key", "clarification_rounds", type_="unique")
    op.drop_column("clarification_rounds", "kind")
    op.create_unique_constraint(
        "clarification_rounds_request_id_round_key", "clarification_rounds", ["request_id", "round"])
    op.drop_constraint("workflow_requests_destination_round_limit_check", "workflow_requests", type_="check")
    op.drop_column("workflow_requests", "max_destination_rounds")
