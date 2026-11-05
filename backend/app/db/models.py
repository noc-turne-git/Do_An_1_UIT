"""Mappings for supabase/schema.sql; SQL owns CHECKs, triggers and RLS.
Never use create_all() to provision the canonical database schema.
"""
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID, ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

# Reference only; not a managed application table.
_auth_users = sa.Table("users", sa.MetaData(), sa.Column("id", PGUUID(as_uuid=True), primary_key=True), schema="auth")
price_status_enum = ENUM('ESTIMATED','UNKNOWN','VERIFIED_FREE', name="price_status", schema="public", create_type=False)
request_type_enum = ENUM('EXPLICIT','IMPLICIT','AMBIGUOUS','INSUFFICIENT', name="request_type", schema="public", create_type=False)
workflow_status_enum = ENUM('parsing','clarifying','planning','validating','awaiting_relaxation','completed','failed', name="workflow_status", schema="public", create_type=False)
workflow_step_enum = ENUM('request_parser','destination_agent','constraint_planner','place_agent','budget_module','planning_input_builder','planning_engine','validator','explainer', name="workflow_step", schema="public", create_type=False)
artifact_type_enum = ENUM('trip_request','destination_result','time_constraints','candidates','costed_candidates','planning_input','itinerary','validation_result', name="artifact_type", schema="public", create_type=False)
message_role_enum = ENUM('user','assistant', name="message_role", schema="public", create_type=False)
pending_status_enum = ENUM('open','resolved','unknown', name="pending_status", schema="public", create_type=False)
candidate_source_enum = ENUM('user_requested','agent_suggested', name="candidate_source", schema="public", create_type=False)
attempt_result_enum = ENUM('accepted','hard_violation','infeasible','error', name="attempt_result", schema="public", create_type=False)
workflow_error_code_enum = ENUM('llm_output_invalid','external_api_error','planning_input_inconsistent','solver_error','validator_internal_error', name="workflow_error_code", schema="public", create_type=False)
itinerary_status_enum = ENUM('feasible','infeasible','partial','error', name="itinerary_status", schema="public", create_type=False)
validation_action_enum = ENUM('accept','replan','ask_user','fail', name="validation_action", schema="public", create_type=False)
issue_kind_enum = ENUM('violation','warning', name="issue_kind", schema="public", create_type=False)
issue_severity_enum = ENUM('hard','soft','info', name="issue_severity", schema="public", create_type=False)

class ProfileRecord(Base):
    __tablename__ = "profiles"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey(_auth_users.c.id, ondelete="CASCADE"), primary_key=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    last_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    full_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    preferences: Mapped[dict | list] = mapped_column(JSONB(none_as_null=True), nullable=False, server_default=sa.text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), server_onupdate=sa.FetchedValue())

    trips: Mapped[list["TripRecord"]] = relationship(viewonly=True)

class TripRecord(Base):
    __tablename__ = "trips"
    trip_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('profiles.id', ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    __table_args__ = (
        sa.Index('trips_user_idx', 'user_id'),
    )
    profile: Mapped["ProfileRecord"] = relationship(foreign_keys=[user_id])

    requests: Mapped[list["WorkflowRequestRecord"]] = relationship(viewonly=True)
    messages: Mapped[list["MessageRecord"]] = relationship(viewonly=True)

class MessageRecord(Base):
    __tablename__ = "messages"
    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    trip_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('trips.trip_id', ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(message_role_enum, nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    __table_args__ = (
        sa.Index('messages_trip_idx', 'trip_id', 'created_at'),
    )

    trip: Mapped["TripRecord"] = relationship(foreign_keys=[trip_id])

class WorkflowRequestRecord(Base):
    __tablename__ = "workflow_requests"
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    trip_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('trips.trip_id', ondelete="CASCADE"), nullable=False)
    schema_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(workflow_status_enum, nullable=False, server_default=sa.text("'parsing'"))
    current_step: Mapped[str] = mapped_column(workflow_step_enum, nullable=False, server_default=sa.text("'request_parser'"))
    clarification_round: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text('0'))
    max_clarification_rounds: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text('3'))
    destination_round: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text('0'))
    retry_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text('0'))
    graph_snapshot: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), server_onupdate=sa.FetchedValue())
    __table_args__ = (
        sa.UniqueConstraint('request_id', 'trip_id'),
        sa.Index('workflow_requests_trip_idx', 'trip_id'),
    )
    trip: Mapped["TripRecord"] = relationship(foreign_keys=[trip_id])

    artifacts: Mapped[list["WorkflowArtifactRecord"]] = relationship(foreign_keys="WorkflowArtifactRecord.request_id", viewonly=True)

