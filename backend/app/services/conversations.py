"""Chat ownership and the explicit boundary from a draft to a workflow request."""
from uuid import uuid4
from sqlalchemy import select
from shared.errors import ApplicationError
from app.db.models import ConversationRecord
from shared.contracts import TripRequest
from app.repositories.workflows import OwnedRepository, TripRepository, RequestRepository
from app.repositories.artifacts import ArtifactRepository


def require_ready(value: TripRequest) -> TripRequest:
    # Revalidate even Python callers; never trust model_construct or stale flags.
    request = TripRequest.model_validate(value.model_dump(mode='json'))
    required = [request.destination.selection_mode, request.trip.start_date,
                request.trip.end_date, request.travelers.adults, request.travelers.children,
                request.preferences.interests, request.preferences.pace,
                request.preferences.transport_modes, request.budget.amount, request.budget.scope]
    if request.destination.selection_mode == 'explicit':
        required.append(request.destination.city)
    if request.missing_fields or any(v is None or (isinstance(v, str) and not v.strip()) for v in required):
        raise ApplicationError('incomplete_trip_request', 'TripRequest is missing required information')
    if request.travelers.adults + request.travelers.children < 1:
        raise ApplicationError('incomplete_trip_request', 'At least one traveler is required')
    return request


class ConversationRepository(OwnedRepository):
    def get(self, conversation_id, *, lock=False):
        query = select(ConversationRecord).where(ConversationRecord.conversation_id == conversation_id,
                                                 ConversationRecord.user_id == self.user_id)
        if lock:
            query = query.with_for_update()
        row = self.session.scalar(query.execution_options(populate_existing=True))
        if row is None:
            raise ApplicationError('not_found', 'Conversation not found')
        return row

    def create(self):
        row = ConversationRecord(conversation_id=uuid4(), user_id=self.user_id)
        self.session.add(row)
        self.session.flush()
        return row

    def prepare_trip(self, conversation_id, value: TripRequest):
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
