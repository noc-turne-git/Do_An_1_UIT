import json
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, ValidationError as SchemaError
from pydantic import ValidationError

from shared.contracts import (AnswerHistory, Destination, DestinationEpisode,
    DestinationResult, PendingQuestion, SelectionPolicy, WorkflowState)
from ai.orchestration.mock_workflow import fixture


def question(**overrides):
    data = dict(question_id=uuid4(), episode_id=uuid4(), status='open', round=2,
        kind='destination_choice', intent_snapshot='USER_UNKNOWN', question='Choose a region',
        fields=['destination.city'], options=[dict(option_id='o1', candidate_id='c1',
            city='Da Lat', rank=1, reason='Cool weather')])
    return PendingQuestion.model_validate(data | overrides)


def answer(q, **overrides):
    return AnswerHistory.model_validate(dict(answer_id=uuid4(), question_id=q.question_id,
        episode_id=q.episode_id, kind=q.kind, round=q.round, asked_fields=q.fields,
        question=q.question, answer_raw='o1', selected_option_id='o1',
        resolved_fields=q.fields, declared_unknown_fields=[]) | overrides)


def result():
    return DestinationResult(request_type='IMPLICIT', selected_region=None,
        selection_status='needs_user_choice', selection_reason='options', missing_fields=[],
        candidate_regions=[dict(city='Hue', candidate_id='c2', rank=2, reason='History'),
                           dict(city='Da Lat', candidate_id='c1', rank=1, reason='Cool')])


@pytest.mark.smoke
def test_legacy_does_not_grant_authority_or_actionability():
    for mode in ['implicit', 'explicit', 'ambiguous']:
        data = fixture('trip_request')['destination'] | dict(selection_mode=mode)
        for key in SelectionPolicy.model_fields:
            data.pop(key, None)
        dest = Destination.model_validate(data)
        assert (dest.selection_intent, dest.selection_authority) == ('UNSPECIFIED', None)
    q = PendingQuestion(question='Choose', fields=['destination.city'], kind='destination_choice')
    assert q.status == 'legacy'
    with pytest.raises(ValueError, match='not open'):
        q.require_actionable()
    with pytest.raises(ValidationError):
        question(options=[dict(option_id='old', city='Hue')])


@pytest.mark.parametrize('intent', ['USER_UNKNOWN', 'UNSPECIFIED', 'EXPLICIT'])
def test_agent_authority_not_inferred(intent):
    with pytest.raises(ValidationError):
        SelectionPolicy(selection_intent=intent, selection_authority='AGENT',
                        selection_provenance=dict(source='user', evidence='anywhere'))


def test_any_requires_exhausted_rounds_and_completed_final_resolve():
    with pytest.raises(ValidationError):
        SelectionPolicy(selection_intent='ANY', selection_authority='USER')
    episode = DestinationEpisode(episode_id=uuid4(), request_id=uuid4(),
        selection_intent='ANY_DESTINATION', selection_authority='USER',
        selection_provenance=dict(source='user', evidence='anywhere'))
    with pytest.raises(ValueError):
        episode.default_candidate()
    episode = DestinationEpisode.model_validate(episode.model_dump() | dict(
        final_resolve_status='completed', final_resolve_id=uuid4(), final_resolve_result=result()))
    with pytest.raises(ValueError):
        episode.default_candidate()
    with pytest.raises(ValueError):
        DestinationEpisode.model_validate(episode.model_dump() | dict(
            selection_intent='DELEGATE_SELECTION')).default_candidate()
    for intent in ['USER_UNKNOWN', 'UNSPECIFIED']:
        other = DestinationEpisode.model_validate(episode.model_dump() | dict(
            selection_intent=intent, selection_authority=('USER' if intent == 'USER_UNKNOWN' else None),
            destination_source=None, selection_provenance=None))
        with pytest.raises(ValueError):
            other.default_candidate()


def test_budget_identity_and_final_resolve_invariants():
    assert DestinationEpisode(episode_id=uuid4(), request_id=uuid4(),
        destination_round=12, max_destination_rounds=2).destination_round == 12
    for changes in [dict(destination_round=-1), dict(final_resolve_status='claimed'),
                    dict(final_resolve_status='completed', final_resolve_id=uuid4()),
                    dict(final_resolve_result=result())]:
        with pytest.raises(ValidationError):
            DestinationEpisode(episode_id=uuid4(), request_id=uuid4(), **changes)
    ep = DestinationEpisode(episode_id=uuid4(), request_id=uuid4(), destination_round=2)
    state = dict(request_id=ep.request_id, trip_id=uuid4(), status='clarifying',
        current_step='destination_agent', completed_steps=[], artifacts={}, clarification_round=0,
        destination_round=2, pending_fields=['destination.city'], retry_count=0, destination_episode=ep)
    assert WorkflowState(**state).destination_episode == ep
    with pytest.raises(ValidationError):
        WorkflowState(**(state | dict(destination_round=1)))
    with pytest.raises(ValidationError):
        WorkflowState(**(state | dict(request_id=uuid4())))


def test_second_question_can_answer_but_snapshot_and_option_must_match():
    q = question()
    assert answer(q).validate_for(q).round == 2
    for changes in [dict(episode_id=uuid4()), dict(question_id=uuid4()),
                    dict(selected_option_id='other'), dict(round=1),
                    dict(asked_fields=['budget.amount']), dict(resolved_fields=['trip.start_date'])]:
        with pytest.raises(ValueError):
            answer(q, **changes).validate_for(q)
    with pytest.raises(ValueError):
        answer(q).validate_for(question(**(q.model_dump() | dict(status='answered'))))


def test_duplicate_identity_and_ranking_rejected():
    q = question()
    with pytest.raises(ValidationError):
        question(options=[*q.options, q.options[0]])
    data = result().model_dump()
    data['candidate_regions'][1]['rank'] = 2
    with pytest.raises(ValidationError):
        DestinationResult.model_validate(data)
