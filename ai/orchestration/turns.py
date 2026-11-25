"""Turn envelopes and lifecycle seeds shared by every transport."""
from dataclasses import dataclass
from typing import Literal

from shared.contracts import TripRequest, Destination
from shared.errors import ApplicationError


class StaleTurn(ApplicationError, ValueError):
    def __init__(self, message):
        super().__init__('stale_turn', message)


@dataclass
class ParsedTurn:
    request: TripRequest | None
    reply: str | None = None
    error: str | None = None
    planning: bool = True
    action: Literal['information', 'destination_recommendation', 'destination_selection',
                    'selection_delegation', 'itinerary_planning', 'itinerary_modification'] = 'itinerary_planning'
    # Parser-supplied wording proposals; workflow retains field and budget control.
    question_drafts: list[dict] | None = None
    destination_action: str = 'none'
    changed_fields: list[str] | None = None


@dataclass
class TurnResult(ParsedTurn):
    run: object | None = None


def check_reference(previous, *, workflow_id=None, episode_id=None, question_id=None,
                    answer=None, expected_transitions=None):
    """Run before any parser sees the message, including explicit-input turns."""
    if expected_transitions is not None and (
            previous is None or previous.transitions != expected_transitions):
        raise StaleTurn('Workflow changed; reload before submitting')
    if workflow_id is not None and (previous is None or previous.state.request_id != workflow_id):
        raise StaleTurn('Response belongs to another workflow')
    if answer is not None:
        if question_id is not None and question_id != answer.question_id:
            raise StaleTurn('Conflicting question references')
        if episode_id is not None and episode_id != answer.episode_id:
            raise StaleTurn('Conflicting episode references')
        question_id, episode_id = answer.question_id, answer.episode_id
    if episode_id is not None and (previous is None or not previous.state.destination_episode
            or previous.state.destination_episode.episode_id != episode_id):
        raise StaleTurn('Response belongs to another episode')
    if question_id is None and answer is None:
        return None
    if previous is None or previous.state.status in {'completed', 'failed'}:
        raise StaleTurn('Terminal workflow cannot accept answers')
    question = next((q for q in previous.pending_questions
                     if q.question_id == question_id and q.status == 'open'), None)
    if question is None or episode_id is None or question.episode_id != episode_id:
        raise StaleTurn('Question is closed, superseded, or belongs to another episode')
    try:
        question.require_actionable()
        if answer is not None:
            answer.validate_for(question)
    except ValueError as exc:
        raise StaleTurn(str(exc)) from exc
    return question


def seed_after_failed(previous: TripRequest, destination: Destination, raw_prompt: str):
    """Approved Lifecycle B baseline; never carry destination candidates/metadata."""
    if (destination.selection_intent != 'EXPLICIT' or destination.selection_authority != 'USER'
            or destination.selection_mode != 'explicit' or not destination.city
            or not destination.city.strip()):
        raise StaleTurn('A new explicit user destination is required after failure')
    data = previous.model_dump(mode='json')
    data['destination'] = destination.model_dump(mode='json')
    for key in ('field_sources', 'field_confidences', 'field_decisions'):
        data['meta'][key] = {k: v for k, v in data['meta'].get(key, {}).items()
                             if not k.startswith('destination.')}
    data['meta']['field_sources'].update({'destination.city': 'user', 'destination.selection_mode': 'user'})
    data['meta'].update(raw_prompt=raw_prompt, parser_status=None)
    data['missing_fields'] = []
    return TripRequest.model_validate(data)
