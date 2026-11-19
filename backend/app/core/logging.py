"""Backend operational events use console handlers only."""
import json
import logging
from ai.logging import diagnostic_snapshot
from ai.logging import configure_ai_logging, log_execution

def configure_logging(settings):
    logging.basicConfig(level=settings.log_level,
        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.getLogger('app').setLevel(settings.log_level)
    configure_ai_logging(settings.ai_log_file or settings.ai_trace_root, max_bytes=settings.log_max_bytes,
                         backups=settings.log_backup_count, level=settings.log_level,
                         retention_days=settings.diagnostic_retention_days)

def log_message(*, message_id, role, content, conversation_id=None, trip_id=None):
    logging.getLogger('conversation').info(json.dumps(dict(
        message_id=str(message_id), role=role, characters=len(content),
        conversation_id=str(conversation_id) if conversation_id else None,
        trip_id=str(trip_id) if trip_id else None)))

def log_parser_turn(*, request_id, conversation_id, message_id, trip_request, error_code,
                    trip_id=None, run_id=None, workflow_id=None):
    # Keep the completed parser state in the ordinary diagnostic stream too.
    # ``diagnostic_snapshot`` preserves business context while redacting only
    # credentials embedded in free text or sensitive fields.
    event = diagnostic_snapshot({
        'event': 'chat.parser_turn', 'request_id': request_id,
        'conversation_id': conversation_id, 'trip_id': trip_id,
        'workflow_id': workflow_id, 'run_id': run_id or request_id,
        'message_id': message_id, 'status': trip_request.meta.parser_status,
        'missing_fields': trip_request.missing_fields,
        'parsed_trip_request': trip_request, 'error_code': error_code,
    })
    logging.getLogger('conversation').info(json.dumps(event, ensure_ascii=False))
    log_execution(run_id=run_id or request_id, workflow_id=workflow_id, request_id=request_id,
        conversation_id=conversation_id, trip_id=trip_id, step='chat.parser_turn',
        event_type='chat.parser', phase='completed', result={
            'message_id': message_id, 'status': trip_request.meta.parser_status,
            'missing_fields': trip_request.missing_fields,
            'parsed_trip_request': trip_request}, error=error_code)
