"""Intent handoff and graph action decisions use offline components only."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from ai.orchestration.graph_workflow import GraphRun
from ai.orchestration.request_parser import Change, ParserOutput, empty_request, parse_turn
from ai.orchestration.turns import ParsedTurn
from ai.schemas.runtime import AgentResult, AgentStatus
from shared.contracts import TripRequest
from test_destination_resolution import request, result
from test_turn_processing import setup_turn, turn


def partial_destination():
    value = TripRequest.model_validate(request('USER_UNKNOWN'))
    data = value.model_dump(mode='json')
    data['trip'].update(start_date=None, end_date=None, duration_days=None)
    data['travelers'].update(adults=None, children=None)
    return TripRequest.model_validate(data)


def test_parser_hands_recommendation_to_graph_without_inventing_selection(monkeypatch):
    from ai.orchestration import request_parser
    output = ParserOutput(intent='travel_advice', requested_action='destination_recommendation',
        summary='Possible destinations', changes=[])
    harness = SimpleNamespace(run=AsyncMock(return_value=AgentResult(
        status=AgentStatus.SUCCESS, output=output)),
        llm=SimpleNamespace(aclose=AsyncMock()))
    monkeypatch.setattr(request_parser, 'create_agent_harness', lambda *args: harness)
    parsed = asyncio.run(parse_turn(SimpleNamespace(llm_timeout_seconds=1),
        previous=empty_request(), content='Suggest destinations', history=[],
        request_id='test', conversation_id='test', extraction_only=True))
    assert parsed.action == 'destination_recommendation'
    assert parsed.planning is True
    assert parsed.request.destination.selection_intent == 'USER_UNKNOWN'
    assert parsed.request.destination.selection_authority == 'USER'
    assert parsed.request.destination.destination_source is None


def test_parser_keeps_informational_advice_direct(monkeypatch):
    from ai.orchestration import request_parser
    output = ParserOutput(intent='travel_advice', requested_action='information',
        summary='Here is the advice', changes=[])
    harness = SimpleNamespace(run=AsyncMock(return_value=AgentResult(
        status=AgentStatus.SUCCESS, output=output)),
        llm=SimpleNamespace(aclose=AsyncMock()))
    monkeypatch.setattr(request_parser, 'create_agent_harness', lambda *args: harness)
    previous = partial_destination()
    parsed = asyncio.run(parse_turn(SimpleNamespace(llm_timeout_seconds=1),
        previous=previous, content='What is there to do?', history=[],
        request_id='test', conversation_id='test', extraction_only=True))
    assert parsed.reply == 'Here is the advice'
    assert parsed.planning is False
    assert parsed.request == previous


def test_recommendations_without_dates_or_travelers_offer_choice_and_resume():
    graph, _, components = setup_turn()
    components.destination_agent.select = AsyncMock(return_value=result())
    value = partial_destination()
    first = turn(graph, content='Suggest destinations',
        parser=AsyncMock(return_value=ParsedTurn(value, action='destination_recommendation'))).run
    assert first.state.status == 'clarifying'
    assert first.pending_questions[0].kind == 'destination_choice'
    assert 'constraint_planner' not in first.visits
    restored = GraphRun.model_validate_json(first.model_dump_json())
    assert restored.itinerary_requested is False


def test_choice_resumes_snapshot_without_starting_itinerary():
    graph, _, components = setup_turn()
    components.destination_agent.select = AsyncMock(side_effect=[result(), result('selected')])
    first = turn(graph, content='Suggest destinations', parser=AsyncMock(return_value=ParsedTurn(
        partial_destination(), action='destination_recommendation'))).run
    restored = GraphRun.model_validate_json(first.model_dump_json())
    chosen = turn(graph, previous=restored, content='1', parser=AsyncMock()).run
    assert chosen.outputs['destination_agent'].selection_method == 'USER_CHOICE'
    assert chosen.outputs['request_parser'].destination.destination_source == 'USER'
    assert chosen.itinerary_requested is False
    assert 'constraint_planner' not in chosen.visits


def test_itinerary_modification_runs_planning_again():
    from test_graph_workflow import workflow
    graph = workflow()
    initial = TripRequest.model_validate(request('EXPLICIT'))
    first = turn(graph, content='Plan the itinerary', parser=AsyncMock(return_value=ParsedTurn(
        initial, action='itinerary_planning'))).run
    assert first.state.status == 'completed', first.errors
    edited = initial.model_copy(deep=True)
    edited.travelers.adults += 1
    second = turn(graph, previous=GraphRun.model_validate_json(first.model_dump_json()),
        content='Add one adult', parser=AsyncMock(return_value=ParsedTurn(
            edited, action='itinerary_modification', changed_fields=['travelers.adults']))).run
    assert second.state.status == 'completed', second.errors
    assert second.outputs['request_parser'].travelers.adults == edited.travelers.adults
    assert second.state.artifacts.itinerary_id != first.state.artifacts.itinerary_id
