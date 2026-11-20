"""Chat persistence for signed-in accounts and bounded anonymous sessions."""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.auth import ChatPrincipal, get_chat_principal
from app.db.models import AnonymousSessionRecord, MessageRecord, ConversationTurnRecord, WorkflowRequestRecord
from app.db.session import get_session
from app.services.conversations import ConversationRepository, ConversationWorkflowPersistence
from app.services.trip_summary import summarize_trip, trip_details
from shared.contracts import TripRequest, AnswerHistory, PendingQuestion, SelectionPolicy
from ai.interface import empty_request, run_turn, StaleTurn
from ai.logging import log_execution, update_diagnostic_identity
from app.services.workflow_factory import get_graph_orchestrator
from ai.orchestration.turns import check_reference
from app.core.logging import log_parser_turn

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/v1/chat', tags=['Chat'])
ANONYMOUS_SESSION_TTL = timedelta(days=30)

class SendMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: UUID | None = None
    content: str = Field(min_length=1, max_length=10000)
    input_id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID | None = None
    episode_id: UUID | None = None
    question_id: UUID | None = None
    answer: AnswerHistory | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    expected_transitions: int | None = Field(default=None, ge=0)

    @field_validator('content')
    @classmethod
    def strip_content(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Message must not be blank')
        return value

class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    message_id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime

class ChatTurnView(MessageView):
    assistant: MessageView
    trip_summary: MessageView | None = None
    parser_status: str
    missing_fields: list[str]
    error_code: str | None = None
    input_id: UUID
    revision: int
    workflow_id: UUID | None = None
    episode_id: UUID | None = None
    workflow_status: str | None = None
    questions: list[PendingQuestion] = Field(default_factory=list)
    clarification_round: int = 0
    destination_round: int = 0
    remaining_destination_rounds: int = 0
    selection_policy: SelectionPolicy | None = None
    transitions: int | None = None


@router.post('/messages', response_model=ChatTurnView, status_code=201)
async def send_message(body: SendMessage, request: Request, principal: ChatPrincipal = Depends(get_chat_principal),
                 session: Session = Depends(get_session), graph=Depends(get_graph_orchestrator)):
    from zoneinfo import ZoneInfo
    # Bind an existing conversation before its first database lookup so the
    # SQL-level trace includes the read/lock that loads it.
    if body.conversation_id is not None:
        update_diagnostic_identity(conversation_id=body.conversation_id)
    conversations = ConversationRepository(session, principal)
    # Serialize the same idempotency key even when the first request creates a conversation.
    postgres = session.bind is not None and session.bind.dialect.name == 'postgresql'
    if postgres:
        from sqlalchemy import text
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'),
                        {'key': body.input_id.int % (2**63)})
    receipt = session.get(ConversationTurnRecord, body.input_id)
    payload = body.model_dump(mode='json')
    if receipt is not None:
        conversations.get(receipt.conversation_id, lock=True)
        if receipt.input_payload != payload:
            raise StaleTurn('Input identity was already used with different content')
        if receipt.response_payload is not None:
            return ChatTurnView.model_validate(receipt.response_payload)
        raise StaleTurn('Turn checkpoint is pending reconciliation; reload the conversation')
    is_new_conversation = body.conversation_id is None
    conversation = conversations.get(body.conversation_id, lock=True) if body.conversation_id else conversations.create()
    update_diagnostic_identity(conversation_id=conversation.conversation_id,
                               workflow_id=conversation.request_id, trip_id=conversation.trip_id)
    session.info['diagnostic_identity'] = dict(
        conversation_id=str(conversation.conversation_id),
        run_id=request.state.diagnostic_run_id, request_id=request.state.request_id,
        workflow_id=str(conversation.request_id) if conversation.request_id else None,
        trip_id=str(conversation.trip_id) if conversation.trip_id else None)
    if is_new_conversation:
        # Creation precedes knowledge of its ID, so record the exact durable
        # result once the ID exists and subsequent events can correlate to it.
        log_execution(event_type='database.write', phase='flushed', step='chat.conversation',
            input={'operation': 'create_conversation', 'request_body': body.model_dump(mode='json')},
            result={'conversation_id': conversation.conversation_id,
                    'trip_id': conversation.trip_id, 'request_id': conversation.request_id,
                    'revision': conversation.revision})
    log_execution(event_type='chat.turn', phase='conversation_loaded', step='chat.send_message',
        input={'request_body': body.model_dump(mode='json'), 'conversation': {
            'conversation_id': conversation.conversation_id, 'trip_id': conversation.trip_id,
            'request_id': conversation.request_id, 'revision': conversation.revision,
            'trip_request': conversation.trip_request}}, result={'input_id': body.input_id, 'conversation_revision': conversation.revision,
                'previous_workflow_id': conversation.request_id, 'previous_trip_id': conversation.trip_id,
                'user_input': body.content, 'is_authenticated': principal.is_authenticated})
    if body.expected_revision is not None and body.expected_revision != (conversation.revision or 0):
        raise StaleTurn('Conversation changed; reload before submitting')
    pending = (session.scalar(select(ConversationTurnRecord).where(
        ConversationTurnRecord.conversation_id == conversation.conversation_id,
        ConversationTurnRecord.response_payload.is_(None))) if postgres else None)
    if pending is not None:
        raise StaleTurn('A previous turn is still being reconciled')
    receipt = ConversationTurnRecord(input_id=body.input_id,
        conversation_id=conversation.conversation_id, input_payload=payload)
    persistence = (ConversationWorkflowPersistence(session, principal.user_id, conversation, receipt)
                   if principal.is_authenticated else None)
    previous_run = None
    if persistence is not None and conversation.request_id:
        row = persistence.request(conversation.request_id, lock=True)
        if row.graph_snapshot is None:
            raise StaleTurn('Legacy conversation has no resumable graph; history remains available')
        previous_run = persistence.load_graph(conversation.request_id)
    check_reference(previous_run, workflow_id=body.workflow_id, episode_id=body.episode_id,
        question_id=body.question_id, answer=body.answer, expected_transitions=body.expected_transitions)
    rows = list(session.scalars(select(MessageRecord).where(
        MessageRecord.conversation_id == conversation.conversation_id)
        .order_by(MessageRecord.created_at.desc(), MessageRecord.message_id.desc()).limit(12)))
    history = [dict(role=row.role, content=row.content) for row in reversed(rows)]
    log_execution(event_type='database.read', phase='completed', step='chat.history',
                  input={'operation': 'recent_messages', 'conversation_id': conversation.conversation_id,
                         'limit': 12}, result={'operation': 'recent_messages', 'count': len(rows),
                          'messages': history, 'message_ids': [row.message_id for row in rows]})
    message = MessageRecord(message_id=uuid4(), conversation_id=conversation.conversation_id,
                            role='user', content=body.content, created_at=datetime.now(timezone.utc))
    session.add(message)
    session.flush()
    log_execution(event_type='database.write', phase='flushed', step='chat.user_message',
                  input={'operation': 'stage_user_message', 'message': {'message_id': message.message_id,
                         'conversation_id': message.conversation_id, 'role': message.role,
                         'content': message.content, 'created_at': message.created_at}}, result={'operation': 'stage_user_message', 'message_id': message.message_id,
                          'conversation_revision': conversation.revision, 'input_id': body.input_id})
    receipt.message_id = message.message_id
    session.add(receipt)
    conversation.revision = (conversation.revision or 0) + 1
    session.flush()
    session.info['chat_message_id'] = str(message.message_id)
    logger.info('chat.message_staged conversation_id=%s message_id=%s characters=%s',
                conversation.conversation_id, message.message_id, len(body.content))
    previous = (TripRequest.model_validate(conversation.trip_request)
                if conversation.trip_request else empty_request())
    graph.persistence = persistence
    turn = await run_turn(request.app.state.settings, graph=graph, previous=previous_run,
        seed=previous, content=body.content, history=history,
        correlation_id=request.state.request_id, conversation_id=str(conversation.conversation_id),
        current_date=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date(),
        workflow_id=body.workflow_id, episode_id=body.episode_id, question_id=body.question_id,
        answer=body.answer, expected_transitions=body.expected_transitions)
    update_diagnostic_identity(workflow_id=turn.run.state.request_id if turn.run else None,
                               trip_id=turn.run.state.trip_id if turn.run else None)
    # The SQLAlchemy dependency commits after this handler returns. Preserve
    # trace identity in session.info so that commit/rollback remains attached to
    # this exact run instead of only the long-lived conversation/workflow.
    session.info['diagnostic_identity'] = dict(
        conversation_id=str(conversation.conversation_id), run_id=getattr(turn, 'diagnostic_run_id', None)
        or request.state.diagnostic_run_id,
        workflow_id=str(turn.run.state.request_id) if turn.run else None,
        trip_id=str(turn.run.state.trip_id) if turn.run else (str(conversation.trip_id) if conversation.trip_id else None),
        request_id=request.state.request_id)
    parsed, reply, error = turn.request or previous, turn.reply, turn.error
    if not principal.is_authenticated:
        # Guest chats retain their message history and latest extracted request,
        # but cannot create account-owned trips/workflow artifacts.
        conversation.trip_request = parsed.model_dump(mode='json')
    if error:
        reply = ('Mình chưa thể phân tích tin nhắn này. Yêu cầu trước đó vẫn được giữ. '
                 'Bạn vui lòng thử lại nhé.')
    summary_needed = (turn.planning and error is None and parsed.meta.parser_status == 'ready'
                      and (turn.run is None or turn.run.state.status != 'failed')
                      and not (turn.run and turn.run.state.status == 'awaiting_relaxation'
                               and turn.run.errors and '[missing_required_fields]' in turn.run.errors[-1].message)
                      and not parsed.missing_fields
                      and (previous.meta.parser_status != 'ready'
                           or trip_details(previous) != trip_details(parsed)))
    assistant = MessageRecord(message_id=uuid4(), conversation_id=conversation.conversation_id,
                              role='assistant', content=reply or 'Đã ghi nhận.', created_at=datetime.now(timezone.utc))
    session.add(assistant)
    summary = None
    if summary_needed:
        summary = MessageRecord(message_id=uuid4(), conversation_id=conversation.conversation_id,
                                role='assistant', content=summarize_trip(parsed),
                                created_at=datetime.now(timezone.utc))
        session.add(summary)
    session.flush()
    # A guest turn may use the graph to compose a reply, but its workflow is
    # deliberately not durable: trip/workflow tables are account-owned.
    run = turn.run if principal.is_authenticated else None
    episode = run.state.destination_episode if run else None
    response = ChatTurnView(**MessageView.model_validate(message).model_dump(),
        assistant=MessageView.model_validate(assistant), parser_status='error' if error else (parsed.meta.parser_status or 'clarifying'),
        trip_summary=MessageView.model_validate(summary) if summary is not None else None,
        missing_fields=parsed.missing_fields, error_code=error, input_id=body.input_id,
        revision=conversation.revision, workflow_id=run.state.request_id if run else None,
        episode_id=episode.episode_id if episode else None, workflow_status=run.state.status if run else None,
        questions=run.pending_questions if run else [], transitions=run.transitions if run else None,
        clarification_round=run.state.clarification_round if run else 0,
        destination_round=episode.destination_round if episode else 0,
        remaining_destination_rounds=max(0, episode.max_destination_rounds - episode.destination_round) if episode else 0,
        selection_policy=SelectionPolicy.model_validate(episode.model_dump(include=set(SelectionPolicy.model_fields))) if episode else None)
    receipt.response_payload = response.model_dump(mode='json')
    session.flush()
    log_execution(event_type='chat.turn', phase='response_staged', step='chat.send_message', result={
        'parser_status': response.parser_status, 'workflow_status': response.workflow_status,
        'error_code': response.error_code, 'revision': response.revision,
        'assistant_message_id': assistant.message_id, 'summary_message_id': summary.message_id if summary else None,
        'workflow_id': response.workflow_id, 'episode_id': response.episode_id,
        'question_ids': [question.question_id for question in response.questions],
        'response': response, 'assistant_message': MessageView.model_validate(assistant),
        'summary_message': MessageView.model_validate(summary) if summary else None})
    log_parser_turn(request_id=request.state.request_id, conversation_id=conversation.conversation_id,
                    message_id=message.message_id, trip_request=parsed, error_code=error, trip_id=conversation.trip_id,
                    run_id=getattr(turn, 'diagnostic_run_id', None),
                    workflow_id=turn.run.state.request_id if turn.run else None)
    return response

