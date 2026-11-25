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
        Change(path=f'trip.{name}', value_json=json.dumps(value),
               decision='UNKNOWN' if value is None else 'SPECIFIED')
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


def test_no_year_uses_next_occurrence_and_ambiguous_input_is_pending():
    source = empty_request()
    normalized = normalize_trip_dates(source, {'trip.start_date': '14/11',
        'trip.duration_days': 3}, current_date=TODAY)
    assert normalized.start_date == date(2026, 11, 14)
    assert normalized.end_date == date(2026, 11, 16)
    next_year = normalize_trip_dates(source, {'trip.start_date': '14/11',
        'trip.duration_days': 3}, current_date=date(2026, 11, 20))
    assert next_year.start_date == date(2027, 11, 14)


def test_unknown_date_clears_value_without_rederiving():
    source = previous()
    result = edit(source, start_date=None)
    assert result.trip.start_date is None
    assert result.trip.end_date == source.trip.end_date
    assert 'trip.start_date' not in result.missing_fields
