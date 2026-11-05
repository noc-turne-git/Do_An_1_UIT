"""Offline acceptance using real SDK models/transport; live access is opt-in."""
import asyncio
import json
import os
from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI
from openai.types.responses import Response
from pydantic import BaseModel, Field

from ai.agents.contracts import AgentContext, AgentDefinition, AgentStatus
from ai.agents.llm import LLMRequest
from ai.agents.llm.openai import OpenAILLMAdapter
from ai.agents.runtime.factory import create_agent_harness
from ai.agents.skills import SkillLoader, SkillRegistry
from ai.agents.tools import ToolDefinition, ToolRegistry
from ai.config import AISettings as Settings


class Value(BaseModel):
    value: int = Field(ge=0)


def response(items, status='completed'):
    return Response.model_validate(dict(id='resp_test', object='response', created_at=0,
        model='test-model', status=status, output=items, parallel_tool_calls=True,
        tool_choice='auto', tools=[], usage=dict(input_tokens=10, output_tokens=5, total_tokens=15,
            input_tokens_details={'cached_tokens': 0, 'cache_write_tokens': 0},
            output_tokens_details={'reasoning_tokens': 0})))


def final(value=3):
    return response([dict(type='message', id='msg_1', role='assistant', status='completed',
        content=[dict(type='output_text', text=json.dumps({'value': value}), annotations=[])])])


def call(identity, value=1):
    return dict(type='function_call', id='fc_' + identity, call_id=identity,
                name='echo', arguments=json.dumps({'value': value}), status='completed')


class FakeClient:
    def __init__(self, script):
        self.script, self.requests = iter(script), []
        self.responses = self

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        item = next(self.script)
        if isinstance(item, BaseException):
            raise item
        return item


def setup(client=None, **limits):
    tools, skills = ToolRegistry(), SkillRegistry()
    effects = []
    async def echo(value):
        effects.append(value.value)
        return value
    tools.register(ToolDefinition(name='echo', description='Mock echo', input_schema=Value,
                                  output_schema=Value, handler=echo, side_effects=True))
    skills.register(SkillLoader.from_markdown('---\n{"name":"sample","description":"Mock skill","required_tools":["echo"]}\n---\nUse echo for data, then return the schema.'))
    definition = AgentDefinition(name='generic', description='Acceptance', system_prompt='Use tools.',
        allowed_tools={'echo'}, allowed_skills={'sample'}, output_schema=Value, limits=limits)
    settings = Settings(_env_file=None, llm_provider='openai', llm_model='test-model')
    harness = create_agent_harness(definition, settings, tools=tools, skills=skills, client=client)
    return definition, harness, effects


def test_generic_multistep_multiple_calls_and_reasoning_continuity():
    reasoning = dict(type='reasoning', id='rs_1', summary=[], encrypted_content='opaque')
    client = FakeClient([response([reasoning, call('a'), call('b', 2)]),
                         response([call('a'), call('c', 3)]), final()])
    definition, harness, effects = setup(client)
    result = asyncio.run(harness.run(definition, AgentContext(request_id='correlation', input_data={}), skills=['sample']))
    assert result.status == AgentStatus.SUCCESS and result.output == Value(value=3)
    assert effects == [1, 2, 3]  # a is cached, never executed twice
    assert result.token_usage['total_tokens'] == 45
    sent = client.requests[-1]
    assert reasoning in sent['input']
    outputs = [i for i in sent['input'] if i.get('type') == 'function_call_output']
    assert [i['call_id'] for i in outputs] == ['a', 'b', 'a', 'c']
    assert json.loads(outputs[0]['output'])['trust'] == 'untrusted_tool_result'
    assert sent['text']['format']['schema']['additionalProperties'] is False
    assert sent['tools'][0]['parameters']['required'] == ['value']
    assert sent['store'] is False


@pytest.mark.parametrize('item,code', [
    (response([], 'incomplete'), 'LLM_INCOMPLETE_RESPONSE'),
    (response([dict(type='message', id='msg', role='assistant', status='completed',
                   content=[dict(type='refusal', refusal='No')])]), 'LLM_REFUSAL'),
    (response([dict(type='message', id='msg', role='assistant', status='completed',
                   content=[dict(type='output_text', text='bad json', annotations=[])])]), 'INVALID_LLM_RESPONSE'),
    (final(-1), 'INVALID_AGENT_OUTPUT'),
    (response([dict(call('a'), arguments='[]')]), 'INVALID_LLM_RESPONSE'),
])
def test_invalid_responses(item, code):
    definition, harness, _ = setup(FakeClient([item]))
    result = asyncio.run(harness.run(definition, AgentContext(request_id='r', input_data={})))
    assert result.error.code == code


