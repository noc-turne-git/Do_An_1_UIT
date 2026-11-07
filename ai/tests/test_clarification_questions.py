from uuid import uuid4

import pytest

from ai.orchestration.clarification_questions import (QuestionSpec, attach_identity,
    prepare_question, specifications)
from ai.orchestration.workflow_state import StateMachine, WorkflowRun
from shared.contracts import (ConstraintProposal, DestinationEpisode, DestinationResult,
                              PendingQuestion, QuestionOption, WorkflowState)


def choice_spec():
    result = DestinationResult(request_type='IMPLICIT', selected_region=None,
        selection_status='needs_user_choice', selection_reason='Choose',
        candidate_regions=[dict(city='Hue', candidate_id='c2', rank=2, reason='History'),
                           dict(city='Da Lat', candidate_id='c1', rank=1, reason='Weather')],
        missing_fields=[])
    return specifications(result)[0]


def test_choice_draft_requires_exact_canonical_options_and_kind():
    spec = choice_spec()
    valid = dict(question='Chọn thành phố', fields=['destination.city'],
        kind='destination_choice', options=[o.model_dump() for o in spec.options])
    assert prepare_question(spec, draft=valid).question == 'Chọn thành phố'
    for change in [dict(kind='trip_request'), dict(fields=['budget.amount']),
                   dict(options=valid['options'][:1]),
                   dict(options=[valid['options'][0], dict(valid['options'][1], rank=None)]),
                   dict(options=[valid['options'][0], dict(valid['options'][1], reason='other')]),
                   dict(options=[valid['options'][0], dict(valid['options'][1], option_id='c2')])]:
        fallback = prepare_question(spec, draft=valid | change)
        assert fallback.question != valid['question']
        assert fallback.options == list(spec.options)
        assert fallback.status == 'legacy' and fallback.question_id is None
        fallback.options[0].city = 'Changed after fallback'
        assert spec.options[0].city == 'Hue'


def test_destination_info_can_request_non_destination_fields_and_preserve_proposal():
    proposal = ConstraintProposal(proposal_id='p1', fields=['budget.amount'],
        current_values={'budget.amount': 3000000},
        proposed_values={'budget.amount': 5000000}, reason='No candidates')
    result = DestinationResult(request_type='INSUFFICIENT', selected_region=None,
        selection_status='no_valid_candidate', selection_reason='No match',
        candidate_regions=[], missing_fields=['budget.amount'],
        recovery=dict(reason='No match', fields=['budget.amount'],
                      constraint_proposal=proposal.model_dump()))
    spec = specifications(result)[0]
    assert spec.kind == 'destination_info' and spec.fields == ('budget.amount',)
    draft = dict(question='Tăng ngân sách?', fields=['budget.amount'],
        kind='destination_info', constraint_proposal=proposal.model_dump())
    assert prepare_question(spec, draft=draft).question == 'Tăng ngân sách?'
    changed = dict(draft, constraint_proposal=proposal.model_dump() |
                   {'proposed_values': {'budget.amount': 9000000}})
    fallback = prepare_question(spec, draft=changed)
    assert fallback.question != draft['question']
    assert fallback.constraint_proposal == proposal
    assert not fallback.options and fallback.question_id is None
    without_original = proposal.model_copy(update={'current_values': None})
    with pytest.raises(ValueError, match='current values'):
        QuestionSpec('destination_info', ('budget.amount',),
                     constraint_proposal=without_original)


def test_information_requests_are_separate_purpose_batches():
    result = DestinationResult(request_type='INSUFFICIENT', selected_region=None,
        selection_status='needs_more_info', selection_reason='Need details',
        candidate_regions=[], missing_fields=['trip.start_date', 'budget.amount'],
        information_requests=[dict(purpose='trip_request', fields=['trip.start_date'], reason='Trip'),
                              dict(purpose='destination_info', fields=['budget.amount'], reason='Search')])
    specs = specifications(result)
    assert [(s.kind, s.fields) for s in specs] == [
        ('trip_request', ('trip.start_date',)), ('destination_info', ('budget.amount',))]
    wrong = dict(question='Both', fields=['trip.start_date', 'budget.amount'], kind='trip_request')
    assert prepare_question(specs[0], draft=wrong).fields == ['trip.start_date']
    assert prepare_question(specs[0], draft=wrong).question != 'Both'


def test_memory_draft_and_validation_do_not_consume_budget():
    run = WorkflowRun(state=WorkflowState(request_id=uuid4(), trip_id=uuid4(),
        status='parsing', current_step='request_parser', completed_steps=[],
        artifacts={}, clarification_round=0, destination_round=0,
        pending_fields=[], retry_count=0))
    sm = StateMachine(run)
    sm.issue_question(choice_spec(), draft={'question': 'invalid', 'fields': [], 'kind': 'trip_request'})
    assert run.state.destination_round == run.state.clarification_round == 0
    assert run.pending_questions[0].question_id is None
    assert run.pending_questions[0].options == list(choice_spec().options)


def test_identity_attaches_only_after_preparation():
    spec = choice_spec()
    draft = prepare_question(spec)
    issued = attach_identity(draft, question_id=uuid4(), episode_id=uuid4(),
                             intent_snapshot='UNKNOWN', round=2)
    assert issued.status == 'open' and issued.round == 2
    with pytest.raises(ValueError):
        attach_identity(issued, question_id=uuid4(), episode_id=uuid4(),
                        intent_snapshot='UNKNOWN', round=2)
