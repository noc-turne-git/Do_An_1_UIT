"""Owner checks are mandatory: admin DB connections bypass RLS.

user_id must come from verified authentication. Caller owns the transaction.
"""
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.errors import ApplicationError
from app.db.models import TripRecord, WorkflowRequestRecord


class OwnedRepository:
    def __init__(self, session: Session, user_id: UUID):
        self.session = session
        self.user_id = UUID(str(user_id))

    def trip(self, trip_id: UUID) -> TripRecord:
        row = self.session.scalar(select(TripRecord).where(
            TripRecord.trip_id == trip_id, TripRecord.user_id == self.user_id))
        if row is None:
            raise ApplicationError("not_found", "Trip not found")
        return row

    def request(self, request_id: UUID, *, lock: bool = False) -> WorkflowRequestRecord:
        query = select(WorkflowRequestRecord).join(TripRecord).where(
            WorkflowRequestRecord.request_id == request_id, TripRecord.user_id == self.user_id)
        if lock:
            query = query.with_for_update(of=WorkflowRequestRecord)
        row = self.session.scalar(query)
        if row is None:
            raise ApplicationError("not_found", "Request not found")
        return row


class TripRepository(OwnedRepository):
    def create(self, *, title: str | None = None) -> TripRecord:
        row = TripRecord(trip_id=uuid4(), user_id=self.user_id, title=title)
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, trip_id: UUID) -> TripRecord:
        return self.trip(trip_id)


class RequestRepository(OwnedRepository):
    def create(self, trip_id: UUID, *, schema_version: str = "1.0") -> WorkflowRequestRecord:
        self.trip(trip_id)
        row = WorkflowRequestRecord(request_id=uuid4(), trip_id=trip_id, schema_version=schema_version)
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, request_id: UUID) -> WorkflowRequestRecord:
        return self.request(request_id)

    def update_projection(self, state) -> WorkflowRequestRecord:
        row = self.request(state.request_id, lock=True)
        if row.trip_id != state.trip_id:
            raise ApplicationError("planning_input_inconsistent", "Trip and request differ")
        for field in ("status", "current_step", "clarification_round", "max_clarification_rounds",
                      "destination_round", "retry_count"):
            setattr(row, field, getattr(state, field))
        self.session.flush()
        return row
