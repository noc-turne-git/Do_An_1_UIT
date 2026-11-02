"""Storage envelopes preserve schema payloads without flattening their fields."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TripRecord(Base):
    __tablename__ = "trips"
    trip_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    workflows: Mapped[list["WorkflowRecord"]] = relationship(back_populates="trip")


class WorkflowRecord(Base):
    __tablename__ = "workflows"
    request_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.trip_id"), index=True)
    schema_version: Mapped[str] = mapped_column(String(16))
    # Entire WorkflowState, including attempts/clarifications/errors, one checkpoint.
    state: Mapped[dict] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    trip: Mapped[TripRecord] = relationship(back_populates="workflows")
    artifacts: Mapped[list["ArtifactRecord"]] = relationship(back_populates="workflow")
    __mapper_args__ = {"version_id_col": revision}
    __table_args__ = (CheckConstraint("revision > 0", name="ck_workflow_revision"),)


class ArtifactRecord(Base):
    __tablename__ = "artifacts"
    artifact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("workflows.request_id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    schema_version: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    workflow: Mapped[WorkflowRecord] = relationship(back_populates="artifacts")
    __table_args__ = (
        UniqueConstraint("request_id", "artifact_id", name="uq_artifact_owner"),
        CheckConstraint("kind IN ('trip_request','destination_result','time_constraints','candidates','costed_candidates','planning_input','itinerary','validation_result')", name="ck_artifact_kind"),
    )
