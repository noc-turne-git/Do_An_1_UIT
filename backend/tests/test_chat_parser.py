import asyncio
import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from ai.agents.llm import MockLLMAdapter
from ai.agents.runtime.harness import AgentHarness
from app.core.config import Settings
from shared.contracts import TripRequest
from ai.orchestration.mock_workflow import fixture
from ai.orchestration.request_parser import (ParserOutput, Change, apply_changes, empty_request,
                                         parse_turn)
from ai.orchestration.turns import TurnResult
from test_chat_api import setup_client


def output(path, value, decision='SPECIFIED'):
    return ParserOutput(summary='Mình đã ghi nhận yêu cầu của bạn.',
        changes=[Change(path=path, value_json=json.dumps(value), decision=decision)])


def complete():
    from support import confirmed_trip_request
    return TripRequest.model_validate(confirmed_trip_request())


def test_complete_missing_and_preserving_corrections():
    ready = apply_changes(complete(), ParserOutput(summary='Đã ghi nhận.', changes=[]))
    assert ready.meta.parser_status == 'ready'
    draft = apply_changes(empty_request(), output('destination.city', 'Đà Lạt'))
    assert draft.meta.parser_status == 'clarifying'
    updated = apply_changes(draft, output('travelers.adults', 2))
    assert updated.destination.city == 'Đà Lạt'
    assert 'travelers.adults' not in updated.missing_fields
    corrected = apply_changes(updated, output('travelers.adults', 3))
    assert corrected.travelers.adults == 3 and updated.travelers.adults == 2


@pytest.mark.parametrize('decision,intent,authority', [
    ('UNKNOWN', 'USER_UNKNOWN', 'USER'),
    ('FLEXIBLE', 'ANY_DESTINATION', 'USER'),
    ('AI_DECIDE', 'DELEGATE_SELECTION', 'USER'),
])
def test_destination_decision_semantics(decision, intent, authority):
    request = apply_changes(empty_request(), output('destination.city', None, decision))
    assert request.destination.selection_intent == intent
    assert request.destination.selection_authority == authority
    assert request.destination.city is None
    assert 'destination.selection_mode' not in request.missing_fields
    assert request.destination.selection_provenance is not None


def test_invalid_json_dates_zero_travelers_and_protected_paths():
    with pytest.raises(ValueError):
        apply_changes(complete(), ParserOutput(summary='Lỗi.', changes=[
            Change(path='budget.amount', value_json='not json', decision='SPECIFIED')]))
    with pytest.raises(ValidationError):
        apply_changes(complete(), output('trip.end_date', '2026-01-01'))
    with pytest.raises(ValueError):
        apply_changes(complete(), output('meta.raw_prompt', 'override'))
    with pytest.raises(ValueError):
        apply_changes(complete(), output('budget.amount', 123, 'AI_DECIDE'))
    no_adults = apply_changes(complete(), output('travelers.adults', 0))
    assert no_adults.meta.parser_status == 'ready'
    assert no_adults.travelers.adults == 0
    assert 'travelers.adults' not in no_adults.missing_fields


def run_script(content, response):
    adapter = MockLLMAdapter([response])
    with patch('ai.orchestration.request_parser.create_agent_harness', return_value=AgentHarness(adapter)):
        result = asyncio.run(parse_turn(Settings(_env_file=None), previous=complete(),
            content=content, history=[dict(role='assistant', content='Bạn thích nhịp độ nào?')],
            request_id='r1', conversation_id='c1'))
    return result, adapter


def test_relative_dates_context_and_schema():
    (_, _, error), adapter = run_script('Ngày mai', dict(kind='final',
        output=ParserOutput(summary='Đã ghi nhận.', changes=[]).model_dump()))
    assert not error
    context = adapter.requests[0].messages[-1]['content']
    assert context['timezone'] == 'Asia/Ho_Chi_Minh'
    assert len(context['current_date']) == 10 and context['trip_request_schema']


@pytest.mark.parametrize('intent,text,reply', [
    ('conversation', 'Xin chào', 'Chào bạn! Mình là Travelio, rất vui được trò chuyện với bạn.'),
    ('conversation', 'Cảm ơn nhé', 'Rất vui vì giúp được bạn!'),
    ('travel_advice', 'Đà Lạt có gì chơi?', 'Bạn có thể ghé hồ Xuân Hương và khám phá các quán cà phê.'),
])
@pytest.mark.parametrize('state', ['empty', 'ready'])
def test_non_planning_turn_answers_without_changing_trip(intent, text, reply, state):
    previous = (empty_request() if state == 'empty' else
                apply_changes(complete(), output('travelers.adults', None, 'UNKNOWN'))
                if state == 'collecting' else complete())
    before = previous.model_dump(mode='json')
    # Even stray model changes/questions must not start or modify planning.
    response = ParserOutput(intent=intent, summary=reply,
        changes=[Change(path='travelers.adults', value_json='9', decision='SPECIFIED')],
        questions=[dict(fields=['travelers.adults'], question='Có bao nhiêu người lớn?')])
    adapter = MockLLMAdapter([dict(kind='final', output=response.model_dump())])
    with patch('ai.orchestration.request_parser.create_agent_harness', return_value=AgentHarness(adapter)):
        request, actual_reply, error = asyncio.run(parse_turn(Settings(_env_file=None),
            previous=previous, content=text, history=[], request_id='r1', conversation_id='c1'))
    assert error is None and actual_reply == reply
    assert request.model_dump(mode='json') == before
    assert previous.model_dump(mode='json') == before
    assert request is not previous


def test_harness_invalid_output_and_provider_failure():
    for response in [dict(kind='final', output={'bad': 'json'}), RuntimeError('secret-provider-key')]:
        (request, reply, error), _ = run_script('Đi chơi', response)
        assert request is None and reply is None and error


def test_logs_exclude_credentials_and_raw_prompt(caplog):
    from app.core.logging import log_parser_turn, log_message
    request = complete()
    request.meta.raw_prompt = 'Bearer private-token'
    request.destination.city = 'sk-secret-value'
    logger = __import__('logging').getLogger('conversation')
    old = logger.propagate
    logger.propagate = True
    try:
        with caplog.at_level('INFO'):
            log_parser_turn(request_id='r', conversation_id='c', message_id='m',
                            trip_request=request, error_code=None)
            log_message(message_id='m', role='user', content='Bearer private-token')
        assert 'private-token' not in caplog.text and 'sk-secret-value' not in caplog.text
        assert 'chat.parser_turn' in caplog.text
    finally:
        logger.propagate = old
