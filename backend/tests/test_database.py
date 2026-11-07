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
from shared.contracts import AnswerHistory, PendingQuestion, TripRequest, WorkflowState
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
    # The canonical Alembic branch executes the immutable Supabase baseline and
    # then its sequential structural migrations; no create_all.
    from alembic import command
    from alembic.config import Config
    config = Config(str(ROOT / 'alembic.ini'))
    config.attributes['database_url'] = parsed.render_as_string(hide_password=False)
    # Historical baseline revision has a mismatched hash/header for committed
    # schema.sql. Preserve that migration: provision the exact Supabase baseline
    # into this verified EMPTY database, then stamp that known baseline and test
    # the real sequential Alembic upgrades. No production database is stamped.
    with db.engine.connect() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute((ROOT / 'supabase' / 'schema.sql').read_text(encoding='utf-8'))
        connection.commit()
    command.stamp(config, '20261105_canonical_baseline')
    legacy_user, legacy_trip, legacy_request = uuid4(), uuid4(), uuid4()
    with db.engine.begin() as connection:
        connection.execute(text('INSERT INTO auth.users(id) VALUES (:id)'), {'id': legacy_user})
        connection.execute(text('INSERT INTO trips(trip_id, user_id, title) VALUES (:trip, :user, :title)'),
                           {'trip': legacy_trip, 'user': legacy_user, 'title': 'pre-upgrade'})
        connection.execute(text('''INSERT INTO workflow_requests
            (request_id, trip_id, schema_version, status, current_step)
            VALUES (:request, :trip, '1.0', 'clarifying', 'request_parser')'''),
                           {'request': legacy_request, 'trip': legacy_trip})
        connection.execute(text('''INSERT INTO clarification_rounds
            (request_id, round, asked_fields, question)
            VALUES (:request, 1, '[]'::jsonb, 'pre-upgrade')'''), {'request': legacy_request})
    command.upgrade(config, 'canonical@head')
    db.pre_upgrade_request_id = legacy_request
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
def test_canonical_migration_backfills_round_defaults_and_allows_kind_pair(database):
    user, _, request = seed(database)
    with database.engine.begin() as connection:
        legacy = connection.execute(text('''SELECT destination_round, max_destination_rounds
            FROM workflow_requests WHERE request_id=:id'''),
            {'id': database.pre_upgrade_request_id}).one()
        assert legacy == (0, 2)
        assert connection.execute(text('''SELECT kind FROM clarification_rounds
            WHERE request_id=:id AND round=1'''),
            {'id': database.pre_upgrade_request_id}).scalar_one() == 'trip_request'
        row = connection.execute(text('''SELECT destination_round, max_destination_rounds
            FROM workflow_requests WHERE request_id=:id'''), {'id': request}).one()
        assert row == (0, 2)
        for kind in ('trip_request', 'destination_choice'):
            connection.execute(text('''INSERT INTO clarification_rounds
                (request_id, round, kind, asked_fields, question)
                VALUES (:request_id, 1, :kind, '[]'::jsonb, :question)'''),
                {'request_id': request, 'kind': kind, 'question': kind})
        count = connection.execute(text('''SELECT count(*) FROM clarification_rounds
            WHERE request_id=:id AND round=1'''), {'id': request}).scalar_one()
        assert count == 2


