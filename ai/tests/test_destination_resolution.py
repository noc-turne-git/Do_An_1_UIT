"""Canonical graph branches with issued identities and durable-store restart simulation."""
from itertools import product
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from ai.orchestration.clarification_answers import InvalidAnswer
from ai.orchestration.clarification_questions import attach_identity
from ai.orchestration.graph_workflow import GraphRun
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.workflow_state import StateMachine
from shared.contracts import AnswerHistory, DestinationEpisode, DestinationResult, SelectionPolicy, TripRequest
from test_graph_workflow import execute, workflow
from support import confirmed_trip_request


class Store:
    """Models canonical issuance/answering; no fake counters in graph tests."""
    def __init__(self):
        self.episode = None
        self.questions = []
        self.answers = []
        self.checkpoint = None
        self.claims = 0

    def save(self, *args):
        pass

    def sync(self, run):
        pass

    def save_graph(self, run):
        self.checkpoint = run.model_dump(mode='json')

    def issue_question(self, run, draft, request, *, question_id=None):
        assert not self.questions
        if self.episode is None:
            self.episode = DestinationEpisode(episode_id=uuid4(), request_id=run.state.request_id,
                **request.destination.model_dump(include=set(SelectionPolicy.model_fields)))
        destination = draft.kind != 'trip_request'
        counter = self.episode.destination_round if destination else run.state.clarification_round
        limit = self.episode.max_destination_rounds if destination else run.state.max_clarification_rounds
        assert counter < limit
        issued = attach_identity(draft, question_id=question_id or uuid4(),
            episode_id=self.episode.episode_id, round=counter + 1,
            intent_snapshot=self.episode.selection_intent)
        if destination:
            self.episode = self.episode.model_copy(update={'destination_round': counter + 1})
        self.questions = [issued]
        return issued, self.episode, run.state.clarification_round if destination else counter + 1

    def answer_question(self, run, answer):
        answer.validate_for(self.questions[0])
        self.answers.append(answer)
        self.questions = []

    def update_episode_policy(self, run, policy):
        assert not self.questions
        self.episode = DestinationEpisode.model_validate(self.episode.model_dump() | policy.model_dump())
        return self.episode

    def refresh_episode(self, run):
        return self.episode

    def claim_final_resolve(self, run, operation):
        assert not self.questions and self.episode.destination_round == 2
        if self.episode.final_resolve_status != 'not_started':
            return self.episode, False
        self.claims += 1
        self.episode = self.episode.model_copy(update={'final_resolve_status': 'claimed', 'final_resolve_id': operation})
        StateMachine(run).update(destination_episode=self.episode)
        self.save_graph(run)
        return self.episode, True

    def complete_final_resolve(self, run, operation, result):
        assert self.episode.final_resolve_id == operation
        self.episode = self.episode.model_copy(update={
            'final_resolve_status': 'completed', 'final_resolve_result': result})
        StateMachine(run).update(destination_episode=self.episode)
        self.save_graph(run)
        return self.episode


def request(intent='ANY_DESTINATION'):
    data = confirmed_trip_request()
    authority = {'EXPLICIT': 'USER', 'USER_UNKNOWN': 'USER',
                 'ANY_DESTINATION': 'USER', 'DELEGATE_SELECTION': 'AGENT'}.get(intent)
    source = 'user' if intent == 'EXPLICIT' else None
    data['destination'].update(selection_intent=intent, selection_authority=authority,
        destination_source=source,
        selection_provenance=dict(source='user', evidence='User intent: ' + intent) if authority else None,
        selection_mode='explicit' if intent == 'EXPLICIT' else 'implicit',
        city=data['destination']['city'] if intent == 'EXPLICIT' else None,
        province=None, country=None)
    return data


def result(status='needs_user_choice', *, recovery=False, purpose='destination_info'):
    data = fixture('destination_result')
    data.update(selection_status=status, selected_region=None, missing_fields=[],
        candidate_regions=[], information_requests=[], recovery=None)
    if status in {'selected', 'needs_user_choice'}:
        region = fixture('destination_result')['selected_region']
        data['candidate_regions'] = [dict(city='Hue', candidate_id='hue', rank=2, reason='History'),
                                    dict(**region, candidate_id='dalat', rank=1, reason='Weather')]
        if status == 'selected':
            data['selected_region'] = region
    if status == 'needs_more_info':
        data['information_requests'] = [dict(purpose=purpose, fields=['destination.preferred_areas'], reason='Search area')]
    if status == 'no_valid_candidate' and recovery:
        data['recovery'] = dict(fields=['destination.preferred_areas'], reason='Search area')
    return DestinationResult.model_validate(data)


def setup(results, intent='ANY_DESTINATION'):
    store = Store()
    components = mock_components()
    components.destination_agent.select = AsyncMock(side_effect=results)
    return workflow(components, persistence=store), store, components, request(intent)


def answer(run, **changes):
    q = run.pending_questions[0]
    return AnswerHistory(**(dict(answer_id=uuid4(), episode_id=q.episode_id,
        question_id=q.question_id, round=q.round, kind=q.kind, asked_fields=q.fields,
        question=q.question, answer_raw='Still undecided', resolved_fields=[],
        declared_unknown_fields=['destination.city'] if q.kind == 'destination_choice' else []) | changes))


