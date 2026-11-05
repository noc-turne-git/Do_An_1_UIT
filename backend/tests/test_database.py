"""Opt-in local integration tests. Never read DATABASE_URL or execute old Alembic."""
import os
from pathlib import Path
from uuid import UUID, uuid4
import asyncio
from datetime import date

import pytest
from sqlalchemy import inspect, text, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from shared.errors import ApplicationError
from app.db.session import Database
from app.db.models import WorkflowArtifactRecord, WorkflowRequestRecord
from shared.contracts import TripRequest
from app.repositories.workflows import TripRepository, RequestRepository
from app.repositories.artifacts import ArtifactRepository
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.graph_workflow import LangGraphOrchestrator
from app.services.persistence import WorkflowPersistence

ROOT = Path(__file__).parents[1]


def test_database_without_configuration():
    db = Database(Settings(_env_file=None, database_url=None))
    assert db.engine is None
    db.dispose()


@pytest.fixture(scope='module')
def database():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set TEST_DATABASE_URL to a dedicated empty LOCAL disposable database')
    parsed = make_url(url)
    assert parsed.host in {'localhost', '127.0.0.1', '::1'}, 'Refusing non-local test database'
    assert parsed.database and 'test' in parsed.database.lower(), 'Database name must contain test'
    db = Database(Settings(_env_file=None, database_url=url))
    with db.engine.begin() as connection:
        assert not inspect(connection).get_table_names(schema='public'), 'Refusing nonempty database'
        assert not inspect(connection).has_schema('auth'), 'Refusing database with existing auth schema'
        # Minimal Supabase platform scaffold, only in an empty local disposable DB.
        connection.execute(text("""DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
        END $$"""))
        connection.execute(text('CREATE SCHEMA auth'))
        connection.execute(text("CREATE TABLE auth.users(id uuid PRIMARY KEY, raw_user_meta_data jsonb NOT NULL DEFAULT '{}')"))
        connection.execute(text("""CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
          SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$"""))
        connection.execute(text('GRANT USAGE ON SCHEMA auth, public TO anon, authenticated, service_role'))
    # Execute canonical SQL exactly, including transaction and triggers; no create_all.
    with db.engine.connect() as connection:
        connection = connection.execution_options(isolation_level='AUTOCOMMIT')
        # No DBAPI parameters: PL/pgSQL format('%I') must not be parsed as placeholders.
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute((ROOT / 'supabase/schema.sql').read_text(encoding='utf-8'))
    yield db
    db.dispose()
    # Intentionally no destructive teardown. Recreate disposable DB before next run.


def seed(db):
    user = uuid4()
    with db.engine.begin() as c:
        c.execute(text('INSERT INTO auth.users(id) VALUES (:id)'), {'id': user})
    with db.sessions.begin() as session:
        trip = TripRepository(session, user).create(title='test')
        request = RequestRepository(session, user).create(trip.trip_id)
        return user, trip.trip_id, request.request_id


