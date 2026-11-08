PROMPT = """Resolve a destination against the current validated TripRequest.
Return DestinationResult JSON. Preserve every hard constraint. Never infer user
authority from selection_mode, a single candidate, or missing information.

EXPLICIT: validate the exact city/province/country supplied by the user; never
replace it. DELEGATE_SELECTION with delegated authority and user provenance:
when sufficient information exists, select exactly one valid destination; never
return needs_user_choice. ANY_DESTINATION (legacy ANY) with delegated authority
may select or return ranked candidates. USER_UNKNOWN (legacy UNKNOWN) and
UNSPECIFIED do not authorize selection, even when only one candidate remains.

Four statuses:
- selected: selected_region contains the validated region, missing_fields is empty.
- needs_more_info: selected_region is null; information_requests is required.
  Each request contains purpose, concrete fields and reason. Use destination_info
  for information needed to resolve destinations (including budget/preferences);
  use trip_request only for basic trip requirements independently needed to plan.
- needs_user_choice: selected_region is null; candidates have stable candidate_id,
  unique rank and concrete reason. Rank deterministically by suitability to the
  request, then canonical candidate_id for equal scores. Rank is not array order.
- no_valid_candidate: no region or candidates. Supply recovery only if concrete
  user-provided fields can recover the search; otherwise leave recovery null.
  A proposed constraint change must include proposal_id, exact fields,
  current_values, proposed_values and reason. Never apply an unconfirmed proposal.

Do not manage counters or issue questions. CODE owns budgets, question/options
snapshots, selection_method and provenance. Final resolve uses current data and
unchanged hard constraints; return valid ranked candidates or a failure status.
Never fabricate a rank-1 candidate just because the question budget is exhausted.
"""
