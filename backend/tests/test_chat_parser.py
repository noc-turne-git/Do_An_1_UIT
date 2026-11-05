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
from test_chat_api import setup_client


def output(path, value, decision='SPECIFIED'):
    return ParserOutput(summary='Mình đã ghi nhận yêu cầu của bạn.',
        changes=[Change(path=path, value_json=json.dumps(value), decision=decision)])


def complete():
    return TripRequest.model_validate(fixture('trip_request'))


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


@pytest.mark.parametrize('decision,missing', [('UNKNOWN', True), ('DEFERRED', True),
    ('FLEXIBLE', False), ('AI_DECIDE', False), ('NO_PREFERENCE', False)])
def test_decision_roundtrip_and_essential_travelers(decision, missing):
    request = apply_changes(complete(), output('preferences.pace', None, decision))
    restored = TripRequest.model_validate(request.model_dump(mode='json'))
    assert ('preferences.pace' in restored.missing_fields) == missing
    assert request.preferences.pace is None
    essential = apply_changes(complete(), output('travelers.adults', None, decision))
    assert 'travelers.adults' in essential.missing_fields
    assert essential.meta.parser_status == 'clarifying'


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
    assert no_adults.meta.parser_status == 'clarifying'


def run_script(content, response):
    adapter = MockLLMAdapter([response])
    with patch('ai.orchestration.request_parser.create_agent_harness', return_value=AgentHarness(adapter)):
        result = asyncio.run(parse_turn(Settings(_env_file=None), previous=complete(),
            content=content, history=[dict(role='assistant', content='Bạn thích nhịp độ nào?')],
            request_id='r1', conversation_id='c1'))
    return result, adapter


@pytest.mark.parametrize('text,decision', [('Không biết', 'UNKNOWN'), ('Sao cũng được', 'FLEXIBLE'),
    ('Bạn chọn giúp', 'AI_DECIDE'), ('Không quan trọng', 'NO_PREFERENCE'), ('Để sau', 'DEFERRED')])
def test_harness_decision_contract(text, decision):
    (request, reply, error), adapter = run_script(text, dict(kind='final',
        output=output('preferences.pace', None, decision).model_dump()))
    assert not error and request.meta.field_decisions['preferences.pace'] == decision
    assert 'nhịp độ' not in reply if decision in {'FLEXIBLE', 'AI_DECIDE', 'NO_PREFERENCE', 'DEFERRED'} else True
    assert adapter.requests[0].messages[-1]['content']['content'] == text
    assert adapter.requests[0].messages[-1]['content']['history']


def test_relative_dates_context_and_schema():
    (_, _, error), adapter = run_script('Ngày mai', dict(kind='final',
        output=ParserOutput(summary='Đã ghi nhận.', changes=[]).model_dump()))
    assert not error
    context = adapter.requests[0].messages[-1]['content']
    assert context['timezone'] == 'Asia/Ho_Chi_Minh'
    assert len(context['current_date']) == 10 and context['trip_request_schema']


def test_relative_date_result_and_grouped_questions():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    tomorrow = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date() + timedelta(days=1)
    response = ParserOutput(summary='Đi từ ngày mai trong ba ngày.', changes=[
        Change(path='trip.start_date', value_json=json.dumps(tomorrow.isoformat()), decision='SPECIFIED'),
        Change(path='trip.end_date', value_json=json.dumps((tomorrow + timedelta(days=2)).isoformat()), decision='SPECIFIED'),
        Change(path='trip.duration_days', value_json='3', decision='SPECIFIED'),
        Change(path='travelers.adults', value_json='null', decision='UNKNOWN'),
        Change(path='travelers.children', value_json='null', decision='UNKNOWN')],
        questions=[dict(fields=['travelers.adults', 'travelers.children'],
                        question='Nhóm có bao nhiêu người lớn và trẻ em?')])
    (request, reply, error), _ = run_script('Ngày mai đi ba ngày, chưa biết số người',
                                          dict(kind='final', output=response.model_dump()))
    assert not error and request.trip.start_date == tomorrow and request.trip.duration_days == 3
    assert reply.count('bao nhiêu') == 1
    assert reply == 'Nhóm có bao nhiêu người lớn và trẻ em?'


def test_ready_request_keeps_confirmation_without_followup():
    response = ParserOutput(summary='Đã đủ thông tin chuyến đi.', changes=[],
        questions=[dict(fields=['travelers.adults'], question='Có bao nhiêu người lớn?')])
    (request, reply, error), _ = run_script('Đi bằng xe máy, không có trẻ em',
                                          dict(kind='final', output=response.model_dump()))
    assert not error and request.meta.parser_status == 'ready'
    assert reply == response.summary


