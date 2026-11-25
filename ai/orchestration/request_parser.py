"""Extract and merge user requirements; lifecycle and issuance belong to Graph."""
import json
import re
from copy import deepcopy
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, ValidationError
from shared.contracts import (DestinationAction, DestinationFieldDecision, LEGACY_DECLINED_DECISIONS, Model,
                              TRIP_COLLECTION_FIELDS, TripFieldState, TripRequest)
from ai.agents.contracts import AgentContext, AgentDefinition, AgentStatus, ExecutionLimits
from ai.agents.runtime.factory import create_agent_harness
from ai.orchestration.date_normalization import DATE_PATHS, normalize_trip_dates
from ai.orchestration.destination_resolution import clear_region_fields
from ai.logging import log_execution

DECISIONS = TripFieldState | DestinationFieldDecision
ACKNOWLEDGEMENT = 'Mình đã ghi nhận yêu cầu chuyến đi của bạn.'
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
DESTINATION_SELECTION_PATHS = frozenset({'destination.selection_mode', 'destination.city'})
NON_NULL_COLLECTION_FIELDS = frozenset({
    'destination.candidate_cities', 'destination.preferred_areas', 'destination.must_visit',
    'destination.avoid_places', 'travelers.children_ages', 'budget.includes', 'budget.excludes',
    'daily_preferences', 'must_do', 'additional_constraints',
})


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


def apply_traveler_evidence(request, content, previous=None):
    """Keep narrow traveler phrases from becoming unsupported user facts."""
    phrase = re.sub(r'[.!?]+$', '', content.strip().lower()).strip()
    data = request.model_dump()
    before = previous or empty_request()
    has_traveler_count = bool(re.search(r'\d+\s+(?:người lớn|trẻ em|em bé|bé|con)\b', phrase))
    adult_count = re.search(r'(?<!\d)(\d+)\s+người lớn\b', phrase)
    has_child_evidence = bool(re.search(r'\b(?:trẻ em|em bé|bé|con)\b', phrase))
    direct_adult_count = re.fullmatch(r'(\d+)\s+người lớn', phrase)
    inferred_family = bool(re.fullmatch(
        r'(?:tôi|mình|em|con)\s+(?:và|với)\s+(?:ba mẹ|bố mẹ|cha mẹ)', phrase))
    if 'cả nhà' in phrase and not has_traveler_count:
        fields = ('adults', 'children')
    elif inferred_family:
        fields = ('adults', 'children') if before.travelers.adults is not None else ('children',)
    elif adult_count and not has_child_evidence:
        fields = ('children',)
    else:
        fields = ()
    for field in fields:
        path = f'travelers.{field}'
        data['travelers'][field] = getattr(before.travelers, field)
        for key in ('field_sources', 'field_confidences', 'field_decisions'):
            data['meta'][key].pop(path, None)
            if path in getattr(before.meta, key):
                data['meta'][key][path] = getattr(before.meta, key)[path]
    if direct_adult_count:
        data['travelers']['adults'] = int(direct_adult_count.group(1))
        data['meta']['field_sources']['travelers.adults'] = 'user'
        data['meta']['field_confidences'].pop('travelers.adults', None)
        data['meta']['field_decisions']['travelers.adults'] = 'SPECIFIED'
    if inferred_family and before.travelers.adults is None:
        data['travelers']['adults'] = 3
        data['meta']['field_sources']['travelers.adults'] = 'inferred'
        data['meta']['field_confidences']['travelers.adults'] = 0.95
        data['meta']['field_decisions']['travelers.adults'] = 'SPECIFIED'
    return TripRequest.model_validate(data)


class Change(Model):
    path: str
    value_json: str  # JSON scalar/list/object; validated against TripRequest after merge.
    decision: DECISIONS


class FollowUp(Model):
    fields: list[str] = Field(min_length=1)
    question: str = Field(min_length=1, max_length=1000)


class ParserOutput(Model):
    intent: Literal['conversation', 'travel_advice', 'trip_planning'] = 'trip_planning'
    requested_action: Literal['information', 'destination_recommendation',
        'destination_selection', 'selection_delegation', 'itinerary_planning',
        'itinerary_modification'] | None = None
    summary: str = Field(min_length=1, max_length=4000)
    changes: list[Change]
    questions: list[FollowUp] = Field(default_factory=list)
    conflicting_input: bool = False
    destination_action: DestinationAction = 'none'


from ai.prompts.request_parser import PROMPT