@pytest.mark.postgres
def test_persistence_round_kind_and_round_are_preserved(database):
    from ai.orchestration.workflow_state import WorkflowRun
    user, trip, request = seed(database)
    trip_answer = AnswerHistory(round=1, kind='trip_request', asked_fields=['trip.start_date'],
        question='Khi nào đi?', answer_raw='2026-12-01', resolved_fields=['trip.start_date'],
        declared_unknown_fields=[])
    trip_run = WorkflowRun(state=WorkflowState(request_id=request, trip_id=trip, status='clarifying',
        current_step='request_parser', completed_steps=[], artifacts={}, clarification_round=1,
        destination_round=0, pending_fields=['trip.start_date'], retry_count=0),
        pending_questions=[PendingQuestion(question='Khi nào đi?', fields=['trip.start_date'])],
        answers_history=[trip_answer])
    with database.sessions.begin() as session:
        WorkflowPersistence(session, user).sync(trip_run)
    destination_answer = AnswerHistory(round=1, kind='destination_choice', asked_fields=['destination.city'],
        question='Chọn khu vực', answer_raw='option-da-lat', resolved_fields=['destination.city'],
        declared_unknown_fields=[])
    destination_question_run = WorkflowRun(state=WorkflowState(request_id=request, trip_id=trip, status='clarifying',
        current_step='destination_agent', completed_steps=[], artifacts={}, clarification_round=1,
        destination_round=1, max_destination_rounds=2, pending_fields=['destination.city'], retry_count=0),
        pending_questions=[PendingQuestion(question='Chọn khu vực', fields=['destination.city'],
            kind='destination_choice')])
    with database.sessions.begin() as session:
        WorkflowPersistence(session, user).sync(destination_question_run)
    with database.sessions.begin() as session:
        pending_run = WorkflowPersistence(session, user).load(request)
    assert {question.kind for question in pending_run.pending_questions} == {'destination_choice'}
    destination_answer_run = WorkflowRun(state=WorkflowState(request_id=request, trip_id=trip, status='planning',
        current_step='destination_agent', completed_steps=[], artifacts={}, clarification_round=1,
        destination_round=1, max_destination_rounds=2, pending_fields=[], retry_count=0),
        answers_history=[trip_answer, destination_answer])
    with database.sessions.begin() as session:
        WorkflowPersistence(session, user).sync(destination_answer_run)
    with database.sessions.begin() as session:
        restored = WorkflowPersistence(session, user).load(request)
    assert restored.state.destination_round == 1
    assert restored.state.max_destination_rounds == 2
    assert {(answer.kind, answer.round) for answer in restored.answers_history} == {
        ('trip_request', 1), ('destination_choice', 1)}
    assert {(answer.kind, answer.answer_raw) for answer in restored.answers_history} == {
        ('trip_request', trip_answer.answer_raw),
        ('destination_choice', destination_answer.answer_raw)}


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
        assert len([m for m in client.get(f'/api/v1/chat/conversations/{identifier}/messages').json() if m['role'] == 'user']) == 3
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
        assert len([m for m in client.get(f'/api/v1/chat/conversations/{identifier}/messages').json() if m['role'] == 'user']) == 3
        app.dependency_overrides[get_current_user_id] = uuid4
        assert client.get(f'/api/v1/chat/conversations/{identifier}/messages').status_code == 404


@pytest.mark.postgres
def test_schema_metadata_matches_columns_and_fks(database):
    from app.db.base import Base
    inspector = inspect(database.engine)
    assert set(inspector.get_table_names()) - {'alembic_version'} == set(Base.metadata.tables)
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


@pytest.mark.postgres
@pytest.mark.parametrize('kinds', [('destination_info', 'destination_choice'), ('destination_choice', 'destination_info')])
def test_canonical_roundtrip_restart_and_shared_budget(database, kinds):
    from canonical_cases import start, question, answer
    from app.repositories.clarifications import ClarificationRepository
    from app.db.models import ClarificationQuestionRecord, ClarificationAnswerRecord
    user, trip, request, ep = start(database, seed)
    first, second = question(ep, kinds[0], 1), question(ep, kinds[1], 2)
    first_answer, second_answer = answer(first), answer(second)
    with database.sessions.begin() as session:
        repo = ClarificationRepository(session, user)
        repo.issue(request, first)
        assert repo.issue(request, first) == first
        assert repo.contract(repo.episode(request)).destination_round == 1
        repo.answer(request, first_answer)
        assert repo.answer(request, first_answer) == first_answer
        repo.issue(request, second)
    # Fresh sessions simulate process restart with question #2 still open.
    with database.sessions.begin() as session:
        persistence = WorkflowPersistence(session, user)
        relational, graph = persistence.load(request), persistence.load_graph(request)
        assert relational.state.destination_episode == graph.state.destination_episode
        assert relational.pending_questions == graph.pending_questions == [second]
        assert relational.answers_history == graph.answers_history == [first_answer]
        assert relational.state.destination_round == 2
        assert relational.state.clarification_round == 0
        persistence.sync(relational)
        persistence.save_graph(graph)
        repo = ClarificationRepository(session, user)
        assert repo.issue(request, second) == second
        # The open second question is answerable at the limit.
        repo.answer(request, second_answer)
        assert repo.answer(request, second_answer) == second_answer
        with pytest.raises(ApplicationError):
            repo.issue(request, question(ep, kinds[0], 3))
        assert repo.contract(repo.episode(request)).destination_round == 2
    with database.sessions.begin() as session:
        persistence = WorkflowPersistence(session, user)
        assert persistence.load(request).pending_questions == []
        assert persistence.load_graph(request).answers_history == [first_answer, second_answer]
        assert session.scalar(select(func.count()).select_from(ClarificationQuestionRecord).where(
            ClarificationQuestionRecord.request_id == request)) == 2
        assert session.scalar(select(func.count()).select_from(ClarificationAnswerRecord).where(
            ClarificationAnswerRecord.request_id == request)) == 2


