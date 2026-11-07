"""Date arithmetic and parser integration; no workflow question issuance."""
from copy import deepcopy
from datetime import date
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ai.orchestration.date_normalization import normalize_trip_dates
from ai.orchestration.mock_workflow import fixture
from ai.orchestration.request_parser import Change, ParserOutput, apply_changes, empty_request
from shared.contracts import TripRequest, WorkflowState


TODAY = date(2026, 11, 8)


def previous():
    return TripRequest.model_validate(fixture('trip_request'))


def edit(source, **values):
    return apply_changes(source, ParserOutput(summary='Updated', changes=[
        Change(path=f'trip.{name}', value_json=json.dumps(value), decision='SPECIFIED')
        for name, value in values.items()]), current_date=TODAY)


def test_explicit_end_date_is_preserved_and_duration_recomputed():
    source = previous()
    before = source.model_dump(mode='json')
    result = edit(source, end_date='2026-11-18')
    assert result.trip.start_date == date(2026, 11, 14)
    assert result.trip.end_date == date(2026, 11, 18)
    assert result.trip.duration_days == 5
    assert result.meta.field_sources['trip.end_date'] == 'user'
    assert result.meta.field_sources['trip.duration_days'] == 'inferred'
    assert result.meta.field_confidences['trip.duration_days'] == 1.0
    assert source.model_dump(mode='json') == before


def test_updated_old_start_date_preserves_valid_end_date():
    result = edit(previous(), start_date='2026-11-15')
    assert (result.trip.start_date, result.trip.end_date, result.trip.duration_days) == (
        date(2026, 11, 15), date(2026, 11, 16), 2)


def test_new_start_after_stale_derived_end_shifts_end_using_prior_duration():
    source = previous()  # fixture end date has no user provenance
    result = edit(source, start_date='2026-11-18')
    assert result.trip.end_date == date(2026, 11, 20)
    assert result.trip.duration_days == 3
    assert result.meta.field_sources['trip.end_date'] == 'inferred'


def test_stale_but_user_provided_end_date_is_not_discarded():
    source = previous()
    source.meta.field_sources['trip.end_date'] = 'user'
    result = normalize_trip_dates(source, {'trip.start_date': '2026-11-15'}, current_date=TODAY)
    assert result.end_date == date(2026, 11, 16) and result.duration_days == 2
    conflict = normalize_trip_dates(source, {'trip.duration_days': 4}, current_date=TODAY)
    assert conflict.conflicting and conflict.end_date == date(2026, 11, 16)
    with pytest.raises(ValidationError):
        edit(source, duration_days=4)


def test_explicit_end_and_duration_can_derive_start_without_losing_end():
    result = edit(previous(), end_date='2026-11-18', duration_days=3)
    assert (result.trip.start_date, result.trip.end_date, result.trip.duration_days) == (
        date(2026, 11, 16), date(2026, 11, 18), 3)
    assert result.meta.field_sources['trip.start_date'] == 'inferred'


def test_start_duration_and_end_are_synchronized():
    source = previous()
    result = edit(source, start_date='2026-11-20', duration_days=4)
    assert result.trip.end_date == date(2026, 11, 23)
    assert result.trip.duration_days == 4
    three = edit(source, start_date='2026-11-20', end_date='2026-11-23', duration_days=4)
    assert three.trip == result.trip
    disagree = normalize_trip_dates(source, {'trip.start_date': '2026-11-20',
        'trip.end_date': '2026-11-22', 'trip.duration_days': 4}, current_date=TODAY)
    assert disagree.conflicting and disagree.issues[0].reason == 'conflicting'
    with pytest.raises(ValidationError):
        edit(source, start_date='2026-11-20', end_date='2026-11-22', duration_days=4)


def test_distinguish_missing_ambiguous_conflicting_without_question_kind():
    blank = normalize_trip_dates(empty_request(), {}, current_date=TODAY)
    assert {issue.reason for issue in blank.issues} == {'missing'}
    ambiguous = normalize_trip_dates(previous(), {'trip.start_date': 'next weekend'}, current_date=TODAY)
    assert ambiguous.start_date is None and ambiguous.issues[0].reason == 'ambiguous'
    corrected = normalize_trip_dates(previous(), {'trip.end_date': '2026-11-10'}, current_date=TODAY)
    assert corrected.conflicting and corrected.issues[0].reason == 'conflicting'
    assert not any(hasattr(item, 'kind') for item in blank.issues + ambiguous.issues + corrected.issues)


def test_no_year_uses_next_occurrence_and_ambiguous_input_is_pending():
    source = empty_request()
    normalized = normalize_trip_dates(source, {'trip.start_date': '14/11',
        'trip.duration_days': 3}, current_date=TODAY)
    assert normalized.start_date == date(2026, 11, 14)
    assert normalized.end_date == date(2026, 11, 16)
    next_year = normalize_trip_dates(source, {'trip.start_date': '14/11',
        'trip.duration_days': 3}, current_date=date(2026, 11, 20))
    assert next_year.start_date == date(2027, 11, 14)
    pending = edit(previous(), start_date='next week')
    assert pending.trip.start_date is None and pending.trip.end_date == date(2026, 11, 16)
    assert pending.meta.field_decisions['trip.start_date'] == 'UNKNOWN'
    assert 'trip.start_date' in pending.missing_fields


def test_null_date_is_not_recreated_from_old_end_and_duration():
    source = previous()
    result = edit(source, start_date=None)
    assert result.trip.start_date is None
    assert result.trip.end_date == source.trip.end_date
    assert 'trip.start_date' in result.missing_fields


def test_normalization_never_touches_workflow_counters_or_issues_questions():
    state = WorkflowState(request_id=uuid4(), trip_id=uuid4(), status='clarifying',
        current_step='request_parser', completed_steps=[], artifacts={},
        clarification_round=2, destination_round=1,
        pending_fields=['trip.end_date'], retry_count=0)
    snapshot = deepcopy(state.model_dump(mode='json'))
    normalized = normalize_trip_dates(previous(), {'trip.end_date': '2026-11-18'}, current_date=TODAY)
    assert not normalized.unresolved and normalized.duration_days == 5
    assert state.model_dump(mode='json') == snapshot
    assert set(normalized.__dataclass_fields__) == {
        'start_date', 'end_date', 'duration_days', 'issues', 'derived_fields'}
