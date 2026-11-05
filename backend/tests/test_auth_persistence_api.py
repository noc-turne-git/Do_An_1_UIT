from uuid import uuid4
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user_id
from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app


def app():
    return create_app(Settings(_env_file=None, database_url=None,
        supabase_url='https://example.supabase.co', supabase_publishable_key='test-key'))


def test_missing_token_rejected_before_database_access():
    application = app()
    with TestClient(application) as client:
        assert client.post('/api/v1/trips', json={'title': 'Trip'}).status_code == 401


@pytest.mark.parametrize('status,expected', [(401, 401), (403, 401), (500, 503)])
def test_invalid_token_or_provider_error(monkeypatch, status, expected):
    monkeypatch.setattr(httpx, 'get', lambda *args, **kwargs: httpx.Response(status))
    with TestClient(app()) as client:
        assert client.post('/api/v1/trips', json={}, headers={'Authorization': 'Bearer bad'}).status_code == expected


def test_verified_subject_is_trip_owner_and_dependency_is_overridable(monkeypatch):
    application, user = app(), uuid4()
    calls = []
    def verified(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={'id': str(user)})
    monkeypatch.setattr(httpx, 'get', verified)
    session = MagicMock()
    application.dependency_overrides[get_session] = lambda: session
    with TestClient(application) as client:
        response = client.post('/api/v1/trips', json={'title': 'Trip'}, headers={'Authorization': 'Bearer verified'})
        assert response.status_code == 201
        assert response.json()['user_id'] == str(user)
        assert calls[0][1]['headers']['Authorization'] == 'Bearer verified'
        assert calls[0][1]['follow_redirects'] is False
        # Body cannot impersonate another owner, even with a verified token.
        response = client.post('/api/v1/trips', json={'user_id': str(uuid4())}, headers={'Authorization': 'Bearer verified'})
        assert response.status_code == 422
        application.dependency_overrides[get_current_user_id] = lambda: user
        assert client.post('/api/v1/trips', json={}).status_code == 201


def test_other_owner_returns_404():
    application, session = app(), MagicMock()
    session.scalar.return_value = None
    application.dependency_overrides[get_current_user_id] = uuid4
    application.dependency_overrides[get_session] = lambda: session
    with TestClient(application) as client:
        assert client.get(f'/api/v1/trips/{uuid4()}').status_code == 404
        assert client.get(f'/api/v1/requests/{uuid4()}').status_code == 404
        assert client.post(f'/api/v1/trips/{uuid4()}/requests').status_code == 404
