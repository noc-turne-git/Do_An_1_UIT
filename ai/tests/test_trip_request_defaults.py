import pytest

from ai.orchestration.clarification_policy import ClarificationPolicy
from ai.orchestration.clarification_questions import QuestionSpec
from ai.orchestration.trip_request_defaults import apply_trip_defaults
from ai.orchestration.mock_workflow import fixture
from shared.contracts import TripRequest
from shared.errors import ApplicationError
from test_graph_workflow import workflow, execute


def policy():
    return ClarificationPolicy(max_clarification_rounds=1, preference_defaults=dict(
        approved_by='test-owner', interests=['history'], pace='relaxed', transport_modes=['walk']))


def request():
    data = fixture('trip_request')
    data['travelers']['children'] = None
    data['preferences'] = dict(interests=None, pace=None, transport_modes=None)
    data['budget']['amount'] = None
    return TripRequest.model_validate(data)


def apply(value, specs, **kwargs):
    return apply_trip_defaults(value, specs, policy=policy(), exhausted=True,
                              question_open=False, **kwargs)


def test_defaults_are_scoped_and_preserve_constraints_and_unknown_money():
    value = request()
    spec = QuestionSpec('trip_request', ('travelers.children', 'budget.amount',
        'preferences.interests', 'preferences.pace', 'preferences.transport_modes', 'trip.start_date'))
    result = apply(value, [spec])
    assert result.travelers.children == 0 and result.preferences.pace == 'relaxed'
    assert result.budget.amount is None
    assert result.meta.field_sources.get('budget.amount') != 'default'
    assert result.trip == value.trip and result.additional_constraints == value.additional_constraints
    assert result.meta.field_sources['preferences.pace'] == 'default'
    assert value.preferences.pace is None
    assert apply(value, [QuestionSpec('destination_info', spec.fields)]) == value


@pytest.mark.parametrize('exhausted,open_question', [(False, False), (True, True)])
def test_last_question_must_be_processed_before_defaults(exhausted, open_question):
    value = request()
    assert apply_trip_defaults(value, [QuestionSpec('trip_request', ('travelers.children',))],
        policy=policy(), exhausted=exhausted, question_open=open_question) == value


@pytest.mark.parametrize('path', ['trip.start_date', 'trip.end_date', 'travelers.adults'])
def test_never_default_fails_safely(path):
    data = request().model_dump()
    group, key = path.split('.')
    data[group][key] = None
    with pytest.raises(ApplicationError, match='Required trip information'):
        apply(TripRequest.model_validate(data), [QuestionSpec('trip_request', (path,))])
