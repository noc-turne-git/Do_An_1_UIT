"""Offline counter/configuration checks; no agent, conversation or provider runs."""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ai.orchestration.clarification_policy import ClarificationPolicy
from ai.orchestration.clarification_questions import QuestionSpec
from ai.orchestration.graph_workflow import GraphRun, LangGraphOrchestrator
from ai.orchestration.mock_workflow import fixture
from ai.orchestration.workflow_state import StateMachine
from shared.clarification_config import destination_question_allowed
from shared.contracts import DestinationEpisode, TripRequest, WorkflowState


def budget_run(*, consumed, maximum):
    request_id = uuid4()
    return GraphRun(state=WorkflowState(request_id=request_id, trip_id=uuid4(),
        status='planning', current_step='destination_agent', completed_steps=[], artifacts={},
        clarification_round=0, destination_round=consumed, max_destination_rounds=maximum,
        destination_episode=DestinationEpisode(episode_id=uuid4(), request_id=request_id,
            destination_round=consumed, max_destination_rounds=maximum),
        pending_fields=[], retry_count=0))


def choice_spec():
    from shared.contracts import QuestionOption
    return QuestionSpec('destination_choice', ('destination.city',),
        (QuestionOption(option_id='o1', candidate_id='o1', rank=1, city='Da Lat', reason='Suitable'),))


@pytest.mark.parametrize('maximum', [0, 10, 20])
def test_boundary_and_choice_exemption(maximum):
    assert not destination_question_allowed('destination_info', maximum, maximum)
    assert not destination_question_allowed('destination_info', maximum + 1, maximum)
    assert destination_question_allowed('destination_choice', maximum, maximum)
    assert destination_question_allowed('destination_choice', maximum + 1, maximum)
    if maximum:
        assert destination_question_allowed('destination_info', maximum - 1, maximum)


def test_offline_issuance_counts_choice_past_cap_and_blocks_info():
    request = TripRequest.model_validate(fixture('trip_request'))
    run = budget_run(consumed=10, maximum=10)
    machine = StateMachine(run)
    issued = machine.issue_question(choice_spec(), request=request)
    assert issued.round == run.state.destination_round == run.state.destination_episode.destination_round == 11
    assert run.state.clarification_round == 0
    # Persisted/guest snapshots must remain loadable above the information limit.
    restored = GraphRun.model_validate(run.model_dump(mode='json'))
    assert restored.pending_questions == [issued]
    assert StateMachine(restored).issue_question(choice_spec(), request=request,
        question_id=issued.question_id) == issued
    assert restored.state.destination_round == 11
    with pytest.raises(ValueError, match='still open'):
        StateMachine(restored).issue_question(QuestionSpec('destination_info', ('preferences.pace',)), request=request)
    machine.update(status='planning', pending_questions=[], pending_fields=[])
    assert machine.issue_question(QuestionSpec('destination_info', ('preferences.pace',)), request=request) is None
    assert run.state.status == 'awaiting_relaxation' and run.state.destination_round == 11


@pytest.mark.parametrize('maximum', [0, 10, 20])
@pytest.mark.parametrize('persisted', [False, True])
def test_resume_rebinds_limit_without_refunding_counter_or_question(maximum, persisted):
    request = TripRequest.model_validate(fixture('trip_request'))
    run = budget_run(consumed=11, maximum=2)
    issued = StateMachine(run).issue_question(choice_spec(), request=request)
    graph = object.__new__(LangGraphOrchestrator)
    graph.clarification_policy = ClarificationPolicy(max_destination_rounds=maximum)
    graph.persistence = MagicMock() if persisted else None
    if persisted:
        graph.persistence.configure_destination_limit.return_value = run.state.destination_episode.model_copy(
            update={'max_destination_rounds': maximum})
    before = run.model_dump(mode='json')
    graph._apply_destination_limit(run)
    assert run.state.max_destination_rounds == run.state.destination_episode.max_destination_rounds == maximum
    assert run.state.destination_round == run.state.destination_episode.destination_round == 12
    assert run.pending_questions == [issued]
    assert run.answers_history == []
    assert str(run.state.destination_episode.episode_id) == before['state']['destination_episode']['episode_id']
    if persisted:
        graph.persistence.configure_destination_limit.assert_called_once_with(run, maximum)


def test_partial_legacy_snapshot_inherits_stored_budget():
    snapshot = budget_run(consumed=12, maximum=2).model_dump(mode='json')
    del snapshot['state']['max_destination_rounds']
    assert GraphRun.model_validate(snapshot).state.max_destination_rounds == 2
    snapshot['state']['max_destination_rounds'] = 2
    del snapshot['state']['destination_episode']['max_destination_rounds']
    assert GraphRun.model_validate(snapshot).state.destination_episode.max_destination_rounds == 2


def test_offline_information_question_consumes_last_slot():
    run = budget_run(consumed=19, maximum=20)
    issued = StateMachine(run).issue_question(QuestionSpec('destination_info', ('preferences.pace',)))
    assert issued.round == run.state.destination_round == run.state.destination_episode.destination_round == 20


def test_persistence_rebinds_both_projections_under_workflow_lock(monkeypatch):
    from app.repositories.clarifications import ClarificationRepository
    from app.services.persistence import WorkflowPersistence
    from app.db.models import DestinationEpisodeRecord, WorkflowRequestRecord
    run = budget_run(consumed=12, maximum=2)
    request = WorkflowRequestRecord(request_id=run.state.request_id, status='clarifying',
        active_episode_id=run.state.destination_episode.episode_id, destination_round=12,
        max_destination_rounds=2)
    episode = DestinationEpisodeRecord(episode_id=request.active_episode_id, request_id=request.request_id,
        status='active', destination_round=12, max_destination_rounds=2,
        final_resolve_status='not_started', selection_policy={})
    repo = MagicMock()
    repo.episode.return_value = episode
    repo.contract.side_effect = ClarificationRepository.contract
    monkeypatch.setattr('app.repositories.clarifications.ClarificationRepository', lambda *args: repo)
    persistence = WorkflowPersistence(MagicMock(), uuid4())
    persistence.request = MagicMock(return_value=request)
    updated = persistence.configure_destination_limit(run, 10)
    persistence.request.assert_called_once_with(run.state.request_id, lock=True)
    assert request.max_destination_rounds == episode.max_destination_rounds == updated.max_destination_rounds == 10
    assert request.destination_round == episode.destination_round == updated.destination_round == 12
    repo._snapshot.assert_called_once_with(request)


def test_orm_insert_default_reads_application_configuration(monkeypatch):
    from types import SimpleNamespace
    from app.db.models import configured_destination_rounds
    monkeypatch.setattr('app.core.config.get_settings', lambda: SimpleNamespace(max_destination_rounds=20))
    assert configured_destination_rounds() == 20