@pytest.mark.parametrize('intent,text,reply', [
    ('conversation', 'Xin chào', 'Chào bạn! Mình là Travelio, rất vui được trò chuyện với bạn.'),
    ('conversation', 'Cảm ơn nhé', 'Rất vui vì giúp được bạn!'),
    ('travel_advice', 'Đà Lạt có gì chơi?', 'Bạn có thể ghé hồ Xuân Hương và khám phá các quán cà phê.'),
])
@pytest.mark.parametrize('state', ['empty', 'collecting', 'ready'])
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


def test_explicit_planning_intent_collects_missing_requirements():
    response = output('travelers.adults', None, 'UNKNOWN')
    response.intent = 'trip_planning'
    (request, reply, error), _ = run_script('Lập lịch trình cho mình',
                                          dict(kind='final', output=response.model_dump()))
    assert error is None and request.meta.parser_status == 'clarifying'
    assert 'travelers.adults' in request.missing_fields
    assert 'bao nhiêu người lớn' in reply
    assert response.summary not in reply


def test_conflicts_and_invalid_change_are_safe_errors():
    for response, code in [
        (dict(summary='Mâu thuẫn.', changes=[], conflicting_input=True), 'CONFLICTING_INPUT'),
        (dict(summary='Sai JSON.', changes=[dict(path='budget.amount', value_json='bad', decision='SPECIFIED')]), 'INVALID_PARSER_JSON'),
        (dict(summary='Sai ngày.', changes=[dict(path='trip.end_date', value_json='"2020-01-01"', decision='SPECIFIED')]), 'INVALID_TRIP_REQUEST'),
    ]:
        (request, reply, error), _ = run_script('Yêu cầu mâu thuẫn', dict(kind='final', output=response))
        assert request is None and reply is None and error == code


def test_harness_invalid_output_and_provider_failure():
    for response in [dict(kind='final', output={'bad': 'json'}), RuntimeError('secret-provider-key')]:
        (request, reply, error), _ = run_script('Đi chơi', response)
        assert request is None and reply is None and error


def test_api_ready_and_error_preserve_state_and_do_not_create_trip():
    app, session, _ = setup_client()
    with patch('app.api.chat.parse_turn') as parser, TestClient(app) as client:
        ready = apply_changes(complete(), ParserOutput(summary='Đã đủ thông tin.', changes=[]))
        parser.return_value = (ready, 'Đã đủ thông tin, chưa tạo lịch trình.', None)
        first = client.post('/api/v1/chat/messages', json={'content': 'Đi Đà Lạt'}).json()
        assert first['parser_status'] == 'ready' and first['assistant']['role'] == 'assistant'
        assert first['trip_summary']['role'] == 'assistant'
        assert 'tóm tắt chuyến đi' in first['trip_summary']['content']
        assert ready.destination.city in first['trip_summary']['content']
        conversation = session.add.call_args_list[0].args[0]
        session.scalar.return_value = conversation
        parser.side_effect = ValueError('sk-private-do-not-log')
        second = client.post('/api/v1/chat/messages', json={
            'conversation_id': first['conversation_id'], 'content': 'Sửa ngày'}).json()
        assert second['parser_status'] == 'error'
        assert second['trip_summary'] is None
        assert conversation.trip_request['destination'] == ready.model_dump(mode='json')['destination']
        assert conversation.trip_id is None and conversation.request_id is None


def test_summary_is_saved_once_and_updated_when_ready_details_change():
    from app.db.models import MessageRecord
    app, session, _ = setup_client()
    ready = apply_changes(complete(), ParserOutput(summary='Đã đủ.', changes=[]))
    with patch('app.api.chat.parse_turn') as parser, TestClient(app) as client:
        parser.return_value = (ready, 'Đã ghi nhận.', None)
        first = client.post('/api/v1/chat/messages', json={'content': 'Lên kế hoạch'}).json()
        conversation = session.add.call_args_list[0].args[0]
        session.scalar.return_value = conversation
        saved = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], MessageRecord)]
        assert len(saved) == 3
        assert saved[-1].content == first['trip_summary']['content']
        body = {'conversation_id': first['conversation_id'], 'content': 'Đúng rồi'}
        unchanged = client.post('/api/v1/chat/messages', json=body).json()
        assert unchanged['trip_summary'] is None
        updated = apply_changes(ready, output('travelers.adults', 4))
        parser.return_value = (updated, 'Đã đổi số người.', None)
        changed = client.post('/api/v1/chat/messages', json=body).json()
        assert '4 người lớn' in changed['trip_summary']['content']


def test_incomplete_request_does_not_emit_summary():
    app, _, _ = setup_client()
    draft = apply_changes(empty_request(), output('destination.city', 'Đà Lạt'))
    with patch('app.api.chat.parse_turn', return_value=(draft, 'Bạn đi ngày nào?', None)), TestClient(app) as client:
        response = client.post('/api/v1/chat/messages', json={'content': 'Đà Lạt'})
    assert response.status_code == 201
    assert response.json()['trip_summary'] is None


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
