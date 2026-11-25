import pytest

from ai.orchestration.request_parser import Change, ParserOutput, apply_changes, empty_request


def apply_destination_change(path, decision, value_json='null', previous=None):
    return apply_changes(previous or empty_request(), ParserOutput(
        summary='Updated destination',
        changes=[Change(path=path, value_json=value_json, decision=decision)],
    ))


def test_specified_destination_city_is_an_explicit_user_selection():
    request = apply_destination_change('destination.city', 'SPECIFIED', '"Da Nang"')

    assert (request.destination.selection_intent, request.destination.selection_authority,
            request.destination.selection_mode, request.destination.city) == (
                'EXPLICIT', 'USER', 'explicit', 'Da Nang')


@pytest.mark.parametrize('path', [
    'destination.selection_intent', 'destination.selection_authority',
    'destination.destination_source', 'destination.selection_provenance',
])
def test_parser_cannot_write_destination_policy_paths(path):
    with pytest.raises(ValueError, match='Selection policy is owned by CODE'):
        apply_destination_change(path, 'SPECIFIED', '"EXPLICIT"')


def test_deferred_destination_selection_preserves_existing_selection_state():
    previous = apply_destination_change('destination.city', 'AI_DECIDE')
    before = previous.destination.model_dump()

    request = apply_destination_change('destination.selection_mode', 'DEFERRED', previous=previous)

    assert request.destination.model_dump() == before
    assert request.meta.field_decisions['destination.selection_mode'] == 'DEFERRED'


def test_implicit_selection_mode_alone_does_not_grant_destination_delegation():
    request = apply_destination_change('destination.selection_mode', 'SPECIFIED', '"implicit"')

    assert (request.destination.selection_intent, request.destination.selection_authority) == (
        'UNSPECIFIED', None)
