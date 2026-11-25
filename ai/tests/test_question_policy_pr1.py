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


def test_three_adults_does_not_prove_zero_children():
    request = apply_changes(empty_request(), ParserOutput(summary='3 người lớn', changes=[
        Change(path='travelers.adults', value_json='3', decision='SPECIFIED')]))
    assert request.travelers.adults == 3
    assert request.travelers.children is None
    assert request.meta.field_sources['travelers.adults'] == 'user'
    assert 'travelers.children' not in request.meta.field_sources


def test_parser_fabricated_zero_children_is_removed_for_three_adults():
    from ai.orchestration.request_parser import apply_traveler_evidence
    previous = empty_request()
    parsed = apply_changes(previous, ParserOutput(summary='3 người lớn', changes=[
        Change(path='travelers.adults', value_json='3', decision='SPECIFIED'),
        Change(path='travelers.children', value_json='0', decision='SPECIFIED')]))
    corrected = apply_traveler_evidence(parsed, '3 người lớn', previous)
    assert corrected.travelers.adults == 3
    assert corrected.travelers.children is None
    assert corrected.meta.field_sources['travelers.adults'] == 'user'
    assert 'travelers.children' not in corrected.meta.field_sources


def test_parser_fabricated_family_counts_are_removed():
    from ai.orchestration.request_parser import apply_traveler_evidence
    previous = empty_request()
    parsed = apply_changes(previous, ParserOutput(summary='cả nhà', changes=[
        Change(path='travelers.adults', value_json='2', decision='SPECIFIED'),
        Change(path='travelers.children', value_json='1', decision='SPECIFIED')]))
    corrected = apply_traveler_evidence(parsed, 'cả nhà', previous)
    assert corrected.travelers.adults is corrected.travelers.children is None
    assert 'travelers.adults' not in corrected.meta.field_sources
    embedded = apply_traveler_evidence(parsed, 'Cho cả nhà đi Đà Lạt 3 ngày', previous)
    assert embedded.travelers.adults is embedded.travelers.children is None


def test_optional_collection_fields_do_not_block_selected_destination():
    from ai.orchestration.mock_workflow import fixture
    data = fixture('trip_request')
    for group, field in [('budget', 'amount'), ('budget', 'scope')]:
        data[group][field] = None
        data['meta']['field_sources'].pop(f'{group}.{field}', None)
    run = execute(workflow(), data)
    assert not run.pending_questions
    assert 'budget.amount' in run.outputs['request_parser'].missing_fields
    assert run.state.status == 'completed'


def test_declined_required_traveler_count_is_not_asked_again():
    from ai.orchestration.mock_workflow import fixture
    data = fixture('trip_request')
    data['travelers']['adults'] = None
    data['meta']['field_sources'].pop('travelers.adults', None)
    data['meta'].setdefault('field_decisions', {})['travelers.adults'] = 'DECLINED'
    run = execute(workflow(), data)
    assert all('travelers.adults' not in q.fields for q in run.pending_questions)


def test_me_and_parents_yields_three_adults_with_inferred_provenance():
    from ai.orchestration.request_parser import apply_traveler_evidence
    request = apply_traveler_evidence(empty_request(), 'tôi và ba mẹ')
    assert request.travelers.adults == 3
    assert request.travelers.children is None
    assert request.meta.field_sources['travelers.adults'] == 'inferred'
    assert 0 < request.meta.field_confidences['travelers.adults'] < 1
    assert request.meta.field_decisions['travelers.adults'] == 'SPECIFIED'


def test_negated_adult_count_keeps_parser_correction_and_user_provenance():
    previous = apply_changes(empty_request(), ParserOutput(summary='3 adults', changes=[
        Change(path='travelers.adults', value_json='3', decision='SPECIFIED')]))
    parsed = apply_changes(previous, ParserOutput(summary='corrected to 2', changes=[
        Change(path='travelers.adults', value_json='2', decision='SPECIFIED')]))
    corrected = apply_traveler_evidence(parsed, 'Không phải 3 người lớn, mà 2 người lớn', previous)
    assert corrected.travelers.adults == 2
    assert corrected.meta.field_sources['travelers.adults'] == 'user'
    assert 'travelers.adults' not in corrected.meta.field_confidences
    assert previous.travelers.adults == 3


def test_direct_adult_count_corrects_previous_turn():
    previous = apply_changes(empty_request(), ParserOutput(summary='3 adults', changes=[
        Change(path='travelers.adults', value_json='3', decision='SPECIFIED')]))
    parsed = apply_changes(previous, ParserOutput(summary='2 adults', changes=[
        Change(path='travelers.adults', value_json='2', decision='SPECIFIED')]))
    corrected = apply_traveler_evidence(parsed, '2 người lớn', previous)
    assert corrected.travelers.adults == 2
    assert corrected.meta.field_sources['travelers.adults'] == 'user'
    assert previous.travelers.adults == 3


def test_inferred_family_count_does_not_replace_confirmed_user_count():
    previous = apply_changes(empty_request(), ParserOutput(summary='2 adults', changes=[
        Change(path='travelers.adults', value_json='2', decision='SPECIFIED')]))
    parsed = apply_changes(previous, ParserOutput(summary='me and parents', changes=[
        Change(path='travelers.adults', value_json='3', decision='SPECIFIED'),
        Change(path='travelers.children', value_json='0', decision='SPECIFIED')]))
    corrected = apply_traveler_evidence(parsed, 'tôi và ba mẹ', previous)
    assert corrected.travelers.adults == 2
    assert corrected.travelers.children is None
    assert corrected.meta.field_sources['travelers.adults'] == 'user'
    assert 'travelers.adults' not in corrected.meta.field_confidences


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
    assert resumed.visits['destination_agent'] == 1


@pytest.mark.parametrize('path', ['trip.start_date', 'trip.end_date',
                                   'travelers.adults', 'travelers.children'])
def test_selected_destination_blocks_only_missing_planning_inputs(path):
    from ai.orchestration.mock_workflow import fixture

    data = fixture('trip_request')
    group, field = path.split('.')
    data[group][field] = None
    data['meta']['field_sources'].pop(path, None)
    run = execute(workflow(), data)
    assert run.state.status == 'clarifying'
    assert run.pending_questions[0].fields == [path]
    assert 'constraint_planner' not in run.visits
