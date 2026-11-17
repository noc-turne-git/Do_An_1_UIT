"""Canonical selection gates. Agent output cannot grant itself authority."""
from shared.contracts import DestinationResult, Region, TripRequest
from shared.errors import ApplicationError

ANY_INTENTS = {'ANY_DESTINATION'}


def reject(message):
    raise ApplicationError('planning_input_inconsistent', message)


def can_select(destination):
    destination.authority_is_explicit()
    return ((destination.selection_intent == 'EXPLICIT' and destination.selection_authority == 'USER'
             and bool(destination.city and destination.city.strip())) or
            (destination.selection_intent == 'DELEGATE_SELECTION'
             and destination.selection_authority == 'AGENT'))


def can_offer_choice(destination):
    """A candidate list is actionable only while the USER owns the choice."""
    return (destination.selection_intent in {'USER_UNKNOWN', 'ANY_DESTINATION'}
            and destination.selection_authority == 'USER')


def authorize_selection(request, result, *, final=False, user_choice=False):
    """Validate a concrete result and stamp its actual decision source."""
    result = DestinationResult.model_validate(result.model_dump()).require_canonical_recovery()
    destination = request.destination
    if final:
        if destination.selection_intent not in ANY_INTENTS or destination.selection_authority != 'USER':
            reject('Only exhausted ANY_DESTINATION may use SYSTEM_DEFAULT')
        if result.selection_status not in {'selected', 'needs_user_choice'} or result.missing_fields:
            reject('Final destination resolution remains unresolved')
        candidates = [c for c in result.candidate_regions
                      if c.rank == 1 and c.candidate_id and c.city.strip() and c.reason.strip()]
        if len(candidates) != 1:
            reject('Final destination resolution requires a unique valid rank 1')
        candidate = candidates[0]
        result = DestinationResult.model_validate(result.model_dump() | dict(
            selected_region=Region(city=candidate.city, province=candidate.province, country=candidate.country),
            selection_status='selected', selected_candidate_id=candidate.candidate_id,
            destination_source='SYSTEM_DEFAULT', selection_method='SYSTEM_DEFAULT'))
        return result
    if result.selection_status != 'selected' or result.missing_fields:
        reject('Destination has not been resolved')
    region = result.selected_region
    if not region.city.strip():
        reject('Destination resolver returned an empty city')
    if destination.selection_intent == 'EXPLICIT':
        for field in ('city', 'province', 'country'):
            expected = getattr(destination, field)
            if expected and getattr(region, field) != expected:
                reject('Validated destination differs from the explicit user destination')
        return DestinationResult.model_validate(result.model_dump() | dict(
            destination_source='user', selection_method='USER_CHOICE' if user_choice else 'USER_EXPLICIT'))
    if destination.selection_intent == 'DELEGATE_SELECTION' and destination.selection_authority == 'AGENT':
        return DestinationResult.model_validate(result.model_dump() | dict(
            destination_source='AGENT_DELEGATED', selection_method='AGENT_DELEGATED'))
    if user_choice and can_offer_choice(destination):
        return DestinationResult.model_validate(result.model_dump() | dict(
            destination_source='user', selection_method='USER_CHOICE'))
    reject('Destination selection requires the authority recorded in TripRequest')


def apply_resolved_destination(request: TripRequest, result: DestinationResult) -> TripRequest:
    """Persist a selected city, authority and source in TripRequest."""
    if result.selection_status != 'selected' or result.selected_region is None:
        reject('Only a selected destination can update TripRequest')
    data = request.model_dump()
    destination = data['destination']
    region = result.selected_region
    # EXPLICIT only freezes what the user supplied.  Resolver enrichment (for
    # example a province inferred from a city) stays on DestinationResult and
    # must not become a new user constraint on a later refresh.
    destination['city'] = region.city
    if result.selection_method != 'USER_EXPLICIT':
        destination.update(province=region.province, country=region.country)
    if result.destination_source == 'user':
        destination.update(selection_authority='USER', destination_source='user')
    elif result.destination_source == 'AGENT_DELEGATED':
        destination.update(selection_authority='AGENT', destination_source='AGENT_DELEGATED')
    elif result.destination_source == 'SYSTEM_DEFAULT':
        destination.update(selection_authority='SYSTEM', destination_source='SYSTEM_DEFAULT')
    else:
        reject('Selected result has no canonical destination source')
    if result.destination_source != 'user':
        data['meta']['field_sources']['destination.city'] = 'inferred'
        data['meta']['field_confidences']['destination.city'] = 1.0
    return TripRequest.model_validate(data)