def apply_changes(previous, output, *, current_date=None):
    payload = deepcopy(previous.model_dump(mode='json'))
    payload['meta'].setdefault('field_decisions', {})
    date_updates = {}
    destination_changes = {}
    for change in output.changes:
        parts = change.path.split('.')
        if parts[0] in {'meta', 'missing_fields', 'schema_version'}:
            raise ValueError('Protected parser path')
        if change.path.startswith(('destination.selection_intent', 'destination.selection_authority',
                                   'destination.destination_source', 'destination.selection_provenance')):
            raise ValueError('Selection policy is owned by CODE, not the parser')
        if len(parts) == 1 and parts[0] in {'destination', 'trip', 'travelers', 'budget', 'preferences'}:
            raise ValueError('Update individual fields to preserve previous answers')
        node = payload
        for part in parts[:-1]:
            node = node[part]
        if parts[-1] not in node:
            raise ValueError('Unknown parser path')
        value = json.loads(change.value_json)
        decision = change.decision
        if decision == 'UNASKED':
            # A failed extraction or omitted answer is not a new user decision.
            if value is not None:
                raise ValueError('UNASKED cannot supply a value')
            continue
        if change.path in TRIP_COLLECTION_FIELDS and decision in LEGACY_DECLINED_DECISIONS:
            decision = 'DECLINED'
        if change.path.startswith('destination.') and decision == 'DECLINED':
            raise ValueError('Destination retains its own decision vocabulary')
        if decision != 'SPECIFIED' and value is not None:
            raise ValueError('Undecided fields cannot contain invented values')
        if decision == 'SPECIFIED' and change.path in TRIP_COLLECTION_FIELDS and (
                value is None or isinstance(value, str) and not value.strip()):
            raise ValueError('SPECIFIED requires a valid value')
        # Deferring a destination-selection answer is intentionally a no-op for
        # the current selection state.  In particular, do not erase an existing
        # selection_mode merely because the user wants to settle it later.
        preserve_destination_selection = (
            change.path in DESTINATION_SELECTION_PATHS and decision == 'DEFERRED'
        )
        if change.path in DATE_PATHS:
            date_updates[change.path] = value
        # Some collection-valued schema fields (for example preferred_areas)
        # are not nullable, so retain their current list while recording a
        # non-specific decision in metadata.
        elif not preserve_destination_selection and not (
                change.path in NON_NULL_COLLECTION_FIELDS and decision != 'SPECIFIED' and value is None):
            node[parts[-1]] = value
        if change.path in DESTINATION_SELECTION_PATHS:
            destination_changes[change.path] = (decision, value)
        payload['meta']['field_decisions'][change.path] = decision
        payload['meta']['field_sources'][change.path] = 'user'
        payload['meta']['field_confidences'].pop(change.path, None)
    normalized = normalize_trip_dates(previous, date_updates, current_date=current_date)
    # An unresolved date expression cannot erase an established answer/refusal.
    ambiguous = {path for issue in normalized.issues if issue.reason == 'ambiguous'
                 for path in issue.fields}
    preserved = {path for path in ambiguous if not previous.should_ask(path)}
    if preserved:
        for path in preserved:
            date_updates.pop(path, None)
            for key in ('field_decisions', 'field_sources', 'field_confidences'):
                payload['meta'][key].pop(path, None)
                if path in getattr(previous.meta, key):
                    payload['meta'][key][path] = getattr(previous.meta, key)[path]
        normalized = normalize_trip_dates(previous, date_updates, current_date=current_date)
    if normalized.conflicting:
        raise ValidationError.from_exception_data('TripRequest', [{
            'type': 'value_error', 'loc': ('trip',), 'input': payload['trip'],
            'ctx': {'error': ValueError('; '.join(issue.detail for issue in normalized.issues
                                                  if issue.reason == 'conflicting'))}}])
    payload['trip'].update(normalized.trip_fields())
    for issue in normalized.issues:
        if issue.reason == 'ambiguous':
            for path in issue.fields:
                payload['meta']['field_decisions'][path] = 'UNASKED'
                payload['meta']['field_sources'].pop(path, None)
    for path in normalized.derived_fields:
        payload['meta']['field_sources'][path] = 'inferred'
        payload['meta']['field_confidences'][path] = 1.0
        payload['meta']['field_decisions'][path] = 'SPECIFIED'
    if destination_changes:
        city = destination_changes.get('destination.city')
        mode = destination_changes.get('destination.selection_mode')
        decisions = {entry[0] for entry in destination_changes.values()}
        decision = ('AI_DECIDE' if 'AI_DECIDE' in decisions else
                    'FLEXIBLE' if 'FLEXIBLE' in decisions else
                    'NO_PREFERENCE' if 'NO_PREFERENCE' in decisions else
                    'UNKNOWN' if 'UNKNOWN' in decisions else None)
        if city and city[0] == 'SPECIFIED' and isinstance(city[1], str) and city[1].strip():
            payload['destination'].update(selection_intent='EXPLICIT',
                selection_authority='USER', destination_source='USER', selection_mode='explicit',
                selection_provenance=dict(source='user', evidence='destination.city=' + city[1]))
            payload['meta']['field_sources']['destination.selection_mode'] = 'user'
            payload['meta']['field_decisions']['destination.selection_mode'] = 'SPECIFIED'
            if city[1] != previous.destination.city:
                changed_paths = {change.path for change in output.changes}
                clear_region_fields(payload, [field for field in ('province', 'country')
                    if f'destination.{field}' not in changed_paths
                    and previous.meta.field_sources.get(f'destination.{field}') != 'user'])
        elif decision in {'UNKNOWN', 'FLEXIBLE', 'NO_PREFERENCE', 'AI_DECIDE'}:
            intent = {'UNKNOWN': 'USER_UNKNOWN', 'FLEXIBLE': 'ANY_DESTINATION',
                      'NO_PREFERENCE': 'ANY_DESTINATION', 'AI_DECIDE': 'DELEGATE_SELECTION'}[decision]
            authority = {'UNKNOWN': 'USER', 'FLEXIBLE': 'USER',
                         'NO_PREFERENCE': 'USER', 'AI_DECIDE': 'USER'}[decision]
            payload['destination'].update(selection_intent=intent,
                selection_authority=authority, destination_source=None,
                selection_mode='implicit' if decision != 'UNKNOWN' else 'ambiguous',
                selection_provenance=dict(source='user', evidence='destination:' + decision),
                city=None)
            changed_paths = {change.path for change in output.changes}
            clear_region_fields(payload, [field for field in ('province', 'country')
                if f'destination.{field}' not in changed_paths
                and previous.destination.destination_source is not None
                and previous.meta.field_sources.get(f'destination.{field}') != 'user'])
            payload['meta']['field_sources']['destination.selection_mode'] = 'user'
            payload['meta']['field_decisions']['destination.selection_mode'] = decision
        elif 'DEFERRED' in decisions:
            # The metadata records that clarification was deferred, while the
            # policy remains exactly as it was before this turn.
            pass
        elif city and city[1] is None:
            payload['destination'].update(selection_intent='UNSPECIFIED',
                selection_authority=None, destination_source=None, selection_provenance=None)
        elif mode and mode[1] == 'implicit':
            # A parser's choice of resolve mode is not evidence of delegation.
            payload['destination'].update(selection_intent='UNSPECIFIED',
                selection_authority=None, destination_source=None, selection_provenance=None)
    payload['meta']['parser_status'] = 'clarifying'
    request = TripRequest.model_validate(payload)
    request.meta.parser_status = 'clarifying' if request.missing_fields else 'ready'
    return request