@pytest.mark.postgres
def test_canonical_stale_cross_episode_owner_and_rollback(database):
    from canonical_cases import start, question, answer
    from app.repositories.clarifications import ClarificationRepository
    from shared.contracts import SelectionPolicy
    user, _, request, ep = start(database, seed)
    q = question(ep, 'destination_choice', 1)
    with database.sessions.begin() as session:
        repo = ClarificationRepository(session, user)
        repo.issue(request, q)
        for invalid in [answer(q, selected_option_id='not-issued'), answer(q, episode_id=uuid4()),
                        answer(q, question_id=uuid4()), answer(q, round=2)]:
            with pytest.raises((ApplicationError, ValueError)):
                repo.answer(request, invalid)
        with pytest.raises(ApplicationError):
            ClarificationRepository(session, uuid4()).issue(request, q)
        with pytest.raises(ApplicationError):
            repo.issue(request, question(ep, 'destination_choice', 1, question_id=q.question_id, question='changed'))
        a = answer(q)
        repo.answer(request, a)
        with pytest.raises(ApplicationError):
            repo.answer(request, answer(q))  # another answer identity
        repo.close_episode(request, ep.episode_id, status='completed')
        newer = repo.start_episode(request, SelectionPolicy())
        assert newer.destination_round == 0
        with pytest.raises(ApplicationError):
            repo.answer(request, a)
        q2 = question(newer, 'destination_info', 1)
        with pytest.raises(RuntimeError):
            with session.begin_nested():
                repo.issue(request, q2)
                raise RuntimeError('simulate crash before commit')
        assert repo.contract(repo.episode(request)).destination_round == 0
        assert repo.questions(request, open_only=True) == []
        repo.issue(request, q2)
        bad_graph = WorkflowPersistence(session, user).load_graph(request)
        bad_graph.pending_questions[0].question = 'tampered'
        with pytest.raises(ApplicationError):
            WorkflowPersistence(session, user).save_graph(bad_graph)


@pytest.mark.postgres
def test_canonical_database_slot_constraint_and_concurrent_retry(database):
    from concurrent.futures import ThreadPoolExecutor
    from canonical_cases import start, question, answer
    from app.repositories.clarifications import ClarificationRepository
    from app.db.models import ClarificationQuestionRecord
    user, _, request, ep = start(database, seed)
    q = question(ep, 'destination_info', 1)
    def issue():
        with database.sessions.begin() as session:
            return ClarificationRepository(session, user).issue(request, q).question_id
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: issue(), range(2))) == [q.question_id, q.question_id]
    with database.sessions.begin() as session:
        repo = ClarificationRepository(session, user)
        assert repo.contract(repo.episode(request)).destination_round == 1
        repo.answer(request, answer(q))
        other_kind_same_round = question(ep, 'destination_choice', 1)
        # Direct SQL/ORM cannot bypass shared budget by changing the question kind.
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.add(ClarificationQuestionRecord(question_id=other_kind_same_round.question_id,
                    request_id=request, episode_id=ep.episode_id, counter_group='destination', round=1,
                    kind='destination_choice', status='open', payload=other_kind_same_round.model_dump(mode='json')))
                session.flush()
        assert repo.contract(repo.episode(request)).destination_round == 1
    unique = inspect(database.engine).get_unique_constraints('clarification_questions')
    assert any(c['column_names'] == ['episode_id', 'counter_group', 'round'] for c in unique)


