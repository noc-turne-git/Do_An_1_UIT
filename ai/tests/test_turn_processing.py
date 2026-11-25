import asyncio
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ai.orchestration.graph_workflow import GraphRun
from ai.orchestration.turns import ParsedTurn, StaleTurn
from ai.orchestration.request_parser import apply_changes, ParserOutput, Change, empty_request
from shared.contracts import DestinationEpisode, DestinationResult, SelectionPolicy, TripRequest
from test_destination_resolution import Store, answer, request, result
from test_graph_workflow import workflow
from ai.orchestration.mock_workflow import fixture, mock_components


class TurnStore(Store):
    def prepare_turn(self, request, previous, *, trip_id=None, request_id=None):
        return trip_id, request_id

    def ensure_episode(self, run, policy):
        self.episode = DestinationEpisode(episode_id=uuid4(), request_id=run.state.request_id,
            **policy.model_dump())
        return self.episode

    def supersede_questions(self, run):
        self.superseded = [q.model_copy(update={'status': 'superseded'}) for q in self.questions]
        self.questions = []


def setup_turn():
    store = TurnStore()
    components = mock_components()
    components.destination_agent.select = AsyncMock(return_value=result())
    return workflow(components, persistence=store), store, components


def turn(graph, request=None, **kwargs):
    return asyncio.run(graph.run_turn(request, current_date=date(2026, 11, 4), **kwargs))


def test_chat_and_structured_graph_share_issuance_and_answer_history():
    graph, store, _ = setup_turn()
    value = TripRequest.model_validate(request('USER_UNKNOWN'))
    first = turn(graph, value).run
    restored = GraphRun.model_validate_json(first.model_dump_json())
    a = answer(restored)
    parser = AsyncMock(return_value=ParsedTurn(value, 'summary'))
    text = turn(graph, previous=restored, content=a.answer_raw, parser=parser, answer=a).run
    other, _, _ = setup_turn()
    initial = turn(other, value).run
    structured = turn(other, value, previous=initial, answer=answer(initial)).run
    assert text.state.status == structured.state.status == 'clarifying'
    assert text.state.destination_round == structured.state.destination_round == 2
    assert len(text.answers_history) == len(structured.answers_history) == 1
    assert len(text.user_updates) == len(structured.user_updates) == 1
    assert text.state.request_id == first.state.request_id
    assert text.state.destination_episode.episode_id == first.state.destination_episode.episode_id
    assert text.pending_questions[0].status == 'open'


def test_stale_reference_rejected_before_parser_even_for_explicit_new_input():
    graph, store, _ = setup_turn()
    value = TripRequest.model_validate(request('USER_UNKNOWN'))
    first = turn(graph, value).run
    parser = AsyncMock(return_value=ParsedTurn(TripRequest.model_validate(request('EXPLICIT'))))
    for changes in [dict(question_id=uuid4(), episode_id=first.state.destination_episode.episode_id),
                    dict(question_id=first.pending_questions[0].question_id, episode_id=uuid4()),
                    dict(workflow_id=uuid4())]:
        with pytest.raises(StaleTurn):
            turn(graph, previous=first, content='New explicit destination', parser=parser, **changes)
    parser.assert_not_called()


def test_nonplanning_and_parser_errors_preserve_entire_workflow():
    graph, store, components = setup_turn()
    first = turn(graph, TripRequest.model_validate(request('USER_UNKNOWN'))).run
    snapshot = first.model_dump(mode='json')
    for extraction in [ParsedTurn(first.outputs['request_parser'], 'Advice', planning=False),
                       ParsedTurn(None, error='PARSER_ERROR')]:
        parser = AsyncMock(return_value=extraction)
        response = turn(graph, previous=first, content='Advice', parser=parser)
        assert response.run.model_dump(mode='json') == snapshot
        assert store.checkpoint == snapshot
    assert components.destination_agent.select.call_count == 1


def test_failed_requires_new_workflow_and_clean_episode():
    graph = workflow()
    value = TripRequest.model_validate(request('EXPLICIT'))
    failed = turn(graph, value).run.model_copy(deep=True)
    failed.state.status = 'failed'
    failed.state.destination_episode.status = 'failed'
    before = failed.model_dump(mode='json')
    changed = value.model_copy(deep=True)
    changed.destination.city = 'Hue'
    parser = AsyncMock(return_value=ParsedTurn(changed))
    new = turn(graph, previous=failed, content='Hue', parser=parser).run
    assert new.state.request_id != failed.state.request_id
    assert new.state.destination_episode.episode_id != failed.state.destination_episode.episode_id
    assert new.state.destination_round == 0
    assert not new.answers_history
    assert failed.model_dump(mode='json') == before
    assert new.outputs['request_parser'].travelers == value.travelers
    assert parser.call_args.args[0].destination.candidate_cities == []
    assert parser.call_args.args[0].destination.city is None


def test_completed_edit_keeps_workflow_and_only_destination_change_starts_episode():
    components = mock_components()
    async def select_current(request, *, context=None):
        payload = fixture('destination_result')
        payload['selected_region']['city'] = request.destination.city
        return DestinationResult.model_validate(payload)
    components.destination_agent.select = AsyncMock(side_effect=select_current)
    graph = workflow(components)
    source = TripRequest.model_validate(request('EXPLICIT'))
    completed = turn(graph, source).run
    assert completed.state.status == 'completed', completed.errors
    original_workflow = completed.state.request_id
    original_episode = completed.state.destination_episode.episode_id

    revised = source.model_copy(deep=True)
    revised.travelers.adults += 1
    ordinary = turn(graph, previous=completed, content='Thêm một người lớn',
                    parser=AsyncMock(return_value=ParsedTurn(revised))).run
    assert ordinary.state.status == 'completed'
    assert ordinary.state.request_id == original_workflow
    assert ordinary.state.destination_episode.episode_id == original_episode
    assert ordinary.state.destination_round == completed.state.destination_round
    assert ordinary.state.artifacts.destination_result_id == completed.state.artifacts.destination_result_id
    assert ordinary.resolved_destination == completed.resolved_destination

    destination = revised.model_copy(deep=True)
    destination.destination.city = 'Hue'
    destination.destination.selection_provenance.evidence = 'destination.city=Hue'
    changed = turn(graph, previous=ordinary, content='Đổi điểm đến sang Huế',
                   parser=AsyncMock(return_value=ParsedTurn(destination))).run
    assert changed.state.status == 'failed'
    assert changed.outputs['request_parser'].destination.city == 'Hue'
    assert changed.state.request_id == original_workflow
    assert changed.state.destination_episode.episode_id != original_episode
    assert changed.state.destination_round == 0
