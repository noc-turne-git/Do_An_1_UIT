"""Authenticated chat persistence; never log message bodies or credentials."""
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.auth import get_current_user_id
from app.db.models import MessageRecord
from app.db.session import get_session
from app.services.conversations import ConversationRepository
from app.services.trip_summary import summarize_trip, trip_details
from shared.contracts import TripRequest
from ai.interface import empty_request, parse_turn
from app.core.logging import log_parser_turn

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/v1/chat', tags=['Chat'])

class SendMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: UUID | None = None
    content: str = Field(min_length=1, max_length=10000)

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


@router.post('/messages', response_model=ChatTurnView, status_code=201)
async def send_message(body: SendMessage, request: Request, user: UUID = Depends(get_current_user_id),
                 session: Session = Depends(get_session)):
    conversations = ConversationRepository(session, user)
    conversation = conversations.get(body.conversation_id, lock=True) if body.conversation_id else conversations.create()
    rows = list(session.scalars(select(MessageRecord).where(
        MessageRecord.conversation_id == conversation.conversation_id)
        .order_by(MessageRecord.created_at.desc(), MessageRecord.message_id.desc()).limit(12)))
    history = [dict(role=row.role, content=row.content) for row in reversed(rows)]
    message = MessageRecord(message_id=uuid4(), conversation_id=conversation.conversation_id,
                            role='user', content=body.content, created_at=datetime.now(timezone.utc))
    session.add(message)
    session.flush()
    session.info['chat_message_id'] = str(message.message_id)
    logger.info('chat.message_staged conversation_id=%s message_id=%s characters=%s',
                conversation.conversation_id, message.message_id, len(body.content))
    previous = TripRequest.model_validate(conversation.trip_request) if conversation.trip_request else empty_request()
    parsed = None
    try:
        parsed, reply, error = await parse_turn(request.app.state.settings, previous=previous,
            content=body.content, history=history, request_id=request.state.request_id,
            conversation_id=str(conversation.conversation_id))
    except Exception:
        # Provider payloads and validation messages can contain credentials or user text.
        reply, error = None, 'PARSER_ERROR'
    if parsed is None:
        previous.meta.parser_status = 'error'
        parsed = previous
        reply = 'Mình chưa thể phân tích tin nhắn này. Yêu cầu trước đó vẫn được giữ. Bạn vui lòng thử lại hoặc diễn đạt rõ hơn, nhất là ngày đi và số người nhé.'
        if error in {'CONFLICTING_INPUT', 'INVALID_TRIP_REQUEST'}:
            reply = 'Thông tin vừa gửi có điểm chưa nhất quán hoặc chưa hợp lệ. Mình vẫn giữ yêu cầu trước đó. Bạn kiểm tra lại ngày đi, ngày về, số ngày và số người rồi gửi lại nhé.'
    summary_needed = (error is None and parsed.meta.parser_status == 'ready'
                      and not parsed.missing_fields
                      and (previous.meta.parser_status != 'ready'
                           or trip_details(previous) != trip_details(parsed)))
    conversation.trip_request = parsed.model_dump(mode='json')
    assistant = MessageRecord(message_id=uuid4(), conversation_id=conversation.conversation_id,
                              role='assistant', content=reply, created_at=datetime.now(timezone.utc))
    session.add(assistant)
    session.flush()
    summary = None
    if summary_needed:
        summary = MessageRecord(message_id=uuid4(), conversation_id=conversation.conversation_id,
                                role='assistant', content=summarize_trip(parsed),
                                created_at=datetime.now(timezone.utc))
        session.add(summary)
        session.flush()
    log_parser_turn(request_id=request.state.request_id, conversation_id=conversation.conversation_id,
                    message_id=message.message_id, trip_request=parsed, error_code=error, trip_id=conversation.trip_id)
    return ChatTurnView(**MessageView.model_validate(message).model_dump(),
        assistant=MessageView.model_validate(assistant), parser_status=parsed.meta.parser_status,
        trip_summary=MessageView.model_validate(summary) if summary is not None else None,
        missing_fields=parsed.missing_fields, error_code=error)

@router.get('/conversations/{conversation_id}/messages', response_model=list[MessageView])
def list_messages(conversation_id: UUID, limit: int = Query(default=100, ge=1, le=100),
                  user: UUID = Depends(get_current_user_id), session: Session = Depends(get_session)):
    ConversationRepository(session, user).get(conversation_id)
    rows = list(session.scalars(select(MessageRecord).where(MessageRecord.conversation_id == conversation_id)
        .order_by(MessageRecord.created_at.desc(), MessageRecord.message_id.desc()).limit(limit)))
    return list(reversed(rows))


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    conversation_id: UUID
    trip_id: UUID | None
    request_id: UUID | None
    trip_request: dict | None


class PrepareTrip(BaseModel):
    model_config = ConfigDict(extra='forbid')
    trip_request: TripRequest


@router.post('/conversations', response_model=ConversationView, status_code=201)
def create_conversation(user: UUID = Depends(get_current_user_id), session: Session = Depends(get_session)):
    return ConversationRepository(session, user).create()


@router.get('/conversations/{conversation_id}', response_model=ConversationView)
def get_conversation(conversation_id: UUID, user: UUID = Depends(get_current_user_id),
                     session: Session = Depends(get_session)):
    return ConversationRepository(session, user).get(conversation_id)


@router.post('/conversations/{conversation_id}/prepare-trip', response_model=ConversationView)
def prepare_trip(conversation_id: UUID, body: PrepareTrip, user: UUID = Depends(get_current_user_id),
                 session: Session = Depends(get_session)):
    return ConversationRepository(session, user).prepare_trip(conversation_id, body.trip_request)
