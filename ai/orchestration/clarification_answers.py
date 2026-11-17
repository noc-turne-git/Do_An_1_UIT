"""Bind parser-confirmed answers to the issued question and preserve constraints."""
from copy import deepcopy
from uuid import uuid4

from shared.contracts import AnswerHistory, TripRequest


class InvalidAnswer(ValueError):
    """An unaccepted response leaves the issued question open."""


def read_path(data, path):
    for part in path.split('.'):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def write_path(data, path, value):
    parts = path.split('.')
    node = data
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    node[int(parts[-1]) if isinstance(node, list) else parts[-1]] = deepcopy(value)


def option_request(request, question, selected):
    option = next((o for o in question.options if o.option_id == selected), None)
    if option is None:
        raise InvalidAnswer('Option does not belong to the issued snapshot')
    data = request.model_dump()
    # Choosing an issued option is a USER decision, not evidence that the
    # episode's intent has become EXPLICIT.  The intent remains USER_UNKNOWN or
    # ANY_DESTINATION while the source records this actual selection.
    data['destination'].update(city=option.city, province=option.province, country=option.country,
        selection_authority='USER', destination_source='user',
        selection_provenance=dict(source='user', evidence='Selected option ' + option.option_id,
            episode_id=question.episode_id, question_id=question.question_id))
    data['meta']['field_sources'].update({'destination.city': 'user', 'destination.selection_mode': 'user'})
    return TripRequest.model_validate(data)


def accept_answer(previous, parsed, question, raw, supplied=None):
    question.require_actionable()
    selected = supplied.selected_option_id if supplied else (
        raw.strip() if question.kind == 'destination_choice'
        and raw.strip() in {o.option_id for o in question.options} else None)
    if selected:
        if supplied is None:
            raise InvalidAnswer('Option response requires the exact issued question identity')
        parsed = option_request(parsed, question, selected)
        # The resolver subsequently validates this exact option region.
    before, data = previous.model_dump(mode='json'), parsed.model_dump(mode='json')
    proposal = question.constraint_proposal
    confirmed = supplied.constraint_confirmed if supplied else None
    if proposal:
        if supplied is None or supplied.confirmed_proposal_id != proposal.proposal_id or confirmed is None:
            raise InvalidAnswer('Explicit confirmation of the specific proposal is required')
        for path in proposal.fields:
            if read_path(before, path) != proposal.current_values[path]:
                raise InvalidAnswer('Constraint proposal is stale')
            if path.startswith(('meta.', 'destination.selection_')):
                raise InvalidAnswer('Proposal cannot change authority or provenance')
            value = proposal.proposed_values[path] if confirmed else proposal.current_values[path]
            write_path(data, path, value)
            if confirmed:
                data['meta']['field_sources'][path] = 'user'
                data['meta']['field_confidences'].pop(path, None)
    protected = ['trip.start_date', 'trip.end_date', 'trip.duration_days', 'trip.arrival',
        'trip.departure', 'travelers.adults', 'travelers.children', 'destination.must_visit',
        'destination.avoid_places', 'must_do', 'additional_constraints', 'daily_preferences',
        'budget.amount', 'budget.currency', 'budget.scope', 'budget.includes', 'budget.excludes',
        'budget.flexibility', 'budget.max_overrun_percent']
    for path in protected:
        old = read_path(before, path)
        if old is not None and old != read_path(data, path) and not (
                proposal and confirmed and path in proposal.fields):
            raise InvalidAnswer('Changing an existing constraint requires the specific confirmed proposal')
    parsed = TripRequest.model_validate(data)
    resolved, unknown = [], []
    for path in question.fields:
        try:
            value = read_path(data, path)
        except (KeyError, TypeError, IndexError, ValueError):
            continue
        if value is not None and value != '':
            resolved.append(path)
        elif (parsed.meta.field_decisions.get(path) in {'UNKNOWN', 'FLEXIBLE', 'AI_DECIDE', 'NO_PREFERENCE'}
              or supplied and path in supplied.declared_unknown_fields
              or path == 'destination.city' and parsed.destination.selection_intent == 'USER_UNKNOWN'):
            unknown.append(path)
    update = None
    if question.kind == 'destination_choice' and not selected:
        d = parsed.destination
        if d != previous.destination and (
                d.selection_authority in {'USER', 'AGENT', 'SYSTEM'} or d.selection_intent == 'USER_UNKNOWN'):
            update = d
        elif 'destination.city' not in unknown:
            raise InvalidAnswer('Response is neither an option nor a parser-confirmed destination update')
    answer = AnswerHistory(round=question.round, kind=question.kind,
        asked_fields=question.fields, question=question.question, answer_raw=raw,
        resolved_fields=resolved, declared_unknown_fields=unknown,
        answer_id=supplied.answer_id if supplied else uuid4(),
        episode_id=question.episode_id, question_id=question.question_id,
        selected_option_id=selected, destination_update=update,
        confirmed_proposal_id=supplied.confirmed_proposal_id if supplied else None,
        constraint_confirmed=confirmed)
    answer.validate_for(question)
    if parsed.destination.selection_authority is not None and any(
            path.startswith('destination.') for path in question.fields):
        data = parsed.model_dump()
        provenance = data['destination']['selection_provenance']
        provenance.update(episode_id=question.episode_id, question_id=question.question_id)
        parsed = TripRequest.model_validate(data)
    return parsed, answer
