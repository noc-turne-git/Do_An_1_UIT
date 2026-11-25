"""Bind parser-confirmed answers to the issued question and preserve constraints."""
from copy import deepcopy
from uuid import uuid4
import re

from shared.contracts import AnswerHistory, TRIP_COLLECTION_FIELDS, TripRequest


class InvalidAnswer(ValueError):
    """An unaccepted response leaves the issued question open."""


def selected_option(raw, question):
    """Exact IDs, ranks and city names need no model interpretation."""
    from ai.orchestration.destination_resolution import normalized_text
    if question is None or question.kind != 'destination_choice':
        return None
    raw = (raw or '').strip()
    direct = next((o.option_id for o in question.options if o.option_id == raw), None)
    if direct:
        return direct
    text = normalized_text(raw).strip(' .!')
    rank = re.fullmatch(r'(?:(?:minh |toi )?chon )?(?:so |phuong an |lua chon )?(\d+)', text)
    matches = [o for o in question.options if (rank and o.rank == int(rank[1]))
               or text == normalized_text(o.city)]
    return matches[0].option_id if len(matches) == 1 else None


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
    # Once chosen, the candidate becomes an exact user constraint to verify.
    data['destination'].update(city=option.city, province=option.province, country=option.country,
        selection_intent='EXPLICIT', selection_mode='explicit',
        selection_authority='USER', destination_source='USER',
        selection_provenance=dict(source='user', evidence='Selected option ' + option.option_id,
            episode_id=question.episode_id, question_id=question.question_id))
    data['meta']['field_sources'].update({'destination.city': 'user', 'destination.selection_mode': 'user'})
    data['meta']['field_decisions'].update({'destination.city': 'SPECIFIED', 'destination.selection_mode': 'SPECIFIED'})
    return TripRequest.model_validate(data)


def accept_answer(previous, parsed, question, raw, supplied=None, *, destination_action='none',
                  user_changed_fields=()):
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
    # A direct user edit can refine a suggestion without accepting a proposal
    # invented by the agent. A specific active proposal still needs confirmation.
    changed = any(before[group] != data[group] for group in (
        'trip', 'travelers', 'budget', 'preferences', 'daily_preferences', 'must_do',
        'additional_constraints'))
    if question.kind == 'destination_choice' and destination_action == 'none' and changed:
        destination_action = 'refine'
    proposal = question.constraint_proposal
    confirmed = supplied.constraint_confirmed if supplied else None
    if proposal:
        if supplied is None or supplied.confirmed_proposal_id != proposal.proposal_id or confirmed is None:
            raise InvalidAnswer('Explicit confirmation of the specific proposal is required')
        for path in proposal.fields:
            if read_path(before, path) != proposal.current_values[path]:
                raise InvalidAnswer('Constraint proposal is stale')
            if path in {'meta', 'destination'} or path.startswith((
                    'meta.', 'destination.selection_', 'destination.destination_source')):
                raise InvalidAnswer('Proposal cannot change authority or provenance')
            value = proposal.proposed_values[path] if confirmed else proposal.current_values[path]
            write_path(data, path, value)
            if confirmed:
                data['meta']['field_sources'][path] = 'user'
                data['meta']['field_confidences'].pop(path, None)
            if path in TRIP_COLLECTION_FIELDS:
                if confirmed:
                    data['meta']['field_decisions'][path] = 'DECLINED' if value is None else 'SPECIFIED'
                else:
                    for key in ('field_decisions', 'field_sources', 'field_confidences'):
                        data['meta'][key].pop(path, None)
                        if path in before['meta'].get(key, {}):
                            data['meta'][key][path] = before['meta'][key][path]
    if supplied:
        for path in supplied.declared_unknown_fields:
            if path in TRIP_COLLECTION_FIELDS:
                write_path(data, path, None)
                data['meta']['field_decisions'][path] = 'DECLINED'
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
                proposal and confirmed and path in proposal.fields) and not (
                any(changed_path == path or changed_path.startswith(path + '.')
                    for changed_path in user_changed_fields)) and not (
                question.kind in {'trip_request', 'destination_info', 'destination_choice'}
                and path in TRIP_COLLECTION_FIELDS
                and data['meta']['field_sources'].get(path) == 'user'
                and data['meta']['field_decisions'].get(path) in {'DECLINED', 'SPECIFIED'}) and not (
                path == 'trip.duration_days'
                and data['meta']['field_sources'].get(path) == 'inferred'
                and any(read_path(before, date_path) != read_path(data, date_path)
                        for date_path in ('trip.start_date', 'trip.end_date'))):
            raise InvalidAnswer('Changing an existing constraint requires the specific confirmed proposal')
    parsed = TripRequest.model_validate(data)
    resolved, unknown = [], []
    for path in question.fields:
        try:
            value = read_path(data, path)
        except (KeyError, TypeError, IndexError, ValueError):
            continue
        if path in TRIP_COLLECTION_FIELDS:
            if parsed.meta.field_decisions[path] == 'SPECIFIED':
                resolved.append(path)
            elif parsed.meta.field_decisions[path] == 'DECLINED':
                unknown.append(path)
        elif value is not None and value != '':
            resolved.append(path)
        elif (parsed.meta.field_decisions.get(path) in {'UNKNOWN', 'FLEXIBLE', 'AI_DECIDE', 'NO_PREFERENCE', 'DEFERRED'}
              or supplied and path in supplied.declared_unknown_fields
              or path == 'destination.city' and parsed.destination.selection_intent == 'USER_UNKNOWN'):
            unknown.append(path)
    update = None
    if question.kind == 'destination_choice' and not selected:
        d = parsed.destination
        if d != previous.destination and (
                d.selection_authority in {'USER', 'AGENT', 'SYSTEM'} or d.selection_intent == 'USER_UNKNOWN'):
            update = d
        elif 'destination.city' not in unknown and destination_action == 'none':
            raise InvalidAnswer('Response is neither an option nor a parser-confirmed destination update')
    answer = AnswerHistory(round=question.round, kind=question.kind,
        asked_fields=question.fields, question=question.question, answer_raw=raw,
        resolved_fields=resolved, declared_unknown_fields=unknown,
        answer_id=supplied.answer_id if supplied else uuid4(),
        episode_id=question.episode_id, question_id=question.question_id,
        selected_option_id=selected, destination_update=update, destination_action=destination_action,
        confirmed_proposal_id=supplied.confirmed_proposal_id if supplied else None,
        constraint_confirmed=confirmed)
    answer.validate_for(question)
    if parsed.destination.selection_authority is not None and any(
            path.startswith('destination.') for path in question.fields):
        data = parsed.model_dump()
        provenance = data['destination']['selection_provenance'] or dict(source='user', evidence=raw)
        provenance.update(episode_id=question.episode_id, question_id=question.question_id)
        data['destination']['selection_provenance'] = provenance
        parsed = TripRequest.model_validate(data)
    return parsed, answer