@pytest.mark.postgres
def test_conversation_to_trip_with_real_persistence(database):
    from fastapi.testclient import TestClient
    from app.api.auth import get_current_user_id
    from app.db.session import get_session
    from app.main import create_app
    from app.db.models import TripRecord, MessageRecord, ConversationRecord
    user = uuid4()
    with database.engine.begin() as connection:
        connection.execute(text('INSERT INTO auth.users(id) VALUES (:id)'), {'id': user})
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_current_user_id] = lambda: user
    app.dependency_overrides[get_session] = database.session
    with TestClient(app) as client:
        first = client.post('/api/v1/chat/messages', json={'content': 'Travel ideas'}).json()
        identifier = first['conversation_id']
        for content in ['Da Lat', 'Two adults']:
            assert client.post('/api/v1/chat/messages', json={
                'conversation_id': identifier, 'content': content}).status_code == 201
        with database.sessions() as session:
            assert session.scalar(select(func.count()).select_from(TripRecord).where(TripRecord.user_id == user)) == 0
        assert len(client.get(f'/api/v1/chat/conversations/{identifier}/messages').json()) == 3
        assert client.get(f'/api/v1/chat/conversations/{identifier}').json()['trip_id'] is None
        url = f'/api/v1/chat/conversations/{identifier}/prepare-trip'
        payload = fixture('trip_request')
        payload['budget']['amount'] = None
        assert client.post(url, json={'trip_request': payload}).status_code == 400
        payload = fixture('trip_request')
        response = client.post(url, json={'trip_request': payload})
        assert response.status_code == 200, response.text
        assert client.post(url, json={'trip_request': payload}).json() == response.json()
        with database.sessions() as session:
            assert session.scalar(select(func.count()).select_from(TripRecord).where(TripRecord.user_id == user)) == 1
            conversation = session.get(ConversationRecord, UUID(identifier))
            assert conversation.trip_request == TripRequest.model_validate(payload).model_dump(mode='json')
            assert session.get(WorkflowRequestRecord, conversation.request_id).trip_id == conversation.trip_id
    # A new browser session recovers the same conversation from the URL ID.
    with TestClient(app) as client:
        assert len(client.get(f'/api/v1/chat/conversations/{identifier}/messages').json()) == 3
        app.dependency_overrides[get_current_user_id] = uuid4
        assert client.get(f'/api/v1/chat/conversations/{identifier}/messages').status_code == 404


@pytest.mark.postgres
def test_schema_metadata_matches_columns_and_fks(database):
    from app.db.base import Base
    inspector = inspect(database.engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables)
    for table in Base.metadata.tables.values():
        actual = {c['name']: c for c in inspector.get_columns(table.name)}
        assert set(actual) == set(table.c.keys()), table.name
        for column in table.c:
            assert actual[column.name]['nullable'] == column.nullable, (table.name, column.name)
            assert str(actual[column.name]['type'].compile(dialect=database.engine.dialect)).removeprefix('public.') == str(column.type.compile(dialect=database.engine.dialect)).removeprefix('public.'), (table.name, column.name)
        model_fks = {(tuple(f.column_keys), tuple(e.target_fullname for e in f.elements), f.ondelete)
                     for f in table.foreign_key_constraints}
        db_fks = {(tuple(f['constrained_columns']), tuple((('auth.' if f['referred_schema']=='auth' else '') + f['referred_table'] + '.' + col) for col in f['referred_columns']), f['options'].get('ondelete'))
                  for f in inspector.get_foreign_keys(table.name)}
        assert model_fks == db_fks, table.name
        assert {tuple(c.columns.keys()) for c in table.constraints if c.__class__.__name__ == 'UniqueConstraint'} == {
            tuple(c['column_names']) for c in inspector.get_unique_constraints(table.name)}, table.name
        indexes = {i['name']: i for i in inspector.get_indexes(table.name)}
        for index in table.indexes:
            assert index.name in indexes
            assert indexes[index.name]['column_names'] == list(index.columns.keys())
            assert indexes[index.name]['unique'] == index.unique
        for column in table.c:
            assert (actual[column.name].get('default') is not None) == (column.server_default is not None and column.computed is None)
            if column.computed is not None:
                assert actual[column.name]['computed']['persisted'] is True


