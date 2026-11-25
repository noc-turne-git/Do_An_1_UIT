import asyncio

from ai.logging import configure_ai_logging, diagnostic_scope, log_execution, mask
from ai.orchestration.request_parser import empty_request


def test_test_process_suppresses_traces_and_redacts_secrets(tmp_path):
    configure_ai_logging(tmp_path / 'execution.jsonl')
    request = empty_request()
    request.meta.raw_prompt = 'call me at private@example.com with sk-secret'
    with diagnostic_scope(conversation_id='conversation-a', run_id='run-a', workflow_id='workflow-a'):
        log_execution(step='workflow.node', event_type='workflow.node', phase='started', result={'request': request})
        log_execution(step='workflow.node', event_type='workflow.node', phase='completed', result={'content': 'private answer'})
    assert not (tmp_path / 'conversations').exists()
    redacted = mask({'request': request.model_dump(mode='json'), 'api_key': 'sk-secret'})
    assert redacted['api_key'] == '[REDACTED_SECRET]'
    assert redacted['request']['meta']['raw_prompt'] == (
        'call me at [REDACTED_EMAIL] with [REDACTED_SECRET]')


def test_concurrent_test_scopes_do_not_write_trace_files(tmp_path):
    configure_ai_logging(tmp_path / 'execution.jsonl')

    async def write(conversation, run):
        with diagnostic_scope(conversation_id=conversation, run_id=run):
            for item in range(10):
                log_execution(step='test', event_type='test.event', result={'item': item})
                await asyncio.sleep(0)

    async def concurrent_writes():
        await asyncio.gather(write('conversation-a', 'run-a'), write('conversation-b', 'run-b'))

    asyncio.run(concurrent_writes())
    assert not (tmp_path / 'conversations').exists()


def test_logging_failure_never_interrupts_execution(tmp_path, monkeypatch):
    configure_ai_logging(tmp_path / 'execution.jsonl')
    monkeypatch.setattr('ai.logging._write_trace', lambda payload: (_ for _ in ()).throw(OSError('disk unavailable')))
    with diagnostic_scope(conversation_id='c', run_id='r'):
        assert log_execution(step='test', result={'safe': True}) is None
