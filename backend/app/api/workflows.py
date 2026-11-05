"""Authenticated persistence API. Sync routes keep SQLAlchemy off the event loop."""
import asyncio
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.api.auth import get_current_user_id
from app.db.session import get_session
from app.models.contracts import TripRequest
from app.repositories.workflows import TripRepository, RequestRepository
from app.repositories.artifacts import ArtifactRepository
from app.services.persistence import WorkflowPersistence
from app.services.graph_workflow import LangGraphOrchestrator, GraphRun
from app.services.workflow_factory import get_graph_orchestrator

router = APIRouter(prefix='/api/v1', tags=['Persistence'])


class TripCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str | None = None


class TripView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    trip_id: UUID
    user_id: UUID
    title: str | None


class RequestView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    request_id: UUID
    trip_id: UUID
    schema_version: str
    status: str
    current_step: str
    clarification_round: int
    max_clarification_rounds: int
    destination_round: int
    retry_count: int


class RunInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    trip_request: TripRequest
    answer_raw: str | None = None
    expected_transitions: int | None = None


@router.post('/trips', response_model=TripView, status_code=201)
def create_trip(body: TripCreate, user: UUID = Depends(get_current_user_id), session: Session = Depends(get_session)):
    return TripRepository(session, user).create(title=body.title)


@router.get('/trips/{trip_id}', response_model=TripView)
def get_trip(trip_id: UUID, user: UUID = Depends(get_current_user_id), session: Session = Depends(get_session)):
    return TripRepository(session, user).get(trip_id)


@router.post('/trips/{trip_id}/requests', response_model=RequestView, status_code=201)
def create_request(trip_id: UUID, user: UUID = Depends(get_current_user_id), session: Session = Depends(get_session)):
    return RequestRepository(session, user).create(trip_id)


@router.get('/requests/{request_id}', response_model=RequestView)
def get_request(request_id: UUID, user: UUID = Depends(get_current_user_id), session: Session = Depends(get_session)):
    return RequestRepository(session, user).get(request_id)


@router.get('/requests/{request_id}/artifacts/{artifact_type}')
def latest_artifact(request_id: UUID, artifact_type: str, user: UUID = Depends(get_current_user_id),
                    session: Session = Depends(get_session)):
    from app.services.persistence import TYPES
    if artifact_type not in TYPES.values():
        raise HTTPException(422, 'Invalid artifact type')
    row = RequestRepository(session, user).get(request_id)
    if row.graph_snapshot is not None:
        from app.services.workflow_state import STEPS, REFS
        run = WorkflowPersistence(session, user).load_graph(request_id)
        step = next(s for s, kind in TYPES.items() if kind == artifact_type)
        identifier = getattr(run.state.artifacts, REFS[STEPS.index(step)])
        artifact = ArtifactRepository(session, user).get(identifier) if identifier else None
    else:
        artifact = ArtifactRepository(session, user).latest(request_id, artifact_type)
    if artifact is None:
        raise HTTPException(404, 'Artifact not found')
    return dict(artifact_id=artifact.artifact_id, request_id=artifact.request_id,
        artifact_type=artifact.artifact_type, parent_artifact_id=artifact.parent_artifact_id,
        is_latest=artifact.is_latest, schema_version=artifact.schema_version, payload=artifact.payload)


@router.post('/requests/{request_id}/mock-run', response_model=GraphRun)
def persist_mock_run(request_id: UUID, body: RunInput, user: UUID = Depends(get_current_user_id),
                     session: Session = Depends(get_session),
                     graph: LangGraphOrchestrator = Depends(get_graph_orchestrator)):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    persistence = WorkflowPersistence(session, user)
    row = persistence.request(request_id, lock=True)
    previous = None
    if row.status in {'clarifying', 'awaiting_relaxation'}:
        if body.answer_raw is None:
            raise HTTPException(422, 'answer_raw is required to resume')
        previous = persistence.load_graph(request_id)
        if body.expected_transitions is not None and previous.transitions != body.expected_transitions:
            raise HTTPException(409, 'Workflow changed; reload before resuming')
    elif row.status != 'parsing':
        raise HTTPException(409, 'Create a new request for a new run')
    graph.persistence = persistence
    return asyncio.run(graph.run(body.trip_request,
            current_date=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date(), previous=previous,
            answer_raw=body.answer_raw, trip_id=row.trip_id, request_id=request_id))


@router.get('/requests/{request_id}/run', response_model=GraphRun)
def get_run(request_id: UUID, user: UUID = Depends(get_current_user_id),
            session: Session = Depends(get_session)):
    return WorkflowPersistence(session, user).load_graph(request_id)


@router.get('/requests/{request_id}/result')
def get_result(request_id: UUID, user: UUID = Depends(get_current_user_id),
               session: Session = Depends(get_session)):
    run = WorkflowPersistence(session, user).load_graph(request_id)
    if run.state.status != 'completed' or run.final_result is None:
        raise HTTPException(409, 'Workflow has no accepted final result')
    return run.final_result