@pytest.mark.postgres
def test_versioning_ownership_immutability_and_rollback(database):
    user, trip, request = seed(database)
    payload = TripRequest.model_validate(fixture('trip_request'))
    with database.sessions.begin() as session:
        repo = ArtifactRepository(session, user)
        first = repo.add(request, 'trip_request', payload)
        second = repo.add(request, 'trip_request', payload)
        assert second.parent_artifact_id == first.artifact_id
        assert repo.latest(request, 'trip_request').artifact_id == second.artifact_id
        assert first.is_latest is False
        a, b = first.artifact_id, second.artifact_id
    with database.sessions.begin() as session:
        stranger = uuid4()
        for action in [lambda: TripRepository(session, stranger).get(trip),
                       lambda: RequestRepository(session, stranger).get(request),
                       lambda: ArtifactRepository(session, stranger).add(request, 'trip_request', payload)]:
            with pytest.raises(ApplicationError): action()
        assert ArtifactRepository(session, stranger).get(b) is None
    with pytest.raises(RuntimeError):
        with database.sessions.begin() as session:
            ArtifactRepository(session, user).add(request, 'trip_request', payload)
            raise RuntimeError('rollback')
    with database.sessions() as session:
        assert ArtifactRepository(session, user).latest(request, 'trip_request').artifact_id == b
    with pytest.raises(DBAPIError):
        with database.engine.begin() as c:
            c.execute(text("UPDATE workflow_artifacts SET payload='{}' WHERE artifact_id=:id"), {'id': b})
    with database.engine.begin() as c:
        c.execute(text('DELETE FROM workflow_requests WHERE request_id=:id'), {'id': request})
        assert c.execute(text('SELECT count(*) FROM workflow_artifacts WHERE artifact_id IN (:a,:b)'), {'a':a,'b':b}).scalar_one() == 0


@pytest.mark.postgres
def test_persisted_workflow_and_resume(database):
    user, trip, request = seed(database)
    with database.sessions.begin() as session:
        service = WorkflowPersistence(session, user)
        data = fixture('trip_request')
        data['budget']['amount'] = None
        run = asyncio.run(LangGraphOrchestrator(mock_components(), defaults=fixture('planner_defaults'), persistence=service).run(
            TripRequest.model_validate(data), current_date=date(2026,11,4), trip_id=trip, request_id=request))
        assert run.state.status == 'clarifying'
    with database.sessions.begin() as session:
        service = WorkflowPersistence(session, user)
        previous = service.load_graph(request)
        assert previous.pending_questions and not previous.answers_history
        run = asyncio.run(LangGraphOrchestrator(mock_components(), defaults=fixture('planner_defaults'), persistence=service).run(
            TripRequest.model_validate(fixture('trip_request')), current_date=date(2026,11,4), previous=previous, answer_raw='3000000'))
        assert run.state.status == 'completed', run.errors
        assert run.state.trip_id == trip and trip != request
        assert run.answers_history[0].resolved_fields == ['budget.amount']
    with database.sessions() as session:
        saved = WorkflowPersistence(session, user).load(request)
        assert saved.state.status == 'completed' and len(saved.attempts) == 1
        assert len(saved.answers_history) == 1
        assert 'errors' not in saved.state.model_dump()
        assert session.scalar(select(func.count()).select_from(WorkflowArtifactRecord).where(
            WorkflowArtifactRecord.request_id == request, WorkflowArtifactRecord.is_latest)) == 8
    with database.engine.begin() as c:
        c.execute(text('DELETE FROM workflow_requests WHERE request_id=:id'), {'id': request})
        assert c.execute(text('SELECT count(*) FROM itineraries WHERE request_id=:id'), {'id': request}).scalar_one() == 0


@pytest.mark.postgres
def test_concurrent_artifact_writers_keep_one_latest(database):
    from concurrent.futures import ThreadPoolExecutor
    user, trip, request = seed(database)
    payload = TripRequest.model_validate(fixture('trip_request'))
    def save(_):
        with database.sessions.begin() as session:
            return ArtifactRepository(session, user).add(request, 'trip_request', payload).artifact_id
    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(save, range(2)))
    with database.sessions() as session:
        rows = list(session.scalars(select(WorkflowArtifactRecord).where(WorkflowArtifactRecord.request_id == request)))
        assert {r.artifact_id for r in rows} == set(ids)
        assert sum(r.is_latest for r in rows) == 1
        latest = next(r for r in rows if r.is_latest)
        assert latest.parent_artifact_id == next(r.artifact_id for r in rows if not r.is_latest)


