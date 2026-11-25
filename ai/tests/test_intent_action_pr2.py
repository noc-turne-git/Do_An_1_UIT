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


def test_explicit_city_selection_action_reaches_graph_without_starting_itinerary(monkeypatch):
    from ai.orchestration import request_parser

    output = ParserOutput(intent='trip_planning', requested_action='destination_selection',
        summary='Mình ghi nhận bạn muốn đi Đà Lạt.', changes=[
            Change(path='destination.city', value_json='"Đà Lạt"', decision='SPECIFIED')])
    harness = SimpleNamespace(run=AsyncMock(return_value=AgentResult(
        status=AgentStatus.SUCCESS, output=output)),
        llm=SimpleNamespace(aclose=AsyncMock()))
    monkeypatch.setattr(request_parser, 'create_agent_harness', lambda *args: harness)
    parsed = asyncio.run(parse_turn(SimpleNamespace(llm_timeout_seconds=1),
        previous=empty_request(), content='tôi muốn đi đà lạt', history=[],
        request_id='test', conversation_id='test', extraction_only=True))

    assert parsed.error is None
    assert parsed.action == 'destination_selection'
    assert parsed.changed_fields == ['destination.city']
    graph, _, components = setup_turn()
    run = turn(graph, content='tôi muốn đi đà lạt',
        parser=AsyncMock(return_value=parsed)).run
    assert run.itinerary_requested is False
    assert run.outputs['request_parser'].destination.city == 'Đà Lạt'
    assert run.outputs['request_parser'].destination.selection_intent == 'EXPLICIT'
    assert 'planning_engine' not in run.visits
    components.destination_agent.select.assert_awaited_once()


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


def test_information_with_incomplete_request_stays_direct():
    graph, _, components = setup_turn()
    response = turn(graph, content='What can I do there?',
        parser=AsyncMock(return_value=ParsedTurn(empty_request(), 'Advice', action='information')))
    assert response.reply == 'Advice'
    assert response.run is None
    components.destination_agent.select.assert_not_called()


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


def test_graph_normalizes_unspecified_recommendation_to_user_choice():
    graph, _, components = setup_turn()
    run = turn(graph, content='Suggest destinations', parser=AsyncMock(return_value=ParsedTurn(
        empty_request(), action='destination_recommendation'))).run
    assert components.destination_agent.select.await_count == 1
    assert run.outputs['request_parser'].destination.selection_intent == 'USER_UNKNOWN'
    assert run.outputs['request_parser'].destination.selection_authority == 'USER'
    assert run.pending_questions[0].kind == 'destination_choice'


def test_legacy_snapshot_defaults_to_itinerary_goal():
    from test_graph_workflow import workflow
    graph = workflow()
    first = turn(graph, TripRequest.model_validate(request('EXPLICIT'))).run
    snapshot = first.model_dump(mode='json')
    snapshot.pop('itinerary_requested')
    assert GraphRun.model_validate(snapshot).itinerary_requested is True


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


def test_explicit_delegation_of_issued_candidates_does_not_start_itinerary():
    graph, _, components = setup_turn()
    components.destination_agent.select = AsyncMock(side_effect=[result(), result('selected')])
    first = turn(graph, content='Suggest destinations', parser=AsyncMock(return_value=ParsedTurn(
        partial_destination(), action='destination_recommendation'))).run
    delegated = turn(graph, previous=GraphRun.model_validate_json(first.model_dump_json()),
        content='Bạn chọn đi', parser=AsyncMock(return_value=ParsedTurn(
            first.outputs['request_parser'], action='selection_delegation',
            destination_action='delegate'))).run
    assert delegated.outputs['destination_agent'].selection_method == 'AGENT_DELEGATED'
    assert delegated.outputs['request_parser'].destination.destination_source == 'AGENT_DELEGATED'
    assert 'constraint_planner' not in delegated.visits


