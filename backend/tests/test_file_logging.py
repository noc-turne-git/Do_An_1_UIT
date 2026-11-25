import logging
from app.core.config import Settings
from app.core.logging import configure_logging, log_message
from ai.logging import diagnostic_scope, log_execution, mask

def test_backend_console_and_test_trace_suppression(tmp_path, caplog):
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
    assert not (tmp_path / 'ai' / 'conversations').exists()
    assert mask({'api_key': 'sk-private'})['api_key'] == '[REDACTED_SECRET]'
    assert 'private raw message' not in caplog.text and 'sk-private' not in caplog.text
