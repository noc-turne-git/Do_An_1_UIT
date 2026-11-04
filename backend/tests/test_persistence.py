from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.orm import configure_mappers

from app.core.errors import ApplicationError
from app.db.base import Base
from app.db.models import TripRecord, WorkflowRequestRecord, WorkflowArtifactRecord
from app.models.contracts import TripRequest
from app.repositories.artifacts import ArtifactRepository
from app.repositories.workflows import TripRepository, RequestRepository
from app.services.mock_workflow import fixture


def test_core_mapping():
    configure_mappers()
    assert len(Base.metadata.tables) == 19
    assert 'state' not in WorkflowRequestRecord.__table__.c
    assert 'revision' not in WorkflowRequestRecord.__table__.c
    for cls, key in [(TripRecord, 'trip_id'), (WorkflowRequestRecord, 'request_id'),
                     (WorkflowArtifactRecord, 'artifact_id')]:
        assert cls.__table__.c[key].type.as_uuid


def test_trip_creation_uses_authenticated_owner():
    session, user = MagicMock(), uuid4()
    row = TripRepository(session, user).create(title='Trip')
    assert row.user_id == user
    session.commit.assert_not_called()


def test_request_creation_checks_trip_owner_before_write():
    session = MagicMock()
    session.scalar.return_value = None
    with pytest.raises(ApplicationError, match='Trip not found'):
        RequestRepository(session, uuid4()).create(uuid4())
    session.add.assert_not_called()


@pytest.mark.parametrize('action', ['read_trip', 'read_request', 'write_artifact', 'read_latest'])
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


def test_artifact_read_filters_owner_in_query():
    session, user = MagicMock(), uuid4()
    session.scalar.return_value = None
    assert ArtifactRepository(session, user).get(uuid4()) is None
    query = session.scalar.call_args.args[0]
    compiled = query.compile(dialect=dialect())
    assert 'trips.user_id =' in str(compiled) and user in compiled.params.values()


def test_itinerary_projection_keeps_price_status_and_uuid():
    from app.models.contracts import Itinerary
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


def test_validation_projection_checks_itinerary_and_keeps_findings():
    from app.models.contracts import ValidationResult
    from app.repositories.results import ResultRepository
    from app.db.models import ItineraryRecord, ValidationIssueRecord
    data = fixture('validation_result')
    data.update(is_valid=False, suggested_action='replan', violations=[
        dict(type='over_budget', rule='budget', severity='hard', actual=5, limit=3, message='over')])
    value = ValidationResult.model_validate(data)
    session, request, itinerary = MagicMock(), uuid4(), uuid4()
    owner = WorkflowRequestRecord(request_id=request, trip_id=value.trip_id)
    session.scalar.side_effect = [owner, owner, ItineraryRecord(itinerary_id=itinerary)]
    artifact = WorkflowArtifactRecord(artifact_id=uuid4(), parent_artifact_id=None)
    row = ResultRepository(session, uuid4()).validation(request, artifact, itinerary, value)
    issues = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], ValidationIssueRecord)]
    assert row.trip_id == value.trip_id and row.itinerary_id == itinerary
    assert issues[0].actual == '5' and issues[0].expected_or_limit == '3'


@pytest.mark.parametrize('value', [92.0, 92.5, '92', True, -1, 101])
def test_candidate_score_never_rounds_or_coerces(value):
    from pydantic import ValidationError
    from app.models.contracts import PlaceCandidate
    data = fixture('place_candidates')[0]
    data['suitability']['score_places'] = value
    with pytest.raises(ValidationError):
        PlaceCandidate.model_validate(data)


def test_raw_admission_price_is_text_not_dict():
    from pydantic import ValidationError
    from app.models.contracts import CostedPlaceCandidate
    data = fixture('costed_place_candidates')[0]
    data['admission_price_raw'] = 'Người lớn: 50.000đ'
    assert CostedPlaceCandidate.model_validate(data).admission_price_raw == data['admission_price_raw']
    data['admission_price_raw'] = {'adult': 50000}
    with pytest.raises(ValidationError):
        CostedPlaceCandidate.model_validate(data)


@pytest.mark.parametrize('level', ['summary', 'day', 'activity'])
def test_itinerary_requires_explicit_price_status(level):
    from pydantic import ValidationError
    from app.models.contracts import Itinerary
    data = fixture('itinerary')
    node = data['summary'] if level == 'summary' else data['days'][0] if level == 'day' else data['days'][0]['activities'][0]
    del node['price_status']
    with pytest.raises(ValidationError):
        Itinerary.model_validate(data)
