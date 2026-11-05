"""Chat-only requirement collection. Never runs a planning workflow."""
import json
from copy import deepcopy
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, ValidationError
from shared.contracts import Model, TripRequest
from ai.agents.contracts import AgentContext, AgentDefinition, AgentStatus, ExecutionLimits
from ai.agents.runtime.factory import create_agent_harness

DECISIONS = Literal['UNKNOWN', 'FLEXIBLE', 'AI_DECIDE', 'NO_PREFERENCE', 'DEFERRED', 'SPECIFIED']
LABELS = {
    'destination.selection_mode': 'Bạn muốn đi đâu, hay muốn AI chọn điểm đến?',
    'destination.city': 'Bạn muốn đến thành phố nào?',
    'trip.start_date': 'Bạn dự định khởi hành ngày nào?',
    'trip.end_date': 'Bạn đi đến ngày nào hoặc trong bao nhiêu ngày?',
    'travelers.adults': 'Có bao nhiêu người lớn? Mình cần số người thực tế để tính chuyến đi.',
    'travelers.children': 'Có bao nhiêu trẻ em (nếu không có, bạn cho mình biết nhé)?',
    'budget.amount': 'Ngân sách dự kiến là bao nhiêu, hay bạn muốn AI đề xuất?',
    'budget.scope': 'Ngân sách dành cho cả nhóm hay mỗi người, gồm những khoản nào?',
    'preferences.interests': 'Bạn thích hoạt động gì, hay không có ưu tiên?',
    'preferences.pace': 'Bạn thích đi thư thả hay dày hoạt động?',
    'preferences.transport_modes': 'Bạn muốn di chuyển bằng gì, hay để AI chọn?',
}
DELEGABLE = {'destination.selection_mode', 'destination.city', 'trip.start_date', 'trip.end_date',
             'budget.amount', 'budget.scope', 'preferences.interests', 'preferences.pace',
             'preferences.transport_modes'}


def empty_request():
    return TripRequest.model_validate(dict(
        destination=dict(selection_mode=None, city=None, province=None, country=None,
                         candidate_cities=[], preferred_areas=[], must_visit=[], avoid_places=[]),
        trip=dict(start_date=None, end_date=None, duration_days=None, timezone=None,
                  arrival=dict(datetime=None, location=None), departure=dict(datetime=None, location=None)),
        travelers=dict(adults=None, children=None, children_ages=[]),
        budget=dict(amount=None, currency='VND', scope=None, includes=[], excludes=[],
                    flexibility='unspecified', max_overrun_percent=0),
        preferences=dict(interests=None, pace=None, transport_modes=None),
        daily_preferences=[], must_do=[], additional_constraints=[],
        meta=dict(raw_prompt='', field_sources={'budget.currency': 'default'}, field_confidences={}),
        missing_fields=[]))


class Change(Model):
    path: str
    value_json: str  # JSON scalar/list/object; validated against TripRequest after merge.
    decision: DECISIONS


class FollowUp(Model):
    fields: list[str] = Field(min_length=1)
    question: str = Field(min_length=1, max_length=1000)


class ParserOutput(Model):
    intent: Literal['conversation', 'travel_advice', 'trip_planning'] = 'trip_planning'
    summary: str = Field(min_length=1, max_length=4000)
    changes: list[Change]
    questions: list[FollowUp] = Field(default_factory=list)
    conflicting_input: bool = False


from ai.prompts.request_parser import PROMPT



def apply_changes(previous, output):
    payload = deepcopy(previous.model_dump(mode='json'))
    payload['meta'].setdefault('field_decisions', {})
    for change in output.changes:
        parts = change.path.split('.')
        if parts[0] in {'meta', 'missing_fields', 'schema_version'}:
            raise ValueError('Protected parser path')
        if len(parts) == 1 and parts[0] in {'destination', 'trip', 'travelers', 'budget', 'preferences'}:
            raise ValueError('Update individual fields to preserve previous answers')
        node = payload
        for part in parts[:-1]:
            node = node[part]
        if parts[-1] not in node:
            raise ValueError('Unknown parser path')
        value = json.loads(change.value_json)
        if change.decision != 'SPECIFIED' and value is not None:
            raise ValueError('Undecided fields cannot contain invented values')
        node[parts[-1]] = value
        payload['meta']['field_decisions'][change.path] = change.decision
        payload['meta']['field_sources'][change.path] = 'user'
        payload['meta']['field_confidences'].pop(change.path, None)
    payload['meta']['parser_status'] = 'clarifying'
    request = TripRequest.model_validate(payload)
    request.meta.parser_status = 'clarifying' if request.missing_fields else 'ready'
    return request


async def parse_turn(settings, *, previous, content, history, request_id, conversation_id):
    definition = AgentDefinition(name='chat_request_parser', description='Travelio conversation, travel advice and trip requirements',
        system_prompt=PROMPT, output_schema=ParserOutput,
        limits=ExecutionLimits(max_steps=1, max_tool_calls=0, max_retries=1,
            timeout=settings.llm_timeout_seconds * 2 + 2, llm_timeout=settings.llm_timeout_seconds))
    harness = create_agent_harness(definition, settings)
    try:
        result = await harness.run(definition, AgentContext(request_id=request_id,
            conversation_id=conversation_id, input_data=dict(content=content, history=history,
                previous_request=previous.model_dump(mode='json'),
                trip_request_schema=TripRequest.model_json_schema(),
                current_date=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat(),
                timezone='Asia/Ho_Chi_Minh')))
        if result.status != AgentStatus.SUCCESS:
            return None, None, result.error.code if result.error else 'INVALID_PARSER_OUTPUT'
        if result.output.intent != 'trip_planning':
            # Casual conversation and advice must never alter the collected
            # requirements or trigger missing-field questions.
            return previous.model_copy(deep=True), result.output.summary, None
        if result.output.conflicting_input:
            return None, None, 'CONFLICTING_INPUT'
        try:
            request = apply_changes(previous, result.output)
        except json.JSONDecodeError:
            return None, None, 'INVALID_PARSER_JSON'
        except ValidationError:
            return None, None, 'INVALID_TRIP_REQUEST'
        except (ValueError, KeyError, TypeError):
            return None, None, 'INVALID_PARSER_CHANGE'
        questions = []
        covered = set()
        for followup in result.output.questions:
            if (set(followup.fields) <= set(request.missing_fields)
                and not covered.intersection(followup.fields)
                and not any(request.meta.field_decisions.get(path) == 'DEFERRED'
                            and path in DELEGABLE for path in followup.fields)):
                questions.append(followup.question)
                covered.update(followup.fields)
                if len(questions) == 3:
                    break
        for path in request.missing_fields:
            if len(questions) == 3:
                break
            if path in covered:
                continue
            decision = request.meta.field_decisions.get(path)
            prefix = 'Nếu chưa biết, bạn có muốn AI đề xuất không? ' if decision == 'UNKNOWN' and path in DELEGABLE else ''
            if decision == 'DEFERRED' and path in DELEGABLE:
                continue
            questions.append(prefix + LABELS[path])
            if len(questions) == 3:
                break
        if request.missing_fields and not questions:
            questions.append('Các thông tin để sau vẫn chưa chốt. Khi sẵn sàng, bạn có thể bổ sung hoặc cho phép AI quyết định nhé.')
        # Only ask for missing requirements; the API sends a separate full
        # trip summary once the collected request is ready.
        reply = '\n\n'.join(questions) if request.missing_fields else result.output.summary
        return request, reply, None
    finally:
        close = getattr(harness.llm, 'aclose', None)
        if close:
            await close()