@pytest.mark.postgres
def test_rls_owner_and_readonly_outputs(database):
    user, trip, request = seed(database)
    with database.engine.begin() as c:
        c.execute(text('SET LOCAL ROLE authenticated'))
        c.execute(text("SELECT set_config('request.jwt.claim.sub', :id, true)"), {'id':str(uuid4())})
        assert c.execute(text('SELECT count(*) FROM trips WHERE trip_id=:id'), {'id':trip}).scalar_one()==0
        assert c.execute(text('SELECT count(*) FROM workflow_requests WHERE request_id=:id'), {'id':request}).scalar_one()==0
        c.execute(text("SELECT set_config('request.jwt.claim.sub', :id, true)"), {'id':str(user)})
        assert c.execute(text('SELECT count(*) FROM trips WHERE trip_id=:id'), {'id':trip}).scalar_one()==1
    with pytest.raises(DBAPIError):
        with database.engine.begin() as c:
            c.execute(text('SET LOCAL ROLE authenticated'))
            c.execute(text("SELECT set_config('request.jwt.claim.sub', :id, true)"), {'id':str(user)})
            c.execute(text("INSERT INTO workflow_artifacts(request_id, artifact_type, schema_version,payload) VALUES (:id,'trip_request','1.0','{}')"), {'id':request})


@pytest.mark.postgres
def test_persistence_api_with_verified_identity_override(database):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.api.auth import get_current_user_id
    from app.db.session import get_session
    user, _, _ = seed(database)
    application = create_app(Settings(_env_file=None, database_url=None))
    application.dependency_overrides[get_current_user_id] = lambda: user
    application.dependency_overrides[get_session] = database.session
    with TestClient(application) as client:
        trip = client.post('/api/v1/trips', json={'title': 'API trip'})
        assert trip.status_code == 201
        trip_id = trip.json()['trip_id']
        request = client.post(f'/api/v1/trips/{trip_id}/requests')
        assert request.status_code == 201
        request_id = request.json()['request_id']
        assert trip_id != request_id
        response = client.post(f'/api/v1/requests/{request_id}/mock-run', json={'trip_request': fixture('trip_request')})
        assert response.status_code == 200, response.text
        assert response.json()['state']['status'] == 'completed'
        assert client.get(f'/api/v1/requests/{request_id}').json()['status'] == 'completed'
        assert client.get(f'/api/v1/requests/{request_id}/artifacts/itinerary').status_code == 200
        assert client.post(f'/api/v1/requests/{request_id}/mock-run', json={'trip_request': fixture('trip_request')}).status_code == 409
        application.dependency_overrides[get_current_user_id] = uuid4
        assert client.get(f'/api/v1/requests/{request_id}').status_code == 404
        assert client.get(f'/api/v1/requests/{request_id}/artifacts/itinerary').status_code == 404


@pytest.mark.postgres
def test_replan_persists_distinct_normalized_versions(database):
    user, trip, request = seed(database)
    components = mock_components()
    calls = 0
    async def validate(itinerary, planning_input, **kwargs):
        from shared.contracts import ValidationResult
        nonlocal calls
        calls += 1
        data = fixture('validation_result')
        data['trip_id'] = trip
        if calls == 1:
            data.update(is_valid=False, suggested_action='replan', violations=[
                dict(type='over_budget', rule='budget', severity='hard', message='replan')])
        return ValidationResult.model_validate(data)
    components.validator.validate = validate
    with database.sessions.begin() as session:
        run = asyncio.run(LangGraphOrchestrator(components, defaults=fixture('planner_defaults'),
            persistence=WorkflowPersistence(session, user)).run(TripRequest.model_validate(fixture('trip_request')),
                current_date=date(2026,11,4), trip_id=trip, request_id=request))
        assert run.state.status == 'completed', run.errors
        assert len(run.attempts) == 2
        saved = WorkflowPersistence(session, user).load(request)
        assert [a.result for a in saved.attempts] == ['hard_violation', 'accepted']
        assert saved.attempts[0].itinerary_id != saved.attempts[1].itinerary_id