@pytest.mark.postgres
def test_canonical_final_resolve_claim_survives_restart(database):
    from canonical_cases import start, question, answer
    from app.repositories.clarifications import ClarificationRepository
    from shared.contracts import DestinationResult
    user, _, request, ep = start(database, seed)
    operation = uuid4()
    with database.sessions.begin() as session:
        repo = ClarificationRepository(session, user)
        for round in (1, 2):
            q = question(ep, 'destination_info', round)
            repo.issue(request, q)
            if round == 2:
                with pytest.raises(ApplicationError):
                    repo.claim_final_resolve(request, ep.episode_id, operation)
            repo.answer(request, answer(q))
        _, acquired = repo.claim_final_resolve(request, ep.episode_id, operation)
        assert acquired
    with database.sessions.begin() as session:
        repo = ClarificationRepository(session, user)
        claimed, acquired = repo.claim_final_resolve(request, ep.episode_id, operation)
        assert not acquired and claimed.final_resolve_status == 'claimed'
        assert WorkflowPersistence(session, user).load_graph(request).state.destination_episode == claimed
        with pytest.raises(ApplicationError):
            repo.claim_final_resolve(request, ep.episode_id, uuid4())
        result = DestinationResult.model_validate(fixture('destination_result'))
        completed = repo.complete_final_resolve(request, ep.episode_id, operation, result)
    with database.sessions.begin() as session:
        repo = ClarificationRepository(session, user)
        assert repo.complete_final_resolve(request, ep.episode_id, operation, result) == completed
        assert repo.claim_final_resolve(request, ep.episode_id, operation) == (completed, False)
        assert WorkflowPersistence(session, user).load(request).state.destination_episode == completed
        assert WorkflowPersistence(session, user).load_graph(request).state.destination_episode == completed


@pytest.mark.postgres
def test_canonical_failed_workflow_new_identity_and_seed(database):
    from canonical_cases import start, question, answer
    from app.repositories.clarifications import ClarificationRepository
    from shared.contracts import Destination
    user, trip, request, ep = start(database, seed)
    source = TripRequest.model_validate(fixture('trip_request'))
    with database.sessions.begin() as session:
        ArtifactRepository(session, user).add(request, 'trip_request', source)
        repo = ClarificationRepository(session, user)
        q = question(ep, 'destination_choice', 1)
        repo.issue(request, q)
        repo.close_episode(request, ep.episode_id, status='failed')
    with database.sessions.begin() as session:
        before = session.execute(text('SELECT to_jsonb(w) FROM workflow_requests w WHERE request_id=:id'), {'id': request}).scalar_one()
        destination = Destination.model_validate(source.destination.model_dump() | dict(city='Hue',
            selection_intent='EXPLICIT', selection_authority='user',
            selection_provenance=dict(source='user', evidence='Go to Hue')))
        new_id, new_ep, new_input = ClarificationRepository(session, user).new_workflow_after_failed(
            request, destination, raw_prompt='Go to Hue')
        assert new_id != request and new_ep.episode_id != ep.episode_id
        assert new_ep.destination_round == 0 and new_ep.final_resolve_status == 'not_started'
        new = WorkflowPersistence(session, user).load(new_id)
        assert new.state.trip_id == trip
        assert new.state.clarification_round == new.state.retry_count == 0
        assert not new.pending_questions and not new.answers_history
        assert new.state.artifacts.destination_result_id is None
        assert new_input.trip == source.trip and new_input.budget == source.budget
        assert new_input.destination.city == 'Hue' and source.destination.city != 'Hue'
        assert ArtifactRepository(session, user).latest(new_id, 'trip_request').payload == new_input.model_dump(mode='json')
        after = session.execute(text('SELECT to_jsonb(w) FROM workflow_requests w WHERE request_id=:id'), {'id': request}).scalar_one()
        assert before == after
        assert WorkflowPersistence(session, user).load_graph(request).state.status == 'failed'
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text("UPDATE workflow_requests SET status='planning' WHERE request_id=:id"), {'id': request})
        with pytest.raises(ApplicationError):
            ClarificationRepository(session, user).answer(request, answer(q))


@pytest.mark.postgres
def test_canonical_legacy_adoption_preserves_budget(database):
    from shared.contracts import SelectionPolicy
    from app.repositories.clarifications import ClarificationRepository
    user, _, request = seed(database)
    with database.sessions.begin() as session:
        row = session.get(WorkflowRequestRecord, request)
        row.destination_round = 1
        session.flush()
        legacy = WorkflowPersistence(session, user).load(request)
        assert legacy.state.destination_episode is None
        episode = ClarificationRepository(session, user).start_episode(request, SelectionPolicy())
        assert episode.destination_round == 1
        assert episode.selection_intent == 'UNSPECIFIED' and episode.selection_authority == 'none'
    with database.engine.connect() as connection:
        assert connection.execute(text('SELECT active_episode_id FROM workflow_requests WHERE request_id=:id'),
            {'id': database.pre_upgrade_request_id}).scalar_one() is None


