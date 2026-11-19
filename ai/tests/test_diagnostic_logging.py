import asyncio
import json
import os
from datetime import date

from ai.logging import configure_ai_logging, diagnostic_scope, log_execution, trace_paths
from ai.orchestration.graph_workflow import LangGraphOrchestrator
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.request_parser import empty_request
from ai.orchestration.workflow_state import STEPS
from shared.contracts import TripRequest


def read_events(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def test_trace_correlates_conversation_and_run_and_redacts(tmp_path):
    configure_ai_logging(tmp_path / 'execution.jsonl')
    request = empty_request()
    request.meta.raw_prompt = 'call me at private@example.com with sk-secret'
    with diagnostic_scope(conversation_id='conversation-a', run_id='run-a', workflow_id='workflow-a'):
        log_execution(step='workflow.node', event_type='workflow.node', phase='started', result={'request': request})
        log_execution(step='workflow.node', event_type='workflow.node', phase='completed', result={'content': 'private answer'})
    events = read_events(tmp_path / 'conversations' / 'conversation-a' / 'runs' / 'run-a' / 'events.jsonl')
    assert [event['sequence'] for event in events] == [1, 2]
    assert {event['conversation_id'] for event in events} == {'conversation-a'}
    assert {event['run_id'] for event in events} == {'run-a'}
    assert {event['workflow_id'] for event in events} == {'workflow-a'}
    text = json.dumps(events)
    assert 'private@example.com' not in text and 'sk-secret' not in text and 'private answer' not in text
    assert events[0]['result']['request']['meta']['raw_prompt']['redacted'] is True
    assert trace_paths(conversation_id='conversation-a', root=tmp_path / 'conversations') == [
        tmp_path / 'conversations' / 'conversation-a' / 'runs' / 'run-a' / 'events.jsonl']
    assert trace_paths(run_id='run-a', root=tmp_path / 'conversations') == trace_paths(
        conversation_id='conversation-a', root=tmp_path / 'conversations')


def test_concurrent_scopes_do_not_mix_trace_files(tmp_path):
    configure_ai_logging(tmp_path / 'execution.jsonl')

    async def write(conversation, run):
        with diagnostic_scope(conversation_id=conversation, run_id=run):
            for item in range(10):
                log_execution(step='test', event_type='test.event', result={'item': item})
                await asyncio.sleep(0)

    async def concurrent_writes():
        await asyncio.gather(write('conversation-a', 'run-a'), write('conversation-b', 'run-b'))

    asyncio.run(concurrent_writes())
    for conversation, run in [('conversation-a', 'run-a'), ('conversation-b', 'run-b')]:
        events = read_events(tmp_path / 'conversations' / conversation / 'runs' / run / 'events.jsonl')
        assert len(events) == 10
        assert [event['sequence'] for event in events] == list(range(1, 11))
        assert all(event['conversation_id'] == conversation and event['run_id'] == run for event in events)


def test_sequence_continues_after_nested_scope_and_transaction_event(tmp_path):
    configure_ai_logging(tmp_path / 'execution.jsonl')
    with diagnostic_scope(conversation_id='c', run_id='r'):
        log_execution(step='chat.started')
        with diagnostic_scope(conversation_id='c', run_id='r'):
            log_execution(step='workflow.started')
        log_execution(step='chat.response_staged')
    log_execution(conversation_id='c', run_id='r', step='database.transaction',
                  event_type='database.transaction', phase='committed')
    events = read_events(tmp_path / 'conversations' / 'c' / 'runs' / 'r' / 'events.jsonl')
    assert [event['sequence'] for event in events] == [1, 2, 3, 4]
    assert events[-1]['workflow_id'] is None


def test_logging_failure_never_interrupts_execution(tmp_path, monkeypatch):
    configure_ai_logging(tmp_path / 'execution.jsonl')
    monkeypatch.setattr('ai.logging._write_trace', lambda payload: (_ for _ in ()).throw(OSError('disk unavailable')))
    with diagnostic_scope(conversation_id='c', run_id='r'):
        assert log_execution(step='test', result={'safe': True}) is None


def test_oversized_event_is_compacted_before_persistence(tmp_path, monkeypatch):
    configure_ai_logging(tmp_path / 'execution.jsonl')
    monkeypatch.setattr('ai.logging.MAX_EVENT_BYTES', 400)
    with diagnostic_scope(conversation_id='c', run_id='r'):
        log_execution(step='test', result={'state': {'status': 'completed'},
                      'payload': list(range(100))})
    event = read_events(tmp_path / 'conversations' / 'c' / 'runs' / 'r' / 'events.jsonl')[0]
    assert event['result']['truncated'] is True
    assert event['result']['state'] == {'status': 'completed'}


def test_complete_mock_workflow_trace_has_routes_nodes_and_final_state(tmp_path):
    configure_ai_logging(tmp_path / 'execution.jsonl')
    graph = LangGraphOrchestrator(mock_components(), defaults=fixture('planner_defaults'))
    request = TripRequest.model_validate(fixture('trip_request'))

    async def execute():
        with diagnostic_scope(conversation_id='conversation-workflow', run_id='run-workflow'):
            return await graph.run(request, current_date=date(2026, 11, 4))

    result = asyncio.run(execute())
    events = read_events(tmp_path / 'conversations' / 'conversation-workflow' / 'runs' / 'run-workflow' / 'events.jsonl')
    assert result.state.status == 'completed'
    assert any(event['event_type'] == 'workflow.run' and event['phase'] == 'started' for event in events)
    assert any(event['event_type'] == 'workflow.run' and event['phase'] == 'completed' for event in events)
    assert {event['step'] for event in events if event['event_type'] == 'workflow.node' and event['phase'] == 'started'} == set(STEPS)
    assert any(event['event_type'] == 'workflow.route' and event['result']['target'] == 'END' for event in events)


def test_direct_graph_turns_get_distinct_run_ids_for_same_workflow(tmp_path):
    configure_ai_logging(tmp_path / 'conversations')
    graph = LangGraphOrchestrator(mock_components(), defaults=fixture('planner_defaults'))
    request = TripRequest.model_validate(fixture('trip_request'))
    first = asyncio.run(graph.run(request, current_date=date(2026, 11, 4)))
    asyncio.run(graph.run(request, current_date=date(2026, 11, 4), previous=first))
    folders = list((tmp_path / 'conversations' / 'standalone' / 'runs').iterdir())
    assert len(folders) == 2
    assert all((folder / 'events.jsonl').exists() for folder in folders)
    assert all(any(event['event_type'] == 'run_turn' and event['phase'] == 'completed'
                   for event in read_events(folder / 'events.jsonl')) for folder in folders)


def test_free_text_and_location_values_are_redacted_but_policy_is_visible(tmp_path):
    configure_ai_logging(tmp_path / 'execution.jsonl')
    with diagnostic_scope(conversation_id='c', run_id='r'):
        log_execution(step='destination_agent', result={
            'selected_region': {'city': 'Private destination'},
            'selection_reason': 'User wants a secret location',
            'selection_intent': 'DELEGATE_SELECTION', 'token_usage': {'total_tokens': 19},
            'field_decisions': {'destination.city': 'AI_DECIDE'},
            'message_id': '8c0b3ed0-c127-4351-a6ee-9737656118ed'})
    event = read_events(tmp_path / 'conversations' / 'c' / 'runs' / 'r' / 'events.jsonl')[0]
    assert event['result']['selected_region']['city']['redacted'] is True
    assert event['result']['selection_reason']['redacted'] is True
    assert event['result']['selection_intent'] == 'DELEGATE_SELECTION'
    assert event['result']['token_usage']['total_tokens'] == 19
    assert event['result']['field_decisions']['destination.city'] == 'AI_DECIDE'
    assert event['result']['message_id'] == '8c0b3ed0-c127-4351-a6ee-9737656118ed'


def test_old_runs_expire_but_recent_runs_remain(tmp_path):
    target = tmp_path / 'execution.jsonl'
    configure_ai_logging(target, retention_days=30)
    with diagnostic_scope(conversation_id='c', run_id='old'):
        log_execution(step='test')
    with diagnostic_scope(conversation_id='c', run_id='recent'):
        log_execution(step='test')
    old = tmp_path / 'conversations' / 'c' / 'runs' / 'old'
    os.utime(old, (1, 1))
    configure_ai_logging(target, retention_days=30)
    assert not old.exists()
    assert (tmp_path / 'conversations' / 'c' / 'runs' / 'recent').exists()
