"""Backend operational events use console handlers only."""
import json
import logging
from ai.logging import configure_ai_logging, log_execution

def configure_logging(settings):
    logging.basicConfig(level=settings.log_level,
        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.getLogger('app').setLevel(settings.log_level)
    configure_ai_logging(settings.ai_log_file, max_bytes=settings.log_max_bytes,
                         backups=settings.log_backup_count, level=settings.log_level)

def log_message(*, message_id, role, content, conversation_id=None, trip_id=None):
    logging.getLogger('conversation').info(json.dumps(dict(
        message_id=str(message_id), role=role, characters=len(content),
        conversation_id=str(conversation_id) if conversation_id else None,
        trip_id=str(trip_id) if trip_id else None)))

def log_parser_turn(*, request_id, conversation_id, message_id, trip_request, error_code, trip_id=None):
    log_execution(run_id=request_id, trip_id=trip_id, step='chat.parser_turn',
        result={'status': trip_request.meta.parser_status}, error=error_code)