def test_planning_after_selection_uses_stored_goal_and_mandatory_fields():
    graph, _, components = setup_turn()
    components.destination_agent.select = AsyncMock(side_effect=[result(), result('selected')])
    first = turn(graph, content='Suggest destinations', parser=AsyncMock(return_value=ParsedTurn(
        partial_destination(), action='destination_recommendation'))).run
    chosen = turn(graph, previous=first, content='1', parser=AsyncMock()).run
    planned_request = chosen.outputs['request_parser'].model_dump(mode='json')
    complete = request('EXPLICIT')
    planned_request['trip'] = complete['trip']
    planned_request['travelers'] = complete['travelers']
    planned_request = TripRequest.model_validate(planned_request)
    planned = turn(graph, previous=GraphRun.model_validate_json(chosen.model_dump_json()),
        content='Now plan the itinerary', parser=AsyncMock(return_value=ParsedTurn(
            planned_request, action='itinerary_planning'))).run
    assert planned.state.status == 'completed', planned.errors
    assert planned.visits['planning_engine'] == 1


def test_information_turn_preserves_pending_question_and_snapshot():
    graph, _, components = setup_turn()
    first = turn(graph, content='Suggest destinations', parser=AsyncMock(return_value=ParsedTurn(
        partial_destination(), action='destination_recommendation'))).run
    restored = GraphRun.model_validate_json(first.model_dump_json())
    response = turn(graph, previous=restored, content='What is the weather like?',
        parser=AsyncMock(return_value=ParsedTurn(restored.outputs['request_parser'],
            'General advice', action='information')))
    assert response.reply == 'General advice'
    assert response.run.model_dump(mode='json') == restored.model_dump(mode='json')
    assert components.destination_agent.select.await_count == 1


def test_recommendation_never_selects_without_user_authority():
    graph, _, components = setup_turn()
    components.destination_agent.select = AsyncMock(return_value=result('selected'))
    run = turn(graph, content='Recommend somewhere', parser=AsyncMock(return_value=ParsedTurn(
        partial_destination(), action='destination_recommendation'))).run
    assert run.outputs['destination_agent'].selection_status == 'needs_user_choice'
    assert run.outputs['request_parser'].destination.selection_authority == 'USER'
    assert run.resolved_destination is None


def test_itinerary_goal_waits_for_mandatory_fields():
    graph, _, _ = setup_turn()
    run = turn(graph, content='Plan a trip', parser=AsyncMock(return_value=ParsedTurn(
        partial_destination(), action='itinerary_planning'))).run
    assert run.pending_questions[0].kind == 'destination_choice'
    assert 'constraint_planner' not in run.visits


def test_explicit_itinerary_asks_for_missing_date_before_planning():
    graph, _, components = setup_turn()
    components.destination_agent.select = AsyncMock(return_value=result('selected'))
    data = request('EXPLICIT')
    data['trip']['start_date'] = None
    data['trip']['end_date'] = None
    data['trip']['duration_days'] = None
    data['meta']['field_sources'].pop('trip.start_date', None)
    data['meta']['field_sources'].pop('trip.end_date', None)
    run = turn(graph, content='Plan an itinerary', parser=AsyncMock(return_value=ParsedTurn(
        TripRequest.model_validate(data), action='itinerary_planning'))).run
    assert components.destination_agent.select.await_count == 1
    assert run.state.status == 'clarifying'
    assert run.pending_questions[0].kind == 'trip_request'
    assert run.pending_questions[0].fields[0].startswith('trip.')
    assert 'constraint_planner' not in run.visits


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


def test_recommendations_after_completed_itinerary_start_new_consultation():
    from ai.orchestration.mock_workflow import mock_components
    from test_graph_workflow import workflow
    components = mock_components()
    components.destination_agent.select = AsyncMock(side_effect=[result('selected'), result()])
    graph = workflow(components)
    initial = TripRequest.model_validate(request('EXPLICIT'))
    first = turn(graph, content='Plan the trip', parser=AsyncMock(return_value=ParsedTurn(
        initial, action='itinerary_planning'))).run
    assert first.state.status == 'completed', first.errors
    second = turn(graph, previous=GraphRun.model_validate_json(first.model_dump_json()),
        content='Suggest other destinations', parser=AsyncMock(return_value=ParsedTurn(
            first.outputs['request_parser'], action='destination_recommendation'))).run
    assert second.state.status == 'clarifying', second.errors
    assert second.pending_questions[0].kind == 'destination_choice'
    assert second.itinerary_requested is False
    assert components.destination_agent.select.await_count == 2
