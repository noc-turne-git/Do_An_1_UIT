import pytest
from pydantic import ValidationError

from ai.config import AISettings
from ai.interface import get_clarification_policy, build_orchestrator
from ai.orchestration.clarification_policy import (
    ClarificationPolicy, NEVER_DEFAULT, PREFERENCE_FIELDS, TRIP_NEVER_DEFAULT,
    DESTINATION_NEVER_DEFAULT,
)


def approved():
    # Test configuration only, not a production recommendation/default table.
    return dict(approved_by='test-owner', interests=['history'], pace='slow', transport_modes=['walk'])


def test_default_policy_is_incomplete_without_owner_preferences():
    policy = get_clarification_policy(AISettings(_env_file=None))
    assert policy.max_clarification_rounds == 10 and policy.max_destination_rounds == 10
    assert policy.unconfigured_defaults == PREFERENCE_FIELDS
    assert policy.default_table == {'travelers.children': 0}
    assert not NEVER_DEFAULT.intersection(policy.default_table)
    assert TRIP_NEVER_DEFAULT == {'trip.start_date', 'trip.end_date', 'travelers.adults'}
    assert DESTINATION_NEVER_DEFAULT == {'destination.city'}


@pytest.mark.parametrize('kind,counter,limit', [
    ('trip_request', 'clarification_round', 3),
    ('destination_choice', 'destination_round', 10),
    ('destination_info', 'destination_round', 10),
])
def test_question_purpose_owns_counter(kind, counter, limit):
    assert ClarificationPolicy.counter_for(kind) == counter
    assert ClarificationPolicy().limit_for(kind) == limit


@pytest.mark.parametrize('value', [-1, 2.5])
def test_wrong_destination_budget_is_rejected(value):
    with pytest.raises(ValidationError):
        ClarificationPolicy(max_destination_rounds=value)
    with pytest.raises(ValidationError):
        AISettings(_env_file=None, max_destination_rounds=value)


@pytest.mark.parametrize('path', ['trip.start_date', 'destination.city'])
def test_never_default_and_destination_cannot_enter_table(path):
    with pytest.raises(ValidationError):
        ClarificationPolicy(trip_request_defaults={path: None})


@pytest.mark.parametrize('preferences', [
    {'pace': 'slow'}, approved() | {'approved_by': ''},
])
def test_preferences_require_complete_owner_configuration(preferences):
    with pytest.raises(ValidationError):
        AISettings(_env_file=None, clarification_preference_defaults=preferences)


def test_backend_env_inheritance_and_production_factory_wiring(monkeypatch):
    import json
    from app.core.config import Settings
    monkeypatch.setenv('GRAPH_MAX_CLARIFICATIONS', '4')
    monkeypatch.setenv('MAX_DESTINATION_ROUNDS', '2')
    monkeypatch.setenv('CLARIFICATION_PREFERENCE_DEFAULTS', json.dumps(approved()))
    settings = Settings(_env_file=None)
    policy = get_clarification_policy(settings)
    assert policy.max_clarification_rounds == 4
    assert policy.default_table['preferences.pace'] == 'slow'
    graph = build_orchestrator(settings)
    assert graph.clarification_policy == policy
    assert graph.limits.max_clarifications == policy.max_clarification_rounds
    for runtime in (False, True):
        settings.agent_runtime_enabled = runtime
        assert build_orchestrator(settings, clarification_policy=policy).clarification_policy is policy
    monkeypatch.setenv('MAX_DESTINATION_ROUNDS', '20')
    assert Settings(_env_file=None).build_clarification_policy().max_destination_rounds == 20
