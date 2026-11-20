"""Chat ownership and the explicit boundary from a draft to a workflow request."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select
from shared.errors import ApplicationError
from app.api.auth import ChatPrincipal
from app.db.models import AnonymousSessionRecord, ConversationRecord
from shared.contracts import TripRequest
from app.repositories.workflows import OwnedRepository, TripRepository, RequestRepository
from app.repositories.artifacts import ArtifactRepository


def require_ready(value: TripRequest) -> TripRequest:
    # Revalidate even Python callers; never trust model_construct or stale flags.
    request = TripRequest.model_validate(value.model_dump(mode='json'))
    required = [request.trip.start_date, request.trip.end_date,
                request.travelers.adults, request.travelers.children]
    if request.missing_fields or any(v is None for v in required):
        raise ApplicationError('incomplete_trip_request', 'TripRequest is missing required information')
    if request.travelers.adults + request.travelers.children < 1:
        raise ApplicationError('incomplete_trip_request', 'At least one traveler is required')
    return request


class ConversationRepository(OwnedRepository):
    def __init__(self, session, principal: ChatPrincipal):
        self.principal = principal
        # Workflow repositories are used only for authenticated conversations.
        super().__init__(session, principal.user_id or uuid4())

    def _owner_clause(self):
        if self.principal.user_id is not None:
            return ConversationRecord.user_id == self.principal.user_id
        session_id = self.principal.anonymous_session_id
        if session_id is None:
            raise ApplicationError('not_found', 'Conversation not found')
        guest = self.session.get(AnonymousSessionRecord, session_id)
        if guest is None or guest.expires_at <= datetime.now(timezone.utc):
            raise ApplicationError('not_found', 'Anonymous session not found or expired')
        guest.last_seen_at = datetime.now(timezone.utc)
        return ConversationRecord.anonymous_session_id == session_id

    def get(self, conversation_id, *, lock=False):
        query = select(ConversationRecord).where(ConversationRecord.conversation_id == conversation_id,
                                                 self._owner_clause())
        if lock:
            query = query.with_for_update()
        row = self.session.scalar(query.execution_options(populate_existing=True))
        if row is None:
            raise ApplicationError('not_found', 'Conversation not found')
        return row

    def create(self):
        # Validate a guest capability before it can own a new conversation.
        if not self.principal.is_authenticated:
            self._owner_clause()
        row = ConversationRecord(conversation_id=uuid4(), user_id=self.principal.user_id,
            anonymous_session_id=self.principal.anonymous_session_id, revision=0)
        self.session.add(row)
        self.session.flush()
        return row

    def prepare_trip(self, conversation_id, value: TripRequest):
        if not self.principal.is_authenticated:
            raise ApplicationError('authentication_required', 'Please sign in to save a trip')
        conversation = self.get(conversation_id, lock=True)
        request = require_ready(value)
        payload = request.model_dump(mode='json')
        if conversation.trip_id is not None:
            if conversation.trip_request != payload or conversation.request_id is None:
                raise ApplicationError('conversation_already_linked', 'Conversation already has a different trip')
            return conversation
        trip = TripRepository(self.session, self.user_id).create(title=request.destination.city)
        workflow = RequestRepository(self.session, self.user_id).create(trip.trip_id,
                                                                      schema_version=request.schema_version)
        ArtifactRepository(self.session, self.user_id).add(workflow.request_id, 'trip_request', request)
        conversation.trip_id = trip.trip_id
        conversation.request_id = workflow.request_id
        conversation.trip_request = payload
        self.session.flush()
        return conversation


from app.services.persistence import WorkflowPersistence


class ConversationWorkflowPersistence(WorkflowPersistence):
    """Associate the conversation at every durable graph checkpoint."""
    def __init__(self, session, user_id, conversation, receipt):
        super().__init__(session, user_id)
        self.conversation = conversation
        self.receipt = receipt

    def save_graph(self, run):
        super().save_graph(run)
        conversation = self.conversation
        conversation.trip_id = run.state.trip_id
        conversation.request_id = run.state.request_id
        conversation.active_episode_id = (run.state.destination_episode.episode_id
                                           if run.state.destination_episode else None)
        if 'request_parser' in run.outputs:
            conversation.trip_request = run.outputs['request_parser'].model_dump(mode='json')
        self.receipt.request_id = run.state.request_id
        self.session.flush()