@pytest.mark.postgres
def test_canonical_independent_trip_budget_and_answer_rollback(database):
    from canonical_cases import start, question, answer
    from app.repositories.clarifications import ClarificationRepository
    user, _, request, ep = start(database, seed)
    with database.sessions.begin() as session:
        repo = ClarificationRepository(session, user)
        q = question(ep, 'trip_request', 1)
        repo.issue(request, q)
        with pytest.raises(RuntimeError):
            with session.begin_nested():
                repo.answer(request, answer(q))
                raise RuntimeError('crash before answer commit')
        assert repo.questions(request, open_only=True) == [q]
        assert repo.answers(request) == []
        repo.answer(request, answer(q))
        for round, kind in [(1, 'destination_info'), (2, 'destination_choice')]:
            destination = question(ep, kind, round)
            repo.issue(request, destination)
            repo.answer(request, answer(destination))
        run = WorkflowPersistence(session, user).load_graph(request)
        assert run.state.clarification_round == 1 and run.state.destination_round == 2


@pytest.mark.postgres
def test_canonical_rls_and_snapshot_immutability(database):
    from canonical_cases import start, question, answer
    from app.repositories.clarifications import ClarificationRepository
    user, _, request, ep = start(database, seed)
    with database.sessions.begin() as session:
        repo = ClarificationRepository(session, user)
        q = question(ep, 'destination_choice', 1)
        repo.issue(request, q)
        repo.answer(request, answer(q))
    for table in ['destination_episodes', 'clarification_questions', 'clarification_answers']:
        with database.engine.begin() as connection:
            connection.execute(text('SET LOCAL ROLE authenticated'))
            connection.execute(text("SELECT set_config('request.jwt.claim.sub', :id, true)"), {'id': str(user)})
            assert connection.execute(text(f'SELECT count(*) FROM {table} WHERE request_id=:id'), {'id': request}).scalar_one() == 1
            connection.execute(text("SELECT set_config('request.jwt.claim.sub', :id, true)"), {'id': str(uuid4())})
            assert connection.execute(text(f'SELECT count(*) FROM {table} WHERE request_id=:id'), {'id': request}).scalar_one() == 0
    for statement in ["UPDATE clarification_questions SET payload=jsonb_set(payload,'{question}','\"changed\"') WHERE request_id=:id",
                      "UPDATE clarification_answers SET payload=jsonb_set(payload,'{answer_raw}','\"changed\"') WHERE request_id=:id"]:
        with pytest.raises(DBAPIError):
            with database.engine.begin() as connection:
                connection.execute(text(statement), {'id': request})


@pytest.mark.postgres
def test_canonical_supabase_alembic_schema_parity(database):
    import psycopg
    from psycopg import sql
    from sqlalchemy import create_engine
    url = database.engine.url
    peer_name = 'canonical_parity_test_' + uuid4().hex[:12]
    with psycopg.connect(host=url.host, port=url.port, user=url.username, password=url.password,
                         dbname='postgres', autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(peer_name)))
    peer = create_engine(url.set(database=peer_name))
    try:
        with peer.connect() as connection:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute("""CREATE SCHEMA auth;
                    CREATE TABLE auth.users(id uuid PRIMARY KEY, raw_user_meta_data jsonb NOT NULL DEFAULT '{}');
                    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
                    SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
                    GRANT USAGE ON SCHEMA auth, public TO anon, authenticated, service_role;""")
                connection.commit()
                for path in [ROOT / 'supabase' / 'schema.sql',
                             ROOT / 'supabase' / 'migrations' / '20261107_clarification_round_kinds.sql',
                             ROOT / 'supabase' / 'migrations' / '20261107_canonical_episodes.sql']:
                    cursor.execute(path.read_text(encoding='utf-8'))
                connection.commit()
        def fingerprint(engine):
            queries = [
                "SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name<>'alembic_version' ORDER BY 1,2",
                "SELECT c.relname,pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname<>'alembic_version' ORDER BY 1,2",
                "SELECT tablename,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename<>'alembic_version' ORDER BY 1,2",
                "SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY 1,2",
                "SELECT tablename,policyname,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname='public' ORDER BY 1,2",
                "SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' ORDER BY 1,2",
            ]
            with engine.connect() as connection:
                return [connection.execute(text(query)).all() for query in queries]
        assert fingerprint(database.engine) == fingerprint(peer)
    finally:
        peer.dispose()  # Leave both disposable databases for inspection; no destructive cleanup.
