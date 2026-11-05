import json
import logging
from app.core.config import Settings
from app.core.logging import configure_logging, log_message
from ai.logging import log_execution

def test_backend_console_and_ai_jsonl_rotation(tmp_path, caplog):
    path = tmp_path / 'ai' / 'execution.jsonl'
    settings = Settings(_env_file=None, ai_log_file=path, log_max_bytes=500, log_backup_count=2)
    configure_logging(settings)
    configure_logging(settings)
    assert len(logging.getLogger('travel.ai').handlers) == 1
    with caplog.at_level('INFO'):
        log_message(message_id='m1', role='user', content='private raw message')
        for _ in range(10):
            log_execution(run_id='r1', trip_id='t1', step='planner',
                result={'status': 'completed', 'api_key': 'sk-private', 'content': 'private raw message'}, error=None)
    assert not (tmp_path / 'backend' / 'logs').exists()
    assert path.with_name('execution.jsonl.1').exists()
    assert path.with_name('execution.jsonl.2').exists()
    row = json.loads(path.read_text(encoding='utf-8').splitlines()[-1])
    assert set(row) == {'run_id', 'trip_id', 'timestamp', 'step', 'result', 'error'}
    assert row['run_id'] == 'r1' and row['trip_id'] == 't1'
    assert row['result']['api_key'] == '[redacted]'
    assert 'private raw message' not in caplog.text and 'sk-private' not in caplog.text