@pytest.mark.parametrize('intent,status', [
    ('EXPLICIT', 'selected'), ('ANY_DESTINATION', 'selected'),
    ('DELEGATE_SELECTION', 'selected'), ('USER_UNKNOWN', 'needs_user_choice'),
    ('UNSPECIFIED', 'needs_more_info'), ('ANY_DESTINATION', 'no_valid_candidate'),
])
def test_intent_status_matrix(intent, status):
    graph, store, components, data = setup([result(status)], intent)
    run = execute(graph, data)
    if status == 'no_valid_candidate':
        assert run.state.status == 'awaiting_relaxation'
        assert not run.pending_questions
    elif status == 'selected' and intent == 'EXPLICIT':
        assert run.state.status == 'completed', run.errors
        assert run.state.destination_round == run.state.clarification_round == 0
        selected = run.outputs['destination_agent']
        assert selected.selection_method == 'USER_EXPLICIT'
        assert selected.destination_source == 'USER'
    else:
        assert run.state.status == 'clarifying', run.errors
        assert run.pending_questions[0].status == 'open'
        if intent == 'UNSPECIFIED':
            assert run.pending_questions[0].kind == 'trip_request'
            assert run.state.destination_round == 0
        else:
            assert run.pending_questions[0].kind == 'destination_choice'
            assert run.state.destination_round == 1
        assert 'constraint_planner' not in run.visits


def exhausted(graph, data):
    run = execute(graph, data)
    return execute(graph, data, previous=run, answer=answer(run))


def test_unanswered_choices_survive_restart_without_automatic_selection():
    graph, store, components, data = setup([result(), result(), result()])
    second = exhausted(graph, data)
    third = execute(graph, data, previous=second, answer=answer(second))
    assert third.state.status == 'clarifying'
    assert third.pending_questions[0].round == 3
    restarted = GraphRun.model_validate(store.checkpoint)
    assert restarted.pending_questions == third.pending_questions
    assert store.claims == 0
    assert components.destination_agent.select.await_count == 3


def test_choice_matches_exact_snapshot_and_does_not_trigger_final_resolve():
    graph, store, components, data = setup([result(), result(), result('selected')])
    second = exhausted(graph, data)
    option = min(second.pending_questions[0].options, key=lambda item: item.rank)
    a = answer(second, selected_option_id=option.option_id,
               declared_unknown_fields=[], answer_raw='Da Lat')
    for patch in [dict(question_id=uuid4()), dict(episode_id=uuid4()), dict(selected_option_id='not-issued'),
                  dict(question='Changed text'), dict(round=1)]:
        with pytest.raises(ValueError):
            execute(graph, data, previous=second, answer=a.model_copy(update=patch))
    final = execute(graph, data, previous=second, answer=a)
    assert final.state.status == 'completed', final.errors
    assert final.outputs['destination_agent'].selection_method == 'USER_CHOICE'
    assert final.outputs['request_parser'].destination.selection_authority == 'USER'
    assert final.state.destination_round == 2 and store.claims == 0


def test_new_explicit_city_cannot_be_replaced_by_resolver():
    graph, store, components, data = setup([result(), result('selected')])
    first = execute(graph, data)
    new = request('EXPLICIT')
    new['destination']['city'] = 'Hue'
    final = execute(graph, new, previous=first, answer_raw='I want Hue')
    assert final.state.status == 'failed' and 'constraint_planner' not in final.visits


def test_missing_unapproved_preference_does_not_get_defaulted():
    data = request()
    data['preferences']['pace'] = None
    data['meta']['field_decisions']['preferences.pace'] = 'UNKNOWN'
    data['meta']['field_sources'].pop('preferences.pace', None)
    data['meta']['field_confidences'].pop('preferences.pace', None)
    first = result('needs_more_info').model_dump()
    first['information_requests'] = [dict(purpose='destination_info', fields=['preferences.pace'], reason='Select city')]
    graph, store, components, _ = setup([DestinationResult.model_validate(first), result('selected')])
    run = execute(graph, data)
    assert run.state.status == 'awaiting_relaxation'
    assert not run.pending_questions
    assert run.outputs['request_parser'].preferences.pace is None
    assert run.outputs['request_parser'].meta.field_sources.get('preferences.pace') != 'default'


@pytest.mark.parametrize('consent', [True, False])
def test_constraint_proposal_requires_specific_explicit_confirmation(consent):
    recovery = result('no_valid_candidate', recovery=True).model_dump()
    recovery['recovery'] = dict(fields=['budget.amount'], reason='Expand budget', constraint_proposal=dict(
        proposal_id='budget-1', fields=['budget.amount'], current_values={'budget.amount': 3000000},
        proposed_values={'budget.amount': 5000000}, reason='More destinations'))
    graph, store, components, data = setup([DestinationResult.model_validate(recovery), result('selected')])
    first = execute(graph, data)
    changed = request()
    changed['budget']['amount'] = 9000000
    invalid = execute(graph, changed, previous=first, answer_raw='yes')
    assert invalid.pending_questions == first.pending_questions
    assert invalid.outputs['request_parser'].budget.amount == 3000000
    assert 'specific proposal' in invalid.explanation
    supplied = answer(first, confirmed_proposal_id='budget-1', constraint_confirmed=consent)
    final = execute(graph, changed, previous=first, answer=supplied)
    assert final.outputs['request_parser'].budget.amount == (5000000 if consent else 3000000)
    assert components.destination_agent.select.call_args.args[0].budget.amount == (5000000 if consent else 3000000)
