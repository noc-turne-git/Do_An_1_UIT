"""Canonical destination gates. Model output cannot grant decision authority."""
import re
import unicodedata

from shared.contracts import DestinationResult, TripRequest
from shared.errors import ApplicationError

SUGGESTION_INTENTS = frozenset({'DELEGATE_SELECTION', 'ANY_DESTINATION', 'USER_UNKNOWN'})


def reject(message):
    raise ApplicationError('planning_input_inconsistent', message)


def normalized_text(value):
    text = unicodedata.normalize('NFKD', value.casefold()).replace('đ', 'd')
    return re.sub(r'\s+', ' ', ''.join(c for c in text if not unicodedata.combining(c))).strip()


def region_key(region):
    # Conversational identity survives optional province/country enrichment.
    return normalized_text(region.city)


def clear_region_fields(payload, fields):
    """Remove stale geography together with its answer/provenance metadata."""
    for field in fields:
        payload['destination'][field] = None
        for table in ('field_sources', 'field_confidences', 'field_decisions'):
            payload['meta'].get(table, {}).pop(f'destination.{field}', None)


def matches_region_constraints(destination, region):
    return all(not getattr(destination, field) or
               getattr(destination, field) == getattr(region, field)
               for field in ('province', 'country'))


def delegates_destination(raw, *, destination_context=True):
    """Check user language, never an LLM decision or selection_mode.

    Broad preferences such as 'ngân sách bao nhiêu cũng được' grant nothing.
    """
    text = normalized_text(raw or '')
    if re.search(r'\b(?:khong|dung|chua|chang)(?:\s+(?:muon|de|cho|ban|ai|tu))*\s+'
                 r'(?:chon|quyet dinh|chot)\b|\b(?:not|never|don.t)\s+(?:choose|pick|decide)\b', text):
        return False
    clause = r'(?:^|[,.!;]\s*)'
    ending = r'(?:[.!;,]|$)'
    requester = r'(?:(?:minh|toi|tui|em|anh|chi)\s+)?(?:(?:nho|de|giao|muon|cu de)\s+)?'
    courtesy = r'(?:\s+(?:di|nhe|nha|luon|giup|minh|toi|tui|em|anh|chi|ho|cho|thay|a|voi))*'
    scope = r'(?:\s+(?:diem den|dia diem|thanh pho|noi den|noi di))'
    if destination_context:
        scope += '?'
    patterns = [
        clause + requester + r'(?:ban|ai)\s+(?:tu\s+)?(?:chon|quyet dinh)'
        + scope + courtesy + ending,
        clause + r'(?:dau|noi nao|diem den nao|thanh pho nao)\s+cung duoc' + courtesy + ending,
        clause + r'(?:any destination|anywhere is fine)' + ending,
    ]
    if destination_context:
        patterns.extend([
            clause + r'(?:chon|quyet dinh)\s+(?:giup|ho)\s+(?:minh|toi|tui|em|anh|chi)' + courtesy + ending,
            clause + r'you (?:pick|choose|decide)' + ending,
        ])
    return bool(re.search('|'.join(patterns), text))


def can_select(destination, *, delegated_candidate_ids=()):
    destination.authority_is_explicit()
    return bool((destination.selection_intent == 'EXPLICIT'
                 and destination.selection_authority == 'USER'
                 and destination.city and destination.city.strip())
                or (destination.selection_intent == 'DELEGATE_SELECTION'
                    and destination.selection_authority == 'AGENT'
                    and delegated_candidate_ids))


def can_offer_choice(destination):
    return destination.selection_intent in SUGGESTION_INTENTS


def authorize_selection(request, result, *, user_choice=False, candidates=(),
                        delegated_candidate_ids=(), final=False):
    """Stamp the decision source only after validating CODE-owned evidence."""
    if final:
        reject('Question exhaustion never authorizes destination selection')
    result = DestinationResult.model_validate(result.model_dump()).require_canonical_recovery()
    destination = request.destination
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
        result.selected_candidate_id = None
        result.candidate_regions = []
        source, method = 'USER', 'USER_CHOICE' if user_choice else 'USER_EXPLICIT'
    elif can_select(destination, delegated_candidate_ids=delegated_candidate_ids):
        if not matches_region_constraints(destination, region):
            reject('Delegated destination violates the user geographic constraints')
        candidate = next((c for c in candidates
                          if c.candidate_id in delegated_candidate_ids and
                          all(not getattr(c, field) or getattr(c, field) == getattr(region, field)
                              for field in ('city', 'province', 'country'))), None)
        if candidate is None or result.selected_candidate_id not in {None, candidate.candidate_id}:
            reject('Delegation only authorizes a candidate from the issued list')
        result.selected_candidate_id = candidate.candidate_id
        source = method = 'AGENT_DELEGATED'
    else:
        reject('Destination selection requires a user choice or a subsequent delegation')
    return DestinationResult.model_validate(result.model_dump() | dict(
        destination_source=source, selection_method=method))


def apply_resolved_destination(request: TripRequest, result: DestinationResult) -> TripRequest:
    if result.selection_status != 'selected' or result.selected_region is None:
        reject('Only a selected destination can update TripRequest')
    data = request.model_dump()
    destination = data['destination']
    region = result.selected_region
    destination['city'] = region.city
    if result.selection_method != 'USER_EXPLICIT':
        destination.update(province=region.province, country=region.country)
    source = result.destination_source
    if source not in {'USER', 'AGENT_DELEGATED'}:
        reject('Selected result has no authorized destination source')
    destination.update(selection_authority='USER' if source == 'USER' else 'AGENT',
                       destination_source=source)
    data['meta']['field_sources']['destination.city'] = 'user' if source == 'USER' else 'inferred'
    if source == 'AGENT_DELEGATED':
        data['meta']['field_confidences']['destination.city'] = 1.0
    return TripRequest.model_validate(data)
