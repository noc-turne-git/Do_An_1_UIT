import json
import logging
from app.core.config import Settings
from app.core.logging import configure_logging, log_message
from ai.logging import diagnostic_scope, log_execution
from ai.orchestration.request_parser import empty_request
from sqlalchemy import create_engine, event, text
from app.db.session import _after_statement, _before_statement, _statement_error

def test_backend_console_and_per_run_jsonl(tmp_path, caplog):
    path = tmp_path / 'ai' / 'execution.jsonl'
    settings = Settings(_env_file=None, ai_log_file=path)
    configure_logging(settings)
    configure_logging(settings)
    assert not logging.getLogger('travel.ai').handlers
    with caplog.at_level('INFO'):
        log_message(message_id='m1', role='user', content='private raw message')
        with diagnostic_scope(conversation_id='c1', run_id='r1'):
            log_execution(run_id='r1', trip_id='t1', step='planner',
                result={'status': 'completed', 'api_key': 'sk-private', 'content': 'private raw message'}, error=None)
    assert not (tmp_path / 'backend' / 'logs').exists()
    assert not path.exists()
    trace = tmp_path / 'ai' / 'conversations' / 'c1' / 'runs' / 'r1' / 'events.jsonl'
    row = json.loads(trace.read_text(encoding='utf-8').splitlines()[-1])
    assert {'schema_version', 'event_type', 'conversation_id', 'run_id', 'workflow_id',
            'trip_id', 'timestamp', 'step', 'result', 'error'} <= set(row)
    assert row['run_id'] == 'r1' and row['trip_id'] == 't1'
    assert row['result']['api_key'] == '[REDACTED_SECRET]'
    assert row['result']['content'] == 'private raw message'
    assert 'private raw message' not in caplog.text and 'sk-private' not in caplog.text


def test_execution_log_serializes_a_complete_pydantic_snapshot(tmp_path):
    path = tmp_path / 'execution.jsonl'
    configure_logging(Settings(_env_file=None, ai_log_file=path))
    request = empty_request()
    request.meta.raw_prompt = 'private user request'
    request.must_do = ['private requirement']
    with diagnostic_scope(conversation_id='c1', run_id='r1'):
        log_execution(step='run_turn.completed', result={'request': request})
    trace = tmp_path / 'conversations' / 'c1' / 'runs' / 'r1' / 'events.jsonl'
    row = json.loads(trace.read_text(encoding='utf-8').splitlines()[-1])
    snapshot = row['result']['request']
    assert snapshot['destination']['candidate_cities'] == []
    assert snapshot['meta']['raw_prompt'] == 'private user request'
    assert snapshot['must_do'] == ['private requirement']


def test_database_statement_trace_preserves_sql_and_bound_parameters(tmp_path):
    configure_logging(Settings(_env_file=None, ai_log_file=tmp_path / 'execution.jsonl'))
    engine = create_engine('sqlite:///:memory:')
    event.listen(engine, 'before_cursor_execute', _before_statement)
    event.listen(engine, 'after_cursor_execute', _after_statement)
    event.listen(engine, 'handle_error', _statement_error)
    with diagnostic_scope(conversation_id='c', run_id='r'):
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE trips (name TEXT)'))
            conn.execute(text('INSERT INTO trips (name) VALUES (:name)'), {'name': 'private@example.com'})
            conn.execute(text('SELECT name FROM trips WHERE name = :name'), {'name': 'private@example.com'})
    trace = tmp_path / 'conversations' / 'c' / 'runs' / 'r' / 'events.jsonl'
    events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
    assert {'INSERT', 'SELECT'} <= {row['result']['operation'] for row in events}
    assert any('trips' in row['result']['tables'] for row in events)
    contents = trace.read_text(encoding='utf-8')
    assert 'private@example.com' in contents
    assert 'VALUES' in contents