class WorkflowArtifactRecord(Base):
    __tablename__ = "workflow_artifacts"
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(artifact_type_enum, nullable=False)
    parent_artifact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    is_latest: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text('true'))
    schema_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload: Mapped[dict | list] = mapped_column(JSONB(none_as_null=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    __table_args__ = (
        sa.UniqueConstraint('request_id', 'artifact_type', 'artifact_id'),
        sa.ForeignKeyConstraint(['request_id', 'artifact_type', 'parent_artifact_id'], ['workflow_artifacts.request_id', 'workflow_artifacts.artifact_type', 'workflow_artifacts.artifact_id']),
        sa.Index('artifacts_lookup_idx', 'request_id', 'artifact_type', 'is_latest'),
        sa.Index('artifacts_latest_idx', 'request_id', 'artifact_type', unique=True, postgresql_where=sa.text("is_latest")),
        sa.Index("workflow_artifacts_request_idx", "request_id"),
    )
    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id])

    parent: Mapped["WorkflowArtifactRecord | None"] = relationship(remote_side="[WorkflowArtifactRecord.request_id, WorkflowArtifactRecord.artifact_type, WorkflowArtifactRecord.artifact_id]", foreign_keys=[request_id, artifact_type, parent_artifact_id], viewonly=True)

class ClarificationRoundRecord(Base):
    __tablename__ = "clarification_rounds"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    round: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    asked_fields: Mapped[dict | list] = mapped_column(JSONB(none_as_null=True), nullable=False)
    question: Mapped[str] = mapped_column(sa.Text, nullable=False)
    answer_raw: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    resolved_fields: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    declared_unknown_fields: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    __table_args__ = (
        sa.UniqueConstraint('request_id', 'round'),
        sa.Index("clarification_rounds_request_idx", "request_id"),
    )

    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class PendingItemRecord(Base):
    __tablename__ = "pending_items"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    field_path: Mapped[str] = mapped_column(sa.Text, nullable=False)
    question: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(pending_status_enum, nullable=False, server_default=sa.text("'open'"))
    __table_args__ = (
        sa.Index("pending_items_request_idx", "request_id"),
    )

    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class WorkflowErrorRecord(Base):
    __tablename__ = "workflow_errors"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    step: Mapped[str] = mapped_column(workflow_step_enum, nullable=False)
    code: Mapped[str] = mapped_column(workflow_error_code_enum, nullable=False)
    message: Mapped[str] = mapped_column(sa.Text, nullable=False)
    retryable: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    __table_args__ = (
        sa.Index("workflow_errors_request_idx", "request_id"),
    )

    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class SolverAttemptRecord(Base):
    __tablename__ = "solver_attempts"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    step: Mapped[str] = mapped_column(workflow_step_enum, nullable=False)
    random_seed: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    time_limit_seconds: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    result: Mapped[str] = mapped_column(attempt_result_enum, nullable=False)
    violations: Mapped[dict | list] = mapped_column(JSONB(none_as_null=True), nullable=False, server_default=sa.text("'[]'"))
    itinerary_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    validation_result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    __table_args__ = (
        sa.UniqueConstraint('request_id', 'attempt_no'),
        sa.ForeignKeyConstraint(['request_id', 'itinerary_id'], ['itineraries.request_id', 'itineraries.itinerary_id']),
        sa.ForeignKeyConstraint(['request_id', 'itinerary_id', 'validation_result_id'], ['validation_results.request_id', 'validation_results.itinerary_id', 'validation_results.validation_result_id']),
        sa.Index("solver_attempts_request_idx", "request_id"),
    )

    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class ItineraryRecord(Base):
    __tablename__ = "itineraries"
    itinerary_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    parent_artifact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    attempt_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(itinerary_status_enum, nullable=False)
    currency: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("'VND'"))
    total_cost_min: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    total_cost_max: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    price_status: Mapped[str] = mapped_column(price_status_enum, nullable=False, server_default=sa.text("'UNKNOWN'"))
    total_travel_minutes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    total_scheduled_places: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    objective_value: Mapped[Decimal | None] = mapped_column(sa.Numeric(), nullable=True)
    solver_status: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    optimality_proven: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    unsatisfied_constraints: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    summary_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    parent_artifact_type: Mapped[str | None] = mapped_column(artifact_type_enum, sa.Computed("'itinerary'::public.artifact_type", persisted=True), nullable=True)
    __table_args__ = (
        sa.UniqueConstraint('request_id', 'itinerary_id'),
        sa.UniqueConstraint('request_id', 'attempt_no'),
        sa.ForeignKeyConstraint(['request_id', 'parent_artifact_type', 'parent_artifact_id'], ['workflow_artifacts.request_id', 'workflow_artifacts.artifact_type', 'workflow_artifacts.artifact_id']),
        sa.Index("itineraries_request_idx", "request_id"),
    )

    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class ItineraryDayRecord(Base):
    __tablename__ = "itinerary_days"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    itinerary_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    day: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    day_cost_min: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    day_cost_max: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    price_status: Mapped[str] = mapped_column(price_status_enum, nullable=False, server_default=sa.text("'UNKNOWN'"))
    __table_args__ = (
        sa.UniqueConstraint('itinerary_id', 'day'),
        sa.UniqueConstraint('request_id', 'id'),
        sa.ForeignKeyConstraint(['request_id', 'itinerary_id'], ['itineraries.request_id', 'itineraries.itinerary_id'], ondelete="CASCADE"),
        sa.Index("itinerary_days_request_idx", "request_id"),
    )

    itinerary: Mapped["ItineraryRecord"] = relationship(foreign_keys=[request_id, itinerary_id], viewonly=True)
    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class ItineraryActivityRecord(Base):
    __tablename__ = "itinerary_activities"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    itinerary_day_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    place_id: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey('places.place_id'), nullable=False)
    arrival_time: Mapped[time] = mapped_column(sa.Time, nullable=False)
    start_time: Mapped[time] = mapped_column(sa.Time, nullable=False)
    departure_time: Mapped[time] = mapped_column(sa.Time, nullable=False)
    travel_minutes_from_previous: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    cost_min: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    cost_max: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    price_status: Mapped[str] = mapped_column(price_status_enum, nullable=False, server_default=sa.text("'UNKNOWN'"))
    __table_args__ = (
        sa.UniqueConstraint('itinerary_day_id', 'seq'),
        sa.ForeignKeyConstraint(['request_id', 'itinerary_day_id'], ['itinerary_days.request_id', 'itinerary_days.id'], ondelete="CASCADE"),
        sa.Index('activities_place_idx', 'place_id'),
        sa.Index("itinerary_activities_request_idx", "request_id"),
    )

    day_record: Mapped["ItineraryDayRecord"] = relationship(foreign_keys=[request_id, itinerary_day_id], viewonly=True)
    place: Mapped["PlaceRecord"] = relationship(foreign_keys=[place_id], viewonly=True)
    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class ItineraryDroppedPlaceRecord(Base):
    __tablename__ = "itinerary_dropped_places"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    itinerary_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    place_id: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey('places.place_id'), nullable=False)
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    __table_args__ = (
        sa.ForeignKeyConstraint(['request_id', 'itinerary_id'], ['itineraries.request_id', 'itineraries.itinerary_id'], ondelete="CASCADE"),
        sa.Index('dropped_place_idx', 'place_id'),
        sa.Index("itinerary_dropped_places_request_idx", "request_id"),
    )

    itinerary: Mapped["ItineraryRecord"] = relationship(foreign_keys=[request_id, itinerary_id], viewonly=True)
    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class RelaxationSuggestionRecord(Base):
    __tablename__ = "relaxation_suggestions"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    itinerary_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    constraint_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload: Mapped[dict | list] = mapped_column(JSONB(none_as_null=True), nullable=False)
    chosen_by_user: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    __table_args__ = (
        sa.ForeignKeyConstraint(['request_id', 'itinerary_id'], ['itineraries.request_id', 'itineraries.itinerary_id'], ondelete="CASCADE"),
        sa.Index("relaxation_suggestions_request_idx", "request_id"),
    )

    itinerary: Mapped["ItineraryRecord"] = relationship(foreign_keys=[request_id, itinerary_id], viewonly=True)
    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class ValidationResultRecord(Base):
    __tablename__ = "validation_results"
    validation_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    itinerary_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    trip_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    parent_artifact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    schema_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_valid: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    suggested_action: Mapped[str] = mapped_column(validation_action_enum, nullable=False)
    checked_rules: Mapped[dict | list] = mapped_column(JSONB(none_as_null=True), nullable=False)
    recomputed: Mapped[dict | list] = mapped_column(JSONB(none_as_null=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    parent_artifact_type: Mapped[str | None] = mapped_column(artifact_type_enum, sa.Computed("'validation_result'::public.artifact_type", persisted=True), nullable=True)
    __table_args__ = (
        sa.UniqueConstraint('request_id', 'itinerary_id', 'validation_result_id'),
        sa.UniqueConstraint('request_id', 'validation_result_id'),
        sa.ForeignKeyConstraint(['request_id', 'itinerary_id'], ['itineraries.request_id', 'itineraries.itinerary_id'], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(['request_id', 'trip_id'], ['workflow_requests.request_id', 'workflow_requests.trip_id'], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(['request_id', 'parent_artifact_type', 'parent_artifact_id'], ['workflow_artifacts.request_id', 'workflow_artifacts.artifact_type', 'workflow_artifacts.artifact_id']),
        sa.Index('validation_trip_idx', 'trip_id'),
        sa.Index("validation_results_request_idx", "request_id"),
    )

    itinerary: Mapped["ItineraryRecord"] = relationship(foreign_keys=[request_id, itinerary_id], viewonly=True)
    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class ValidationIssueRecord(Base):
    __tablename__ = "validation_issues"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    validation_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(issue_kind_enum, nullable=False)
    severity: Mapped[str] = mapped_column(issue_severity_enum, nullable=False)
    rule: Mapped[str] = mapped_column(sa.Text, nullable=False)
    type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    day: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    place_id: Mapped[str | None] = mapped_column(sa.Text, sa.ForeignKey('places.place_id'), nullable=True)
    actual: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    expected_or_limit: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    message: Mapped[str] = mapped_column(sa.Text, nullable=False)
    __table_args__ = (
        sa.ForeignKeyConstraint(['request_id', 'validation_result_id'], ['validation_results.request_id', 'validation_results.validation_result_id'], ondelete="CASCADE"),
        sa.Index('issues_result_kind_idx', 'validation_result_id', 'kind'),
        sa.Index('issues_place_idx', 'place_id'),
        sa.Index("validation_issues_request_idx", "request_id"),
    )

    validation: Mapped["ValidationResultRecord"] = relationship(foreign_keys=[request_id, validation_result_id], viewonly=True)
    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class PlaceRecord(Base):
    __tablename__ = "places"
    place_id: Mapped[str] = mapped_column(sa.Text, primary_key=True, nullable=False)
    google_place_id: Mapped[str | None] = mapped_column(sa.Text, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    category: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    types: Mapped[list[str] | None] = mapped_column(ARRAY(sa.Text), nullable=True)
    google_maps_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    rating: Mapped[Decimal | None] = mapped_column(sa.Numeric(2,1), nullable=True)
    user_rating_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    business_status: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(sa.Double, nullable=True)
    longitude: Mapped[float | None] = mapped_column(sa.Double, nullable=True)
    address: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    timezone: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reservation_required: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    accessibility_notes: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    source: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    opening_hours_verified: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    opening_hours: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    photos: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    visit_duration: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    price: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), server_onupdate=sa.FetchedValue())

class RequestPlaceCandidateRecord(Base):
    __tablename__ = "request_place_candidates"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('workflow_requests.request_id', ondelete="CASCADE"), nullable=False)
    place_id: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey('places.place_id'), nullable=False)
    schema_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    score_places: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    matched_interests: Mapped[dict | list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    cluster_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(candidate_source_enum, nullable=False)
    original_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    candidate_status: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    price_min: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    price_max: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    price_status: Mapped[str] = mapped_column(price_status_enum, nullable=False, server_default=sa.text("'UNKNOWN'"))
    price_confidence_score: Mapped[Decimal | None] = mapped_column(sa.Numeric(3,2), nullable=True)
    admission_price_raw: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    __table_args__ = (
        sa.UniqueConstraint('request_id', 'place_id'),
        sa.Index('candidates_place_idx', 'place_id'),
        sa.Index("request_place_candidates_request_idx", "request_id"),
    )

    place: Mapped["PlaceRecord"] = relationship(foreign_keys=[place_id], viewonly=True)
    request: Mapped["WorkflowRequestRecord"] = relationship(foreign_keys=[request_id], viewonly=True)

class TravelTimeCacheRecord(Base):
    __tablename__ = "travel_time_cache"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()'))
    from_place_id: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey('places.place_id', ondelete="CASCADE"), nullable=False)
    to_place_id: Mapped[str] = mapped_column(sa.Text, sa.ForeignKey('places.place_id', ondelete="CASCADE"), nullable=False)
    transport_mode: Mapped[str] = mapped_column(sa.Text, nullable=False)
    departure_bucket: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    distance_meters: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    schema_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    __table_args__ = (
        sa.UniqueConstraint('from_place_id', 'to_place_id', 'transport_mode', 'departure_bucket'),
        sa.Index('travel_cache_to_idx', 'to_place_id'),
    )

    from_place: Mapped["PlaceRecord"] = relationship(foreign_keys=[from_place_id], viewonly=True)
    to_place: Mapped["PlaceRecord"] = relationship(foreign_keys=[to_place_id], viewonly=True)

WorkflowRecord = WorkflowRequestRecord
ArtifactRecord = WorkflowArtifactRecord
