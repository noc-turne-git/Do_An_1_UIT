"""Test-only requests with explicit user provenance for populated fields."""

from ai.orchestration.mock_workflow import fixture
from shared.contracts import TRIP_COLLECTION_FIELDS


def confirmed_trip_request():
    data = fixture('trip_request')
    decisions = data['meta'].setdefault('field_decisions', {})
    sources = data['meta'].setdefault('field_sources', {})
    for path in TRIP_COLLECTION_FIELDS:
        group, field = path.split('.')
        if data[group].get(field) is not None:
            decisions[path] = 'SPECIFIED'
            sources.setdefault(path, 'user')
    return data
