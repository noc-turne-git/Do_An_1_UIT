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
    data = fixture('trip_request')
    authority = 'user' if intent == 'EXPLICIT' else 'delegated' if intent in {
        'ANY', 'ANY_DESTINATION', 'DELEGATE_SELECTION'} else 'none'
    data['destination'].update(selection_intent=intent, selection_authority=authority,
        selection_provenance=dict(source='user', evidence='User intent: ' + intent) if authority != 'none' else None,
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


@pytest.mark.parametrize('intent,status', list(product(
    ['EXPLICIT', 'ANY_DESTINATION', 'DELEGATE_SELECTION', 'USER_UNKNOWN', 'UNSPECIFIED'],
    ['selected', 'needs_more_info', 'needs_user_choice', 'no_valid_candidate'])))
def test_intent_status_matrix(intent, status):
    graph, store, components, data = setup([result(status)], intent)
    run = execute(graph, data)
    if status == 'no_valid_candidate' or intent == 'DELEGATE_SELECTION' and status == 'needs_user_choice':
        assert run.state.status == 'failed'
        assert not run.pending_questions
    elif status == 'selected' and intent in {'EXPLICIT', 'ANY_DESTINATION', 'DELEGATE_SELECTION'}:
        assert run.state.status == 'completed', run.errors
        assert run.state.destination_round == run.state.clarification_round == 0
        selected = run.outputs['destination_agent']
        assert selected.selection_method == ('USER_EXPLICIT' if intent == 'EXPLICIT' else 'DELEGATED')
        assert selected.selection_provenance.source == ('user' if intent == 'EXPLICIT' else 'default')
    else:
        assert run.state.status == 'clarifying', run.errors
        assert run.pending_questions[0].status == 'open'
        assert run.state.destination_round == 1 and run.state.clarification_round == 0
        assert 'constraint_planner' not in run.visits


@pytest.mark.parametrize('sequence', list(product(['needs_more_info', 'needs_user_choice'], repeat=2)))
def test_any_all_info_choice_sequences_wait_for_last_answer_then_resolve_once(sequence):
    graph, store, components, data = setup([*(result(s) for s in sequence), result()])
    first = execute(graph, data)
    second = execute(graph, data, previous=first, answer=answer(first))
    assert second.state.status == 'clarifying' and second.state.destination_round == 2
    assert second.state.destination_episode.final_resolve_status == 'not_started'
    assert components.destination_agent.select.await_count == 2 and store.claims == 0
    unchanged = execute(graph, data, previous=second)
    assert unchanged == second and store.claims == 0
    final = execute(graph, data, previous=second, answer=answer(second))
    assert final.state.status == 'completed', final.errors
    assert components.destination_agent.select.await_count == 3 and store.claims == 1
    selected = final.outputs['destination_agent']
    assert selected.selected_candidate_id == 'dalat'  # rank 1 is second in array
    assert selected.selection_method == 'ANY_DEFAULT' and selected.selection_provenance.source == 'default'
    assert final.outputs['request_parser'].destination.selection_provenance.source == 'user'
    assert final.state.destination_round == 2 and final.state.clarification_round == 0
    assert execute(graph, data, previous=final) == final


def exhausted(graph, data):
    run = execute(graph, data)
    return execute(graph, data, previous=run, answer=answer(run))


@pytest.mark.parametrize('final_result', [result('no_valid_candidate'), result('needs_more_info'),
    result().model_copy(update={'candidate_regions': result().candidate_regions[:1]})])
def test_final_resolution_without_valid_rank_one_fails(final_result):
    graph, store, components, data = setup([result(), result(), final_result])
    second = exhausted(graph, data)
    final = execute(graph, data, previous=second, answer=answer(second))
    assert final.state.status == 'failed' and not final.pending_questions
    assert final.state.destination_episode.final_resolve_status == 'completed'
    assert store.claims == 1 and components.destination_agent.select.await_count == 3


def test_completed_checkpoint_is_reused_after_crash_before_selection():
    graph, store, components, data = setup([result(), result(), result()])
    second = exhausted(graph, data)
    original = store.complete_final_resolve
    saved = []
    def complete(*args):
        episode = original(*args)
        saved.append(store.checkpoint)
        return episode
    store.complete_final_resolve = complete
    execute(graph, data, previous=second, answer=answer(second))
    restarted = GraphRun.model_validate(saved[0])
    final = execute(graph, data, previous=restarted)
    assert final.state.status == 'completed', final.errors
    assert components.destination_agent.select.await_count == 3 and store.claims == 1


def test_claimed_checkpoint_never_reexecutes_provider():
    graph, store, components, data = setup([result(), result(), RuntimeError('provider interrupted')])
    second = exhausted(graph, data)
    saved = []
    original = store.claim_final_resolve
    def claim(*args):
        value = original(*args)
        saved.append(store.checkpoint)
        return value
    store.claim_final_resolve = claim
    execute(graph, data, previous=second, answer=answer(second))
    run = execute(graph, data, previous=GraphRun.model_validate(saved[0]))
    assert run.state.status == 'planning' and run.awaiting_final_resolve
    assert components.destination_agent.select.await_count == 3 and store.claims == 1


def test_choice_matches_exact_snapshot_and_does_not_trigger_final_resolve():
    graph, store, components, data = setup([result(), result(), result('selected')])
    second = exhausted(graph, data)
    a = answer(second, selected_option_id='dalat', declared_unknown_fields=[], answer_raw='dalat')
    for patch in [dict(question_id=uuid4()), dict(episode_id=uuid4()), dict(selected_option_id='not-issued'),
                  dict(question='Changed text'), dict(round=1)]:
        with pytest.raises(ValueError):
            execute(graph, data, previous=second, answer=a.model_copy(update=patch))
    final = execute(graph, data, previous=second, answer=a)
    assert final.state.status == 'completed', final.errors
    assert final.outputs['destination_agent'].selection_method == 'USER_CHOICE'
    assert final.outputs['request_parser'].destination.selection_authority == 'user'
    assert final.state.destination_round == 2 and store.claims == 0


def test_unrecognized_option_keeps_question_open_but_new_explicit_destination_is_validated():
    graph, store, components, data = setup([result(), result('selected')])
    first = execute(graph, data)
    invalid = execute(graph, data, previous=first, answer_raw='not-an-option')
    assert invalid.pending_questions == first.pending_questions and len(store.answers) == 0
    without_identity = execute(graph, data, previous=first, answer_raw='dalat')
    assert without_identity.pending_questions == first.pending_questions and len(store.answers) == 0
    new = request('EXPLICIT')
    final = execute(graph, new, previous=first, answer_raw='I want Da Lat')
    assert final.state.status == 'completed', final.errors
    assert components.destination_agent.select.await_count == 2
    assert final.outputs['destination_agent'].selection_method == 'USER_EXPLICIT'
    assert final.outputs['destination_agent'].selection_provenance.source == 'user'
    assert store.answers[0].destination_update.city == new['destination']['city']


def test_new_explicit_city_cannot_be_replaced_by_resolver():
    graph, store, components, data = setup([result(), result('selected')])
    first = execute(graph, data)
    new = request('EXPLICIT')
    new['destination']['city'] = 'Hue'
    final = execute(graph, new, previous=first, answer_raw='I want Hue')
    assert final.state.status == 'failed' and 'constraint_planner' not in final.visits


def test_recovery_questions_require_fields_and_remaining_destination_budget():
    graph, store, components, data = setup([result('no_valid_candidate', recovery=True)] * 3, 'USER_UNKNOWN')
    first = execute(graph, data)
    second = execute(graph, data, previous=first, answer=answer(first))
    final = execute(graph, data, previous=second, answer=answer(second))
    assert final.state.status == 'failed' and store.claims == 0
    assert final.state.destination_round == 2 and not final.pending_questions


def test_needs_more_info_requires_structured_purpose():
    invalid = result('needs_more_info').model_copy(update={'information_requests': []})
    graph, _, _, data = setup([invalid])
    run = execute(graph, data)
    assert run.state.status == 'failed' and run.state.destination_round == 0


def test_duplicate_ranks_fail_and_permutation_cannot_change_final_choice():
    invalid = result().model_dump()
    invalid['candidate_regions'][0]['rank'] = 1
    graph, _, _, data = setup([invalid])
    failed = execute(graph, data)
    assert failed.state.status == 'failed' and failed.state.destination_round == 0
    reversed_result = result().model_copy(update={'candidate_regions': list(reversed(result().candidate_regions))})
    graph, _, _, data = setup([result(), result(), reversed_result])
    second = exhausted(graph, data)
    final = execute(graph, data, previous=second, answer=answer(second))
    assert final.outputs['destination_agent'].selected_candidate_id == 'dalat'


@pytest.mark.parametrize('intent', ['USER_UNKNOWN', 'UNSPECIFIED'])
def test_single_candidate_never_grants_selection_authority(intent):
    one = result('selected').model_copy(update={'candidate_regions': result().candidate_regions[1:]})
    graph, _, _, data = setup([one], intent)
    run = execute(graph, data)
    assert run.state.status == 'clarifying' and 'constraint_planner' not in run.visits


def test_mixed_purposes_use_independent_budgets_and_do_not_default_destination_fields():
    data = request()
    data['preferences']['pace'] = None
    data['meta']['field_decisions'] = {'preferences.pace': 'UNKNOWN'}
    first = result('needs_more_info').model_dump()
    first['information_requests'] = [dict(purpose='destination_info', fields=['preferences.pace'], reason='Select city')]
    graph, store, components, _ = setup([DestinationResult.model_validate(first), result('selected')])
    run = execute(graph, data)
    assert run.pending_questions[0].kind == 'destination_info'
    assert run.state.clarification_round == 0 and run.state.destination_round == 1
    assert run.outputs['request_parser'].preferences.pace is None
    final = execute(graph, data, previous=run, answer=answer(run))
    assert final.outputs['request_parser'].preferences.pace is None
    assert final.outputs['request_parser'].meta.field_sources.get('preferences.pace') != 'default'


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
    supplied = answer(first, confirmed_proposal_id='budget-1', constraint_confirmed=consent)
    final = execute(graph, changed, previous=first, answer=supplied)
    assert final.outputs['request_parser'].budget.amount == (5000000 if consent else 3000000)
    assert components.destination_agent.select.call_args.args[0].budget.amount == (5000000 if consent else 3000000)


def test_actual_issued_last_trip_question_defaults_only_after_answer():
    from ai.orchestration.clarification_policy import ClarificationPolicy
    data = request('EXPLICIT')
    data['travelers']['children'] = None
    data['meta']['field_sources'].pop('travelers.children', None)
    store = Store()
    graph = workflow(persistence=store, clarification_policy=ClarificationPolicy(max_clarification_rounds=1))
    first = execute(graph, data)
    assert first.state.clarification_round == 1 and first.pending_questions[0].status == 'open'
    assert first.outputs['request_parser'].travelers.children is None
    assert execute(graph, data, previous=first) == first
    final = execute(graph, data, previous=first, answer=answer(first))
    assert final.outputs['request_parser'].travelers.children == 0
    assert final.outputs['request_parser'].meta.field_sources['travelers.children'] == 'default'
    assert final.state.status == 'completed', final.errors