def applicable_followups(request, followups):
    """Accept wording only when every assigned field can still be asked."""
    questions, covered = [], set()
    for followup in followups:
        fields = set(followup.fields)
        if (fields and fields <= set(request.missing_fields)
                and all(request.should_ask(path) for path in fields)
                and not covered.intersection(fields)):
            questions.append(followup)
            covered.update(fields)
            if len(questions) == 3:
                break
    return questions


def collection_question(request, *, fields=None, drafts=()):
    """One state-checked draft or one deterministic LABELS question."""
    allowed = set(request.missing_fields if fields is None else fields)
    candidates = []
    for draft in drafts:
        try:
            candidate = FollowUp.model_validate(draft)
        except (ValidationError, TypeError, ValueError):
            continue
        if set(candidate.fields) <= allowed:
            candidates.append(candidate)
    followups = applicable_followups(request, candidates)
    if followups:
        return followups[0].model_dump()
    for path in request.missing_fields:
        if path in allowed and path in LABELS and request.should_ask(path):
            return dict(fields=[path], question=LABELS[path])
    return None


def recommendation_request(request, *, current_date=None):
    """A request for suggestions leaves the user in charge of choosing."""
    if request.destination.selection_intent != 'UNSPECIFIED':
        return request
    return apply_changes(request, ParserOutput(summary='Destination recommendations',
        changes=[Change(path='destination.city', value_json='null', decision='UNKNOWN')]),
        current_date=current_date)