@router.get('/conversations/{conversation_id}/messages', response_model=list[MessageView])
def list_messages(conversation_id: UUID, limit: int = Query(default=100, ge=1, le=100),
                  principal: ChatPrincipal = Depends(get_chat_principal), session: Session = Depends(get_session)):
    ConversationRepository(session, principal).get(conversation_id)
    rows = list(session.scalars(select(MessageRecord).where(MessageRecord.conversation_id == conversation_id)
        .order_by(MessageRecord.created_at.desc(), MessageRecord.message_id.desc()).limit(limit)))
    return list(reversed(rows))


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    conversation_id: UUID
    trip_id: UUID | None
    request_id: UUID | None
    trip_request: dict | None
    active_episode_id: UUID | None = None
    revision: int = 0

    @field_validator('trip_request', mode='before')
    @classmethod
    def normalize_trip_request(cls, value):
        return TripRequest.model_validate(value).model_dump(mode='json') if value is not None else None

    @field_validator('revision', mode='before')
    @classmethod
    def default_revision(cls, value):
        return value or 0


@router.get('/conversations/{conversation_id}/workflows')
def list_workflows(conversation_id: UUID, principal: ChatPrincipal = Depends(get_chat_principal),
                   session: Session = Depends(get_session)):
    conversation = ConversationRepository(session, principal).get(conversation_id)
    if conversation.trip_id is None:
        return []
    return [dict(workflow_id=row.request_id, episode_id=row.active_episode_id, status=row.status)
            for row in session.scalars(select(WorkflowRequestRecord).where(
                WorkflowRequestRecord.trip_id == conversation.trip_id).order_by(WorkflowRequestRecord.created_at))]


