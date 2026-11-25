from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.orm import configure_mappers

from shared.errors import ApplicationError
from app.db.base import Base
from app.db.models import ClarificationRoundRecord, TripRecord, WorkflowRequestRecord, WorkflowArtifactRecord
from shared.contracts import AnswerHistory, TripRequest, WorkflowState
from app.repositories.artifacts import ArtifactRepository
from app.repositories.workflows import TripRepository, RequestRepository
from ai.orchestration.mock_workflow import fixture


def test_core_mapping():
    configure_mappers()
    assert len(Base.metadata.tables) == 25
    assert 'state' not in WorkflowRequestRecord.__table__.c
    assert 'revision' not in WorkflowRequestRecord.__table__.c
    for cls, key in [(TripRecord, 'trip_id'), (WorkflowRequestRecord, 'request_id'),
                     (WorkflowArtifactRecord, 'artifact_id')]:
        assert cls.__table__.c[key].type.as_uuid
    assert WorkflowRequestRecord.__table__.c.max_destination_rounds.server_default is None
    assert WorkflowRequestRecord.__table__.c.max_destination_rounds.default.is_callable
    assert ClarificationRoundRecord.__table__.c.kind.server_default.arg.text == "'trip_request'"
    assert any(set(constraint.columns.keys()) == {'request_id', 'kind', 'round'}
               for constraint in ClarificationRoundRecord.__table__.constraints
               if constraint.__class__.__name__ == 'UniqueConstraint')


def test_legacy_graph_snapshot_defaults_clarification_kinds():
    from ai.orchestration.graph_workflow import GraphRun
    state = WorkflowState(request_id=uuid4(), trip_id=uuid4(), status='clarifying',
        current_step='request_parser', completed_steps=[], artifacts={}, clarification_round=1,
        pending_fields=['trip.start_date'], retry_count=0).model_dump()
    state.pop('destination_round')
    state.pop('max_destination_rounds')
    snapshot = dict(state=state, answers_history=[dict(round=1, asked_fields=['trip.start_date'],
        question='Ngày nào?', answer_raw='14/11', resolved_fields=['trip.start_date'],
        declared_unknown_fields=[])])
    restored = GraphRun.model_validate(snapshot)
    assert restored.state.destination_round == 0
    assert restored.state.max_destination_rounds == 10
    assert restored.answers_history == [AnswerHistory(round=1, kind='trip_request',
        asked_fields=['trip.start_date'], question='Ngày nào?', answer_raw='14/11',
        resolved_fields=['trip.start_date'], declared_unknown_fields=[])]


@pytest.mark.parametrize('action', ['read_trip', 'read_request', 'write_artifact', 'read_latest'])
@pytest.mark.smoke
def test_missing_or_other_owner_denied(action):
    session, user, identifier = MagicMock(), uuid4(), uuid4()
    session.scalar.return_value = None
    with pytest.raises(ApplicationError):
        if action == 'read_trip': TripRepository(session, user).get(identifier)
        elif action == 'read_request': RequestRepository(session, user).get(identifier)
        elif action == 'read_latest': ArtifactRepository(session, user).latest(identifier, 'trip_request')
        else: ArtifactRepository(session, user).add(identifier, 'trip_request', TripRequest.model_validate(fixture('trip_request')))
    query = str(session.scalar.call_args.args[0].compile(dialect=dialect()))
    assert 'trips.user_id =' in query
    session.add.assert_not_called()


def test_artifact_version_uses_parent_and_request_lock():
    session, user, request, parent = MagicMock(), uuid4(), uuid4(), uuid4()
    previous = WorkflowArtifactRecord(artifact_id=parent)
    session.scalar.side_effect = [WorkflowRequestRecord(request_id=request), previous]
    row = ArtifactRepository(session, user).add(request, 'trip_request', TripRequest.model_validate(fixture('trip_request')))
    assert row.parent_artifact_id == parent and row.is_latest
    assert 'FOR UPDATE OF workflow_requests' in str(session.scalar.call_args_list[0].args[0].compile(dialect=dialect()))
    session.expire.assert_called_once_with(previous)
    session.commit.assert_not_called()


def test_itinerary_projection_keeps_price_status_and_uuid():
    from shared.contracts import Itinerary
    from app.repositories.results import ResultRepository
    from app.db.models import ItineraryActivityRecord
    value = Itinerary.model_validate(fixture('itinerary'))
    session, request = MagicMock(), uuid4()
    session.scalar.return_value = WorkflowRequestRecord(request_id=request, trip_id=value.trip_id)
    artifact = WorkflowArtifactRecord(artifact_id=uuid4(), parent_artifact_id=None)
    row = ResultRepository(session, uuid4()).itinerary(request, artifact, value, 1)
    assert row.itinerary_id == artifact.artifact_id
    assert row.price_status == value.summary.price_status
    activities = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], ItineraryActivityRecord)]
    assert len(activities) == 3
    assert all(a.request_id == request and a.price_status == 'ESTIMATED' for a in activities)


@pytest.mark.parametrize('value', [92.5, True, -1])
def test_candidate_score_never_rounds_or_coerces(value):
    from pydantic import ValidationError
    from shared.contracts import PlaceCandidate
    data = fixture('place_candidates')[0]
    data['suitability']['score_places'] = value
    with pytest.raises(ValidationError):
        PlaceCandidate.model_validate(data)


@pytest.mark.parametrize('level', ['summary', 'activity'])
def test_itinerary_requires_explicit_price_status(level):
    from pydantic import ValidationError
    from shared.contracts import Itinerary
    data = fixture('itinerary')
    node = data['summary'] if level == 'summary' else data['days'][0] if level == 'day' else data['days'][0]['activities'][0]
    del node['price_status']
    with pytest.raises(ValidationError):
        Itinerary.model_validate(data)
