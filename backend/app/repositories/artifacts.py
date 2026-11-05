from uuid import UUID, uuid4
from sqlalchemy import select
from app.db.models import ArtifactRecord, TripRecord, WorkflowRequestRecord
from app.models.contracts import Contract
from app.repositories.workflows import OwnedRepository


class ArtifactRepository(OwnedRepository):
    """Append-only API. Caller owns the transaction; no implicit commits.

    Database also rejects UPDATE/DELETE so a stored result ID stays immutable.
    """

    def add(self, request_id: UUID, artifact_type: str, payload: Contract,
            *, artifact_id: UUID | None = None) -> ArtifactRecord:
        self.request(request_id, lock=True)
        latest = self.session.scalar(select(ArtifactRecord).where(
            ArtifactRecord.request_id == request_id, ArtifactRecord.artifact_type == artifact_type,
            ArtifactRecord.is_latest.is_(True)).execution_options(populate_existing=True))
        record = ArtifactRecord(artifact_id=artifact_id or uuid4(), request_id=request_id,
                                artifact_type=artifact_type, is_latest=True,
                                parent_artifact_id=latest.artifact_id if latest else None,
                                schema_version=payload.schema_version,
                                payload=payload.model_dump(mode="json"))
        self.session.add(record)
        self.session.flush()
        if latest is not None:
            # Canonical INSERT trigger retired this marker; refresh ORM state lazily.
            self.session.expire(latest)
        return record

    def get(self, artifact_id: UUID) -> ArtifactRecord | None:
        return self.session.scalar(select(ArtifactRecord)
            .join(WorkflowRequestRecord, ArtifactRecord.request_id == WorkflowRequestRecord.request_id)
            .join(TripRecord, WorkflowRequestRecord.trip_id == TripRecord.trip_id)
            .where(ArtifactRecord.artifact_id == artifact_id, TripRecord.user_id == self.user_id))

    def latest(self, request_id: UUID, artifact_type: str) -> ArtifactRecord | None:
        self.request(request_id)
        return self.session.scalar(select(ArtifactRecord).where(
            ArtifactRecord.request_id == request_id, ArtifactRecord.artifact_type == artifact_type,
            ArtifactRecord.is_latest.is_(True)))
