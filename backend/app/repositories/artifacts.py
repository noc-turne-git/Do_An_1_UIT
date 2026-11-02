from sqlalchemy.orm import Session

from app.db.models import ArtifactRecord
from app.models.contracts import Contract


class ArtifactRepository:
    """Append-only API. Caller owns the transaction; no implicit commits.

    Database also rejects UPDATE/DELETE so a stored result ID stays immutable.
    """

    def __init__(self, session: Session):
        self.session = session

    def add(self, artifact_id: str, request_id: str, kind: str, payload: Contract) -> ArtifactRecord:
        record = ArtifactRecord(artifact_id=artifact_id, request_id=request_id, kind=kind,
                                schema_version=payload.schema_version,
                                payload=payload.model_dump(mode="json"))
        self.session.add(record)
        self.session.flush()
        return record

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        return self.session.get(ArtifactRecord, artifact_id)