async def parse_turn(settings, *, previous, content, history, request_id, conversation_id,
                     extraction_only=False, pending_question=None, workflow_context=None):
    from ai.orchestration.turns import ParsedTurn
    def result_value(value, reply, error, planning=True):
        return ParsedTurn(value, reply, error, planning, action='information') if extraction_only else (value, reply, error)
    timezone_name = previous.trip.timezone or 'Asia/Ho_Chi_Minh'
    user_date = datetime.now(ZoneInfo(timezone_name)).date()
    definition = AgentDefinition(name='chat_request_parser', description='Travelio conversation, travel advice and trip requirements',
        system_prompt=PROMPT, output_schema=ParserOutput,
        limits=ExecutionLimits(max_steps=1, max_tool_calls=0, max_retries=1,
            timeout=settings.llm_timeout_seconds * 2 + 2, llm_timeout=settings.llm_timeout_seconds))
    harness = create_agent_harness(definition, settings)
    try:
        log_execution(run_id=request_id, conversation_id=conversation_id, step='parser.extract',
            event_type='parser.input', phase='received', input={
                'content': content, 'conversation_history': history,
                'previous_request': previous, 'pending_question': pending_question,
                'workflow_context': workflow_context, 'current_date': user_date,
                'timezone': timezone_name, 'system_prompt': PROMPT})
        result = await harness.run(definition, AgentContext(request_id=request_id,
            conversation_id=conversation_id, input_data=dict(content=content, history=history,
                previous_request=previous.model_dump(mode='json'),
                pending_question=pending_question, workflow_context=workflow_context,
                trip_request_schema=TripRequest.model_json_schema(),
                current_date=user_date.isoformat(),
                timezone=timezone_name)))
        log_execution(run_id=request_id, conversation_id=conversation_id, step='parser.extract',
            event_type='parser.agent_output', phase='received',
            input={'content': content, 'previous_request': previous}, output=result)
        if result.status != AgentStatus.SUCCESS:
            return result_value(None, None, result.error.code if result.error else 'INVALID_PARSER_OUTPUT')
        action = result.output.requested_action or (
            'information' if result.output.intent != 'trip_planning' else 'itinerary_planning')
        if action == 'information' or result.output.intent == 'conversation':
            # Casual conversation and advice must never alter the collected
            # requirements or trigger missing-field questions.
            return result_value(previous.model_copy(deep=True), result.output.summary, None, False)
        if result.output.conflicting_input:
            return result_value(None, None, 'CONFLICTING_INPUT')
        try:
            request = apply_traveler_evidence(
                apply_changes(previous, result.output, current_date=user_date), content, previous)
            if (action == 'destination_recommendation'
                    and request.destination.selection_intent == 'UNSPECIFIED'):
                request = recommendation_request(request, current_date=user_date)
            log_execution(run_id=request_id, conversation_id=conversation_id, step='parser.apply_changes',
                event_type='parser.transformation', phase='completed',
                input={'previous_request': previous, 'parser_output': result.output,
                       'current_date': user_date}, output={'trip_request': request})
        except json.JSONDecodeError:
            return result_value(None, None, 'INVALID_PARSER_JSON')
        except ValidationError:
            return result_value(None, None, 'INVALID_TRIP_REQUEST')
        except (ValueError, KeyError, TypeError):
            return result_value(None, None, 'INVALID_PARSER_CHANGE')
        if extraction_only:
            request.meta.raw_prompt = content
            return ParsedTurn(request, ACKNOWLEDGEMENT,
                              action=action,
                              destination_action=result.output.destination_action,
                              changed_fields=[change.path for change in result.output.changes],
                              question_drafts=[question.model_dump() for question in
                                               applicable_followups(request, result.output.questions)])
        # Ask one actionable question per turn.  Remaining LLM questions are
        # alternatives, not text to concatenate into the reply.
        question = collection_question(request, drafts=[q.model_dump() for q in result.output.questions])
        # Only ask for missing requirements; the API sends a separate full
        # trip summary once the collected request is ready.
        reply = question['question'] if question else ACKNOWLEDGEMENT
        return request, reply, None
    finally:
        close = getattr(harness.llm, 'aclose', None)
        if close:
            await close()
