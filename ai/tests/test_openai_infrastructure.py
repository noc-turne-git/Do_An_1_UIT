"""Offline acceptance using real SDK models/transport; live access is opt-in."""
import asyncio
import json
import os
from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI
from openai.types.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ai.agents.contracts import AgentContext, AgentDefinition, AgentStatus
from ai.agents.llm import LLMRequest
from ai.agents.llm.openai import OpenAILLMAdapter
from ai.agents.runtime.factory import create_agent_harness
from ai.agents.skills import SkillLoader, SkillRegistry
from ai.agents.tools import ToolDefinition, ToolRegistry
from ai.config import AISettings as Settings


class Value(BaseModel):
    model_config = ConfigDict(extra='forbid')
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
    assert 'include' not in sent


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


def test_skill_cannot_expand_tools():
    client = FakeClient([])
    definition, harness, _ = setup(client)
    definition.allowed_tools = frozenset()
    result = asyncio.run(harness.run(definition, AgentContext(request_id='r', input_data={}), skills=['sample']))
    assert result.error.code == 'SKILL_TOOL_PERMISSION_CONFLICT' and not client.requests


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
