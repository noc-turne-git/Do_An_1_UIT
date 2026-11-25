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
        from app.core.config import get_settings
        assert row == (0, get_settings().max_destination_rounds)
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
def test_chat_turn_idempotency_persists_one_workflow_episode_and_response(database, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.api.auth import get_current_user_id
    from app.db.session import get_session
    from app.db.models import (ConversationRecord, ConversationTurnRecord,
        DestinationEpisodeRecord, MessageRecord)

    user = uuid4()
    with database.engine.begin() as connection:
        connection.execute(text('INSERT INTO auth.users(id) VALUES (:id)'), {'id': user})
    value = TripRequest.model_validate(fixture('trip_request'))
    value.destination.city = None

    async def deterministic_turn(settings, *, graph, previous, current_date, **kwargs):
        return await graph.run_turn(value, current_date=current_date, previous=previous)

    monkeypatch.setattr('app.api.chat.run_turn', deterministic_turn)
    application = create_app(Settings(_env_file=None, database_url=None))
    application.dependency_overrides[get_current_user_id] = lambda: user
    application.dependency_overrides[get_session] = database.session
    input_id = uuid4()
    body = {'input_id': str(input_id), 'content': 'Tôi muốn lên kế hoạch chuyến đi'}
    with TestClient(application) as client:
        first = client.post('/api/v1/chat/messages', json=body)
        second = client.post('/api/v1/chat/messages', json=body)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    payload = first.json()
    assert payload['workflow_status'] == 'clarifying'
    assert payload['workflow_id'] and payload['episode_id']
    assert payload['remaining_destination_rounds'] == 1
    assert len(payload['questions']) == 1
    with database.sessions.begin() as session:
        conversation = session.scalar(select(ConversationRecord).where(ConversationRecord.user_id == user))
        assert conversation is not None
        assert session.scalar(select(func.count()).select_from(ConversationTurnRecord).where(
            ConversationTurnRecord.conversation_id == conversation.conversation_id)) == 1
        assert session.scalar(select(func.count()).select_from(WorkflowRequestRecord).where(
            WorkflowRequestRecord.request_id == conversation.request_id)) == 1
        assert session.scalar(select(func.count()).select_from(DestinationEpisodeRecord).where(
            DestinationEpisodeRecord.request_id == conversation.request_id)) == 1
        assert session.scalar(select(func.count()).select_from(MessageRecord).where(
            MessageRecord.conversation_id == conversation.conversation_id)) == 2
        assert conversation.request_id == UUID(payload['workflow_id'])
        assert conversation.active_episode_id == UUID(payload['episode_id'])


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
def test_concurrent_answers_accept_only_one_question_identity(database):
    from concurrent.futures import ThreadPoolExecutor
    from canonical_cases import start, question, answer
    from app.repositories.clarifications import ClarificationRepository
    user, _, request, ep = start(database, seed)
    q = question(ep, 'destination_info', 1)
    with database.sessions.begin() as session:
        ClarificationRepository(session, user).issue(request, q)

    answers = [answer(q), answer(q)]
    def submit(value):
        try:
            with database.sessions.begin() as session:
                ClarificationRepository(session, user).answer(request, value)
            return 'accepted'
        except (ApplicationError, DBAPIError):
            return 'stale'

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, answers)) == ['accepted', 'stale']
    with database.sessions.begin() as session:
        repo = ClarificationRepository(session, user)
        assert repo.questions(request, open_only=True) == []
        assert len(repo.answers(request)) == 1


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
                             ROOT / 'supabase' / 'migrations' / '20261107_canonical_episodes.sql',
                             ROOT / 'supabase' / 'migrations' / '20261108_destination_responses.sql',
                             ROOT / 'supabase' / 'migrations' / '20261108_conversation_lifecycle.sql',
                             ROOT / 'supabase' / 'migrations' / '20261117_five_intent_destination_policy.sql']:
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


@pytest.mark.postgres
@pytest.mark.parametrize('sequence', [
    ('needs_more_info', 'needs_user_choice'), ('needs_user_choice', 'needs_more_info'),
    ('needs_more_info', 'needs_more_info'), ('needs_user_choice', 'needs_user_choice')])
def test_destination_graph_final_resolve_durable_across_sessions(database, sequence):
    from unittest.mock import AsyncMock
    from test_destination_resolution import request as input_request, result, answer
    from app.repositories.clarifications import ClarificationRepository
    from ai.agents.runtime.context import execution_identity
    user, trip, request_id = seed(database)
    data = TripRequest.model_validate(input_request())
    components = mock_components()
    results = iter([*(result(status) for status in sequence), result()])
    seen_operations = []

    async def resolve(current):
        operation = (execution_identity.get() or {}).get('metadata', {}).get('final_resolve_id')
        if operation:
            # A distinct DB connection sees the claim BEFORE the business call.
            with database.sessions() as observer:
                repo = ClarificationRepository(observer, user)
                ep = repo.contract(repo.episode(request_id))
                assert ep.final_resolve_status == 'claimed' and str(ep.final_resolve_id) == operation
                assert not repo.questions(request_id, open_only=True)
                assert len(repo.answers(request_id)) == 2
            seen_operations.append(operation)
        return next(results)
    components.destination_agent.select = AsyncMock(side_effect=resolve)

    def turn(resume=False):
        with database.sessions() as session:
            persistence = WorkflowPersistence(session, user)
            previous = persistence.load_graph(request_id) if resume else None
            graph = LangGraphOrchestrator(components, defaults=fixture('planner_defaults'), persistence=persistence)
            run = asyncio.run(graph.run(data, current_date=date(2026, 11, 4),
                trip_id=trip, request_id=request_id, previous=previous,
                answer=answer(previous) if previous and previous.pending_questions else None))
            session.commit()
            return run
    first, second = turn(), turn(True)
    assert first.state.destination_round == 1
    assert second.state.destination_round == 2 and second.pending_questions[0].status == 'open'
    assert not seen_operations
    final = turn(True)
    assert final.state.status == 'completed', final.errors
    assert final.outputs['destination_agent'].selected_candidate_id == 'dalat'
    assert final.outputs['destination_agent'].selection_method == 'SYSTEM_DEFAULT'
    assert len(seen_operations) == 1 and components.destination_agent.select.await_count == 3
    with database.sessions() as session:
        restored = WorkflowPersistence(session, user).load_graph(request_id)
        assert restored.state.destination_episode.final_resolve_status == 'completed'
        assert restored.outputs['destination_agent'] == final.outputs['destination_agent']