class PrepareTrip(BaseModel):
    model_config = ConfigDict(extra='forbid')
    trip_request: TripRequest


class AnonymousSessionView(BaseModel):
    anonymous_session_id: UUID
    expires_at: datetime


@router.post('/anonymous-sessions', response_model=AnonymousSessionView, status_code=201)
def create_anonymous_session(session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    row = AnonymousSessionRecord(anonymous_session_id=uuid4(), expires_at=now + ANONYMOUS_SESSION_TTL,
        last_seen_at=now)
    session.add(row)
    session.flush()
    return row


@router.post('/conversations', response_model=ConversationView, status_code=201)
def create_conversation(principal: ChatPrincipal = Depends(get_chat_principal), session: Session = Depends(get_session)):
    return ConversationRepository(session, principal).create()


@router.get('/conversations/{conversation_id}', response_model=ConversationView)
def get_conversation(conversation_id: UUID, principal: ChatPrincipal = Depends(get_chat_principal),
                     session: Session = Depends(get_session)):
    return ConversationRepository(session, principal).get(conversation_id)


@router.post('/conversations/{conversation_id}/prepare-trip', response_model=ConversationView)
def prepare_trip(conversation_id: UUID, body: PrepareTrip, principal: ChatPrincipal = Depends(get_chat_principal),
                 session: Session = Depends(get_session)):
    return ConversationRepository(session, principal).prepare_trip(conversation_id, body.trip_request)
