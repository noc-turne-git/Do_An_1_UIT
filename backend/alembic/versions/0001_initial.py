"""Initial PostgreSQL storage; no connection secrets or business algorithms."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("trips",
        sa.Column("trip_id", sa.String(128), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("workflows",
        sa.Column("request_id", sa.String(128), primary_key=True),
        sa.Column("trip_id", sa.String(128), sa.ForeignKey("trips.trip_id"), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("state", JSONB, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_workflow_revision"))
    op.create_index("ix_workflows_trip_id", "workflows", ["trip_id"])
    op.create_table("artifacts",
        sa.Column("artifact_id", sa.String(128), primary_key=True),
        sa.Column("request_id", sa.String(128), sa.ForeignKey("workflows.request_id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("request_id", "artifact_id", name="uq_artifact_owner"),
        sa.CheckConstraint("kind IN ('trip_request','destination_result','time_constraints','candidates','costed_candidates','planning_input','itinerary','validation_result')", name="ck_artifact_kind"))
    op.create_index("ix_artifacts_request_id", "artifacts", ["request_id"])
    op.execute("""CREATE FUNCTION reject_artifact_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Artifacts are immutable; create a new artifact ID'; END;
        $$""")
    op.execute("""CREATE TRIGGER artifacts_immutable BEFORE UPDATE OR DELETE ON artifacts
        FOR EACH ROW EXECUTE FUNCTION reject_artifact_mutation()""")


def downgrade():
    op.drop_table("artifacts")
    op.execute("DROP FUNCTION reject_artifact_mutation()")
    op.drop_table("workflows")
    op.drop_table("trips")
