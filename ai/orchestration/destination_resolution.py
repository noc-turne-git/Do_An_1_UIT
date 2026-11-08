"""Canonical selection gates. Agent output cannot grant itself authority."""
from shared.contracts import DestinationResult, SelectionProvenance, Region
from shared.errors import ApplicationError

ANY_INTENTS = {'ANY', 'ANY_DESTINATION'}
DELEGATED_INTENTS = ANY_INTENTS | {'DELEGATE_SELECTION'}


def reject(message):
    raise ApplicationError('planning_input_inconsistent', message)


def can_select(destination):
    destination.authority_is_explicit()
    return ((destination.selection_intent == 'EXPLICIT' and destination.selection_authority == 'user'
             and bool(destination.city and destination.city.strip())) or
            (destination.selection_intent in DELEGATED_INTENTS
             and destination.selection_authority == 'delegated'))


def authorize_selection(request, result, *, final=False, user_choice=False):
    """Normalize provenance after the resolver has validated a concrete region."""
    result = DestinationResult.model_validate(result.model_dump()).require_canonical_recovery()
    destination = request.destination
    if not can_select(destination):
        reject('Destination selection requires explicit user authority or delegation')
    if final:
        if destination.selection_intent not in ANY_INTENTS:
            reject('Only ANY may use final destination resolution')
        if result.selection_status not in {'selected', 'needs_user_choice'} or result.missing_fields:
            reject('Final destination resolution remains unresolved')
        candidates = [c for c in result.candidate_regions
                      if c.rank == 1 and c.candidate_id and c.city.strip() and c.reason.strip()]
        if len(candidates) != 1:
            reject('Final destination resolution requires a unique valid rank 1')
        candidate = candidates[0]
        result = DestinationResult.model_validate(result.model_dump() | dict(
            selected_region=Region(city=candidate.city, province=candidate.province, country=candidate.country),
            selection_status='selected', selected_candidate_id=candidate.candidate_id))
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
        source, method = 'user', 'USER_CHOICE' if user_choice else 'USER_EXPLICIT'
    else:
        source, method = 'default', 'ANY_DEFAULT' if final else 'DELEGATED'
    provenance = destination.selection_provenance.model_dump()
    provenance['source'] = source
    return DestinationResult.model_validate(result.model_dump() | dict(
        selection_provenance=SelectionProvenance(**provenance), selection_method=method))
