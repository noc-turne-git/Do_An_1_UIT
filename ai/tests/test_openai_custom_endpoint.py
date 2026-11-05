"""Custom gateway is an endpoint configuration, not a separate provider."""
import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from ai.agents.contracts import AgentContext, AgentDefinition
from ai.agents.runtime.factory import create_agent_harness
from ai.config import AISettings as Settings
from test_openai_infrastructure import Value, call, final, response


@pytest.mark.parametrize('base_url', [
    'https://gateway.example/v1', 'https://gateway.example/v1/',
    'http://localhost:20128/api/v1',
])
def test_custom_endpoint_real_sdk_multistep(monkeypatch, base_url):
    async def check():
        seen = []
        script = iter([response([call('a'), call('b', 2)]), response([call('c', 3)]), final()])
        async def handle(request):
            seen.append(request)
            return httpx.Response(200, json=next(script).model_dump(mode='json'))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            def sdk(**kwargs):
                return AsyncOpenAI(http_client=http, **kwargs)
            monkeypatch.setattr('ai.agents.llm.openai.AsyncOpenAI', sdk)
            from ai.agents.tools import ToolRegistry, ToolDefinition
            tools = ToolRegistry()
            tools.register(ToolDefinition(name='echo', description='Mock', input_schema=Value,
                output_schema=Value, handler=lambda v: v, side_effects=False))
            definition = AgentDefinition(name='gateway_test', description='Mock', system_prompt='Use echo',
                output_schema=Value, allowed_tools={'echo'})
            settings = Settings(_env_file=None, llm_provider='openai',
                openai_base_url=base_url, openai_model='gateway/model-id',
                llm_model='legacy-model', openai_api_key='gateway-key')
            harness = create_agent_harness(definition, settings, tools=tools)
            try:
                result = await harness.run(definition, AgentContext(request_id='test', input_data={'query': 'test'}))
                assert result.output == Value(value=3)
                assert len(seen) == 3
                assert all(str(r.url) == base_url.rstrip('/') + '/responses' for r in seen)
                assert all(r.method == 'POST' and r.headers['authorization'] == 'Bearer gateway-key' for r in seen)
                bodies = [json.loads(r.content) for r in seen]
                assert all(b['model'] == 'gateway/model-id' for b in bodies)
                assert bodies[0]['tools'][0]['type'] == 'function'
                assert bodies[0]['text']['format']['type'] == 'json_schema'
                assert bodies[0]['text']['format']['strict'] is True
                assert bodies[0]['input'][-1]['content'] == '{"query": "test"}'
                outputs = [i for i in bodies[2]['input'] if i.get('type') == 'function_call_output']
                assert [o['call_id'] for o in outputs] == ['a', 'b', 'c']
                assert json.loads(outputs[0]['output'])['output'] == {'value': 1}
                assert harness.llm.client.max_retries == 0
            finally:
                await harness.llm.aclose()
    asyncio.run(check())


@pytest.mark.parametrize('status', [400, 404, 405, 422, 501])
def test_incompatible_endpoint_fails_without_protocol_fallback(status):
    async def check():
        seen = []
        async def handle(request):
            seen.append(request)
            return httpx.Response(status, json={'error': {'message': 'Feature unavailable'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            async with AsyncOpenAI(api_key='fake', base_url='https://gateway.example/v1', http_client=http) as client:
                settings = Settings(_env_file=None, llm_provider='openai', openai_model='gateway-model')
                definition = AgentDefinition(name='test', description='Test', system_prompt='Test',
                    output_schema=Value, limits={'max_retries': 0})
                harness = create_agent_harness(definition, settings, client=client)
                result = await harness.run(definition, AgentContext(request_id='r', input_data={}))
                expected = 'LLM_TRANSIENT_ERROR' if status == 501 else 'LLM_REQUEST_ERROR'
                assert result.error.code == expected
                assert len(seen) == 1 and seen[0].url.path == '/v1/responses'
    asyncio.run(check())


def test_environment_settings_and_legacy_model_fallback(monkeypatch):
    for name, value in dict(OPENAI_BASE_URL=' https://gateway.example/v1 ',
                            OPENAI_MODEL=' gateway/model ', OPENAI_API_KEY='test-key',
                            LLM_PROVIDER='openai').items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)
    assert settings.openai_base_url == 'https://gateway.example/v1'
    assert settings.openai_model == 'gateway/model'
    assert settings.openai_api_key.get_secret_value() == 'test-key'
    definition = AgentDefinition(name='test', description='Test', system_prompt='Test', output_schema=Value)
    from test_openai_infrastructure import FakeClient
    harness = create_agent_harness(definition, settings, client=FakeClient([]))
    assert harness.llm.model == 'gateway/model'
    settings.openai_model = None
    settings.llm_model = 'legacy'
    assert create_agent_harness(definition, settings, client=FakeClient([])).llm.model == 'legacy'
    assert Settings(_env_file=None, openai_base_url='', openai_model=' ').openai_base_url is None


def test_sdk_default_and_injected_endpoint_override(monkeypatch):
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)
    async def check():
        from ai.agents.llm.openai import OpenAILLMAdapter
        adapter = OpenAILLMAdapter(model='test', api_key='fake')
        try:
            assert str(adapter.client.base_url) == 'https://api.openai.com/v1/'
        finally:
            await adapter.aclose()
        async with AsyncOpenAI(api_key='fake', base_url='https://original.example/v1') as client:
            adapter = OpenAILLMAdapter(model='test', client=client, base_url='https://override.example/v1')
            assert str(adapter.client.base_url) == 'https://override.example/v1/'
            assert str(client.base_url) == 'https://original.example/v1/'
            assert adapter.client.max_retries == 0
    asyncio.run(check())