@pytest.mark.postgres
def test_engine_error_is_persisted_with_nullable_result_ids(database):
    user, trip, request = seed(database)
    components = mock_components()
    async def broken(planning_input):
        raise RuntimeError('private implementation detail')
    components.planning_engine.plan = broken
    with database.sessions.begin() as session:
        run = asyncio.run(LangGraphOrchestrator(components, defaults=fixture('planner_defaults'),
            persistence=WorkflowPersistence(session, user)).run(TripRequest.model_validate(fixture('trip_request')),
                current_date=date(2026,11,4), trip_id=trip, request_id=request))
        assert run.state.status == 'failed'
    with database.sessions() as session:
        saved = WorkflowPersistence(session, user).load(request)
        assert saved.errors[0].code == 'solver_error'
        assert saved.attempts[0].result == 'error'
        assert saved.attempts[0].itinerary_id is None and saved.attempts[0].validation_result_id is None
        assert 'private implementation detail' not in saved.model_dump_json()


@pytest.mark.postgres
def test_graph_snapshot_restart_resume(database):
    from ai.orchestration.graph_workflow import LangGraphOrchestrator
    user, trip_id, request_id = seed(database)
    missing = TripRequest.model_validate(fixture('trip_request'))
    missing.destination.city = None
    with database.sessions.begin() as session:
        adapter = WorkflowPersistence(session, user)
        adapter.request(request_id, lock=True)
        run = asyncio.run(LangGraphOrchestrator(mock_components(),
            defaults=fixture('planner_defaults'), persistence=adapter).run(missing,
                current_date=date(2026, 11, 4), trip_id=trip_id, request_id=request_id))
        assert run.state.status == 'clarifying'
        transitions = run.transitions
    # New session and graph instance: no process-local state is reused.
    with database.sessions.begin() as session:
        adapter = WorkflowPersistence(session, user)
        previous = adapter.load_graph(request_id)
        run = asyncio.run(LangGraphOrchestrator(mock_components(),
            defaults=fixture('planner_defaults'), persistence=adapter).run(
                TripRequest.model_validate(fixture('trip_request')),
                current_date=date(2026, 11, 4), previous=previous, answer_raw='Da Lat'))
        assert run.state.status == 'completed'
        assert run.transitions > transitions
    with database.sessions.begin() as session:
        recovered = WorkflowPersistence(session, user).load_graph(request_id)
        assert recovered.final_result == run.final_result
        assert recovered.history == run.history
        assert recovered.state.request_id == request_id


@pytest.mark.postgres
def test_http_graph_real_postgres(database):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.api.auth import get_current_user_id
    from app.db.session import get_session
    user, trip_id, request_id = seed(database)
    application = create_app(Settings(_env_file=None, database_url=None))
    application.dependency_overrides[get_current_user_id] = lambda: user
    application.dependency_overrides[get_session] = database.session
    with TestClient(application) as client:
        url = f'/api/v1/requests/{request_id}'
        data = fixture('trip_request')
        data['destination']['city'] = None
        response = client.post(url + '/mock-run', json={'trip_request': data})
        assert response.status_code == 200, response.text
        assert response.json()['state']['status'] == 'clarifying'
        assert client.get(url).json()['status'] == 'clarifying'
        assert client.get(url + '/result').status_code == 409
        response = client.post(url + '/mock-run', json={
            'trip_request': fixture('trip_request'), 'answer_raw': 'Da Lat',
            'expected_transitions': response.json()['transitions']})
        assert response.status_code == 200, response.text
        assert response.json()['state']['status'] == 'completed'
        assert client.get(url + '/result').json() == response.json()['final_result']
        assert client.get(url + '/run').json()['history'] == response.json()['history']
        application.dependency_overrides[get_current_user_id] = uuid4
        assert client.get(url + '/run').status_code == 404
