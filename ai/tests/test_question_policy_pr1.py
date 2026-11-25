"""Question policy regressions for consultation and traveler evidence."""
import pytest

from ai.orchestration.request_parser import (empty_request, apply_changes,
                                             apply_traveler_evidence, ParserOutput, Change)
from test_graph_workflow import execute, workflow


def test_unresolved_destination_is_the_first_blocker_not_trip_dates():
    run = execute(workflow(), empty_request().model_dump())
    assert run.state.status == 'clarifying'
    assert run.pending_questions[0].fields == ['destination.selection_mode']
    assert run.outputs['request_parser'].missing_fields  # Collection remains incomplete.


def test_family_does_not_supply_a_traveler_count():
    request = apply_changes(empty_request(), ParserOutput(
        summary='Cả nhà muốn đi chơi', changes=[]))
    assert request.travelers.adults is None
    assert request.travelers.children is None
    assert 'travelers.adults' not in request.meta.field_sources


def test_declined_required_traveler_count_is_not_asked_again():
    from ai.orchestration.mock_workflow import fixture
    data = fixture('trip_request')
    data['travelers']['adults'] = None
    data['meta']['field_sources'].pop('travelers.adults', None)
    data['meta'].setdefault('field_decisions', {})['travelers.adults'] = 'DECLINED'
    run = execute(workflow(), data)
    assert all('travelers.adults' not in q.fields for q in run.pending_questions)


def test_direct_adult_count_corrects_previous_turn():
    previous = apply_changes(empty_request(), ParserOutput(summary='3 adults', changes=[
        Change(path='travelers.adults', value_json='3', decision='SPECIFIED')]))
    parsed = apply_changes(previous, ParserOutput(summary='2 adults', changes=[
        Change(path='travelers.adults', value_json='2', decision='SPECIFIED')]))
    corrected = apply_traveler_evidence(parsed, '2 người lớn', previous)
    assert corrected.travelers.adults == 2
    assert corrected.meta.field_sources['travelers.adults'] == 'user'
    assert previous.travelers.adults == 3


def test_selected_destination_checks_missing_travelers_before_planning_and_resumes():
    from ai.orchestration.mock_workflow import fixture
    from ai.orchestration.graph_workflow import GraphRun
    from test_destination_resolution import answer

    data = fixture('trip_request')
    data['travelers']['children'] = None
    data['meta']['field_sources'].pop('travelers.children', None)
    graph = workflow()
    first = execute(graph, data)
    assert first.outputs['destination_agent'].selection_status == 'selected'
    assert first.state.status == 'clarifying'
    assert first.pending_questions[0].fields == ['travelers.children']
    assert 'constraint_planner' not in first.visits
    restored = GraphRun.model_validate_json(first.model_dump_json())
    answered = fixture('trip_request')
    answered['travelers']['children'] = 0
    resumed = execute(graph, answered, previous=restored, answer=answer(restored,
        answer_raw='Không có trẻ em', resolved_fields=['travelers.children'],
        declared_unknown_fields=[]))
    assert resumed.state.status == 'completed', resumed.errors
    assert resumed.visits['constraint_planner'] == 1
    assert resumed.state.artifacts.destination_result_id == first.state.artifacts.destination_result_id
