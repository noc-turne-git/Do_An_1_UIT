"""Shared PostgreSQL scenario builders (not mocks)."""
from uuid import uuid4

from shared.contracts import PendingQuestion, AnswerHistory, SelectionPolicy
from app.repositories.clarifications import ClarificationRepository
from app.services.persistence import WorkflowPersistence
from ai.orchestration.graph_workflow import GraphRun


def start(db, seed):
    user, trip, request = seed(db)
    with db.sessions.begin() as session:
        ep = ClarificationRepository(session, user).start_episode(request, SelectionPolicy(
            selection_intent='ANY_DESTINATION', selection_authority='USER',
            selection_provenance=dict(source='user', evidence='Choose anywhere')))
        persistence = WorkflowPersistence(session, user)
        run = GraphRun.model_validate(persistence.load(request).model_dump())
        persistence.save_graph(run)
    return user, trip, request, ep


def question(ep, kind, round, **changes):
    data = dict(question_id=uuid4(), episode_id=ep.episode_id, status='open', round=round,
        intent_snapshot=ep.selection_intent, kind=kind, question='Choose a destination',
        fields=['destination.city'], options=[dict(option_id='o1', candidate_id='c1',
            city='Da Lat', rank=1, reason='Cool weather'), dict(option_id='o2', candidate_id='c2',
            city='Hue', rank=2, reason='History')])
    if kind != 'destination_choice':
        data.update(question='Confirm budget and pace', fields=['budget.amount', 'preferences.pace'], options=[])
        if kind == 'destination_info':
            data['constraint_proposal'] = dict(proposal_id='p1', fields=['budget.amount'],
                proposed_values={'budget.amount': 5000000}, reason='Expand destinations')
    return PendingQuestion.model_validate(data | changes)


def answer(q, **changes):
    return AnswerHistory.model_validate(dict(answer_id=uuid4(), question_id=q.question_id,
        episode_id=q.episode_id, kind=q.kind, round=q.round, asked_fields=q.fields,
        question=q.question, answer_raw='yes', resolved_fields=q.fields, declared_unknown_fields=[],
        selected_option_id='o1' if q.kind == 'destination_choice' else None,
        confirmed_proposal_id=q.constraint_proposal.proposal_id if q.constraint_proposal else None,
        constraint_confirmed=True if q.constraint_proposal else None) | changes)
