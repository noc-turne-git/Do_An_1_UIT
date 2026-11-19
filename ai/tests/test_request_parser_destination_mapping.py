import pytest

from ai.orchestration.request_parser import Change, ParserOutput, apply_changes, empty_request


def apply_destination_change(path, decision, value_json='null', previous=None):
    return apply_changes(previous or empty_request(), ParserOutput(
        summary='Updated destination',
        changes=[Change(path=path, value_json=value_json, decision=decision)],
    ))


@pytest.mark.parametrize(
    ('decision', 'intent', 'authority', 'mode'),
    [
        ('UNKNOWN', 'USER_UNKNOWN', 'USER', 'ambiguous'),
        ('FLEXIBLE', 'ANY_DESTINATION', 'USER', 'implicit'),
        ('NO_PREFERENCE', 'ANY_DESTINATION', 'USER', 'implicit'),
        ('AI_DECIDE', 'DELEGATE_SELECTION', 'AGENT', 'implicit'),
    ],
)
def test_destination_city_decision_maps_to_the_established_selection_policy(
        decision, intent, authority, mode):
    request = apply_destination_change('destination.city', decision)

    assert (request.destination.selection_intent, request.destination.selection_authority,
            request.destination.selection_mode) == (intent, authority, mode)
    assert request.destination.city is None
    assert request.meta.field_decisions['destination.selection_mode'] == decision


def test_specified_destination_city_is_an_explicit_user_selection():
    request = apply_destination_change('destination.city', 'SPECIFIED', '"Da Nang"')

    assert (request.destination.selection_intent, request.destination.selection_authority,
            request.destination.selection_mode, request.destination.city) == (
                'EXPLICIT', 'USER', 'explicit', 'Da Nang')


def test_deferred_destination_selection_preserves_existing_selection_state():
    previous = apply_destination_change('destination.city', 'AI_DECIDE')
    before = previous.destination.model_dump()

    request = apply_destination_change('destination.selection_mode', 'DEFERRED', previous=previous)

    assert request.destination.model_dump() == before
    assert request.meta.field_decisions['destination.selection_mode'] == 'DEFERRED'


def test_unrelated_destination_field_decision_does_not_delegate_destination_selection():
    request = apply_destination_change('destination.preferred_areas', 'AI_DECIDE')

    assert (request.destination.selection_intent, request.destination.selection_authority,
            request.destination.selection_mode) == ('UNSPECIFIED', None, None)
    assert request.meta.field_decisions['destination.preferred_areas'] == 'AI_DECIDE'


@pytest.mark.parametrize('decision', ['UNKNOWN', 'FLEXIBLE', 'AI_DECIDE', 'NO_PREFERENCE', 'DEFERRED'])
def test_non_specified_decisions_reject_non_null_values(decision):
    with pytest.raises(ValueError, match='Undecided fields cannot contain invented values'):
        apply_destination_change('destination.city', decision, '"invented"')


def test_implicit_selection_mode_alone_does_not_grant_destination_delegation():
    request = apply_destination_change('destination.selection_mode', 'SPECIFIED', '"implicit"')

    assert (request.destination.selection_intent, request.destination.selection_authority) == (
        'UNSPECIFIED', None)