@pytest.mark.parametrize('status,code,count', [
    (401, 'LLM_AUTHENTICATION_ERROR', 1), (400, 'LLM_REQUEST_ERROR', 1),
    (429, 'LLM_TRANSIENT_ERROR', 2), (503, 'LLM_TRANSIENT_ERROR', 2),
])
def test_real_sdk_http_mapping_and_no_nested_retries(status, code, count):
    async def check():
        requests = []
        async def handle(request):
            requests.append(json.loads(request.content))
            return httpx.Response(status, json={'error': {'message': 'secret credential', 'type': 'test'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            async with AsyncOpenAI(api_key='fake', http_client=http, max_retries=7) as client:
                definition, harness, _ = setup(client, max_retries=1, retry_backoff=0)
                result = await harness.run(definition, AgentContext(request_id='r', input_data={}))
                assert result.error.code == code
                assert len(requests) == count
                assert 'secret credential' not in result.model_dump_json()
    asyncio.run(check())


@pytest.mark.parametrize('limit,code', [
    ({'max_context_bytes': 1}, 'MAX_CONTEXT_BYTES'),
    ({'max_output_bytes': 1}, 'MAX_OUTPUT_BYTES'),
    ({'max_total_tokens': 1}, 'MAX_TOTAL_TOKENS'),
])
def test_limits(limit, code):
    definition, harness, effects = setup(FakeClient([final()]), **limit)
    result = asyncio.run(harness.run(definition, AgentContext(request_id='r', input_data={})))
    assert result.error.code == code and not effects


def test_skill_cannot_expand_tools():
    client = FakeClient([])
    definition, harness, _ = setup(client)
    definition.allowed_tools = frozenset()
    result = asyncio.run(harness.run(definition, AgentContext(request_id='r', input_data={}), skills=['sample']))
    assert result.error.code == 'SKILL_TOOL_PERMISSION_CONFLICT' and not client.requests


def test_factory_mock_and_configuration_errors():
    definition = AgentDefinition(name='mock', description='Mock', system_prompt='Test', output_schema=Value)
    harness = create_agent_harness(definition, Settings(_env_file=None, llm_provider='mock'),
                                   mock_responses=[dict(kind='final', output={'value': 1})])
    assert asyncio.run(harness.run(definition, AgentContext(request_id='r', input_data={}))).output.value == 1
    with pytest.raises(ValueError):
        create_agent_harness(definition, SimpleNamespace(llm_provider='invalid'))


@pytest.mark.parametrize('mode,code', [('network', 'LLM_TRANSIENT_ERROR'), ('timeout', 'LLM_TIMEOUT')])
def test_real_sdk_transport_failures(mode, code):
    async def check():
        attempts = []
        async def handle(request):
            attempts.append(1)
            if mode == 'timeout':
                raise httpx.ReadTimeout('sensitive transport details', request=request)
            raise httpx.ConnectError('sensitive transport details', request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            async with AsyncOpenAI(api_key='fake', http_client=http) as client:
                definition, harness, _ = setup(client, max_retries=1, retry_backoff=0)
                result = await harness.run(definition, AgentContext(request_id='r', input_data={}))
                assert result.error.code == code and len(attempts) == 2
                assert 'sensitive' not in result.model_dump_json()
    asyncio.run(check())


def test_openai_cancellation_propagates():
    async def check():
        started, cleaned = asyncio.Event(), asyncio.Event()
        class Slow(FakeClient):
            async def create(self, **kwargs):
                started.set()
                try:
                    await asyncio.sleep(10)
                finally:
                    cleaned.set()
        definition, harness, _ = setup(Slow([]))
        task = asyncio.create_task(harness.run(definition, AgentContext(request_id='r', input_data={})))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set()
    asyncio.run(check())


def test_successful_real_sdk_transport_serialization():
    async def check():
        seen = []
        async def handle(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=final().model_dump(mode='json'))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            async with AsyncOpenAI(api_key='fake', http_client=http) as client:
                definition, harness, _ = setup(client)
                result = await harness.run(definition, AgentContext(request_id='r', input_data={}), skills=['sample'])
                assert result.output.value == 3 and len(seen) == 1
                assert seen[0]['input'][1]['role'] == 'developer'
                assert seen[0]['max_output_tokens'] == definition.limits.max_output_tokens
    asyncio.run(check())


@pytest.mark.skipif(os.getenv('RUN_OPENAI_LIVE') != '1', reason='LIVE_NOT_RUN: explicitly set RUN_OPENAI_LIVE=1')
def test_live_generic_acceptance():
    settings = Settings()
    model = os.getenv('OPENAI_TEST_MODEL') or settings.openai_model or settings.llm_model
    key = settings.openai_api_key or settings.llm_api_key
    if not key or model == 'mock-model':
        pytest.skip('LIVE_NOT_RUN: configure API key and OPENAI_MODEL (or OPENAI_TEST_MODEL)')
    async def check():
        adapter = OpenAILLMAdapter(model=model, api_key=key.get_secret_value(),
            base_url=settings.openai_base_url, timeout=settings.llm_timeout_seconds)
        definition, harness, effects = setup(FakeClient([]))
        harness.llm = adapter
        definition.system_prompt = ('Call echo with value 1 and value 2 in the first step. '
            'After receiving both results call echo with value 3. After that return {"value":3}.')
        try:
            result = await harness.run(definition, AgentContext(request_id='live-test', input_data={}), skills=['sample'])
            assert result.status == AgentStatus.SUCCESS and result.output.value == 3
            assert sorted(effects[:2]) == [1, 2] and effects[2:] == [3]
            assert len([e for e in result.events if e.event == 'llm_response']) >= 3
        finally:
            await adapter.aclose()
    asyncio.run(check())
