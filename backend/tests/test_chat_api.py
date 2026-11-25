from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from app.api.auth import get_current_user_id
from app.core.config import Settings
from app.db.models import AnonymousSessionRecord, MessageRecord, TripRecord, ConversationRecord
from app.db.session import get_session
from app.main import create_app
from shared.contracts import TripRequest
from ai.orchestration.mock_workflow import fixture
from ai.orchestration.request_parser import empty_request
from ai.orchestration.turns import TurnResult
from app.db.models import WorkflowRequestRecord, WorkflowArtifactRecord


def setup_client(settings=None):
    app = create_app(settings or Settings(_env_file=None))
    session = MagicMock()
    session.bind = None
    session.get.return_value = None
    user = uuid4()
    app.dependency_overrides[get_current_user_id] = lambda: user
    app.dependency_overrides[get_session] = lambda: session
    def fill_defaults():
        for call in session.add.call_args_list:
            row = call.args[0]
            if isinstance(row, MessageRecord):
                row.created_at = datetime.now(timezone.utc)
    session.flush.side_effect = fill_defaults
    return app, session, user


def test_send_creates_conversation_without_trip_and_stores_unicode_message(caplog):
    app, session, user = setup_client()
    turn = TurnResult(empty_request(), 'Mình có thể giúp gì?', planning=False)
    with patch('app.api.chat.run_turn', return_value=turn), TestClient(app) as client, caplog.at_level('INFO'):
        response = client.post('/api/v1/chat/messages', json={'content': '  Đi Đà Lạt 3 ngày  '})
    assert response.status_code == 201, response.text
    data = response.json()
    rows = [call.args[0] for call in session.add.call_args_list]
    assert isinstance(rows[0], ConversationRecord) and rows[0].user_id == user
    assert rows[1].conversation_id == rows[0].conversation_id
    assert not any(isinstance(row, TripRecord) for row in rows)
    assert data['content'] == 'Đi Đà Lạt 3 ngày' and data['role'] == 'user'
    assert response.headers['x-request-id']
    assert response.headers['x-trace-run-id']
    assert 'chat.message_staged' in caplog.text
    assert data['content'] not in caplog.text


def test_foreign_or_missing_trip_cannot_send_or_read():
    app, session, _ = setup_client()
    session.scalar.return_value = None
    trip = str(uuid4())
    with TestClient(app) as client:
        assert client.post('/api/v1/chat/messages', json={'conversation_id': trip, 'content': 'Hello'}).status_code == 404
        assert client.get(f'/api/v1/chat/conversations/{trip}/messages').status_code == 404
        assert client.get(f'/api/v1/chat/conversations/{trip}').status_code == 404
        assert client.post(f'/api/v1/chat/conversations/{trip}/prepare-trip',
                           json={'trip_request': fixture('trip_request')}).status_code == 404
    session.add.assert_not_called()


def test_rejects_invalid_messages_and_missing_auth():
    app, session, _ = setup_client()
    with TestClient(app) as client:
        for body in ({'content': '  '}, {'content': 'a' * 10001}, {'content': 'Hello', 'role': 'assistant'}):
            assert client.post('/api/v1/chat/messages', json=body).status_code == 422
        app.dependency_overrides.pop(get_current_user_id)
        assert client.post('/api/v1/chat/messages', json={'content': 'Hello'}).status_code == 401
    session.add.assert_not_called()


def test_guest_session_owns_persisted_chat_without_a_bearer_token():
    app, session, _ = setup_client()
    app.dependency_overrides.pop(get_current_user_id)
    guest_id = uuid4()
    session.get.side_effect = lambda model, key: (
        AnonymousSessionRecord(anonymous_session_id=guest_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1))
        if model is AnonymousSessionRecord else None)
    turn = TurnResult(empty_request(), 'Welcome!', planning=False)
    with patch('app.api.chat.run_turn', return_value=turn), TestClient(app) as client:
        response = client.post('/api/v1/chat/messages', headers={
            'X-Anonymous-Session-ID': str(guest_id)}, json={'content': 'Hello'})
    assert response.status_code == 201, response.text
    conversation = next(call.args[0] for call in session.add.call_args_list
                        if isinstance(call.args[0], ConversationRecord))
    assert conversation.user_id is None
    assert conversation.anonymous_session_id == guest_id


def test_prepare_complete_request_creates_trip_workflow_and_artifact_once():
    app, session, user = setup_client()
    conversation = ConversationRecord(conversation_id=uuid4(), user_id=user)
    trip = TripRecord(trip_id=uuid4(), user_id=user)
    workflow = WorkflowRequestRecord(request_id=uuid4(), trip_id=trip.trip_id)
    session.scalar.side_effect = [conversation, trip, workflow, None, conversation]
    # This is an actual structured request checked by Pydantic, not a mocked parser result.
    from support import confirmed_trip_request
    payload = TripRequest.model_validate(confirmed_trip_request()).model_dump(mode='json')
    with TestClient(app) as client:
        url = f'/api/v1/chat/conversations/{conversation.conversation_id}/prepare-trip'
        first = client.post(url, json={'trip_request': payload})
        assert first.status_code == 200, first.text
        second = client.post(url, json={'trip_request': payload})
        assert second.status_code == 200
        assert first.json() == second.json()
    rows = [call.args[0] for call in session.add.call_args_list]
    assert sum(isinstance(row, TripRecord) for row in rows) == 1
    assert sum(isinstance(row, WorkflowRequestRecord) for row in rows) == 1
    artifact = next(row for row in rows if isinstance(row, WorkflowArtifactRecord))
    assert artifact.payload == payload
