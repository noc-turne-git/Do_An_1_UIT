"""Responses transport only; the shared harness owns execution and retry policy."""
import json
from copy import deepcopy

from openai import (AsyncOpenAI, APIConnectionError, APITimeoutError,
                    APIStatusError, AuthenticationError, RateLimitError)

from app.agents.llm import LLMResponse, ToolCall, TransientLLMError, ProviderError


def strict_schema(schema):
    # SDK's own conversion preserves $refs, optional fields and nested models.
    from openai.lib._pydantic import _ensure_strict_json_schema
    result = deepcopy(schema)
    return _ensure_strict_json_schema(result, path=(), root=result)


class OpenAILLMAdapter:
    def __init__(self, *, model, api_key=None, timeout=30, client=None, base_url=None):
        self.model = model
        self._owns_client = client is None
        source = client if client is not None else AsyncOpenAI(
            api_key=api_key, timeout=timeout, max_retries=0, base_url=base_url)
        # Even injected real SDK clients must not retry below the harness.
        options = {'max_retries': 0}
        if base_url is not None:
            options['base_url'] = base_url
        self.client = source.with_options(**options) if hasattr(source, 'with_options') else source

    async def aclose(self):
        if self._owns_client:
            await self.client.close()

    async def respond(self, request):
        items = []
        for message in request.messages:
            role = message['role']
            if role == 'assistant' and 'provider_items' in message:
                items.extend(deepcopy(message['provider_items']))
            elif role == 'assistant' and 'tool_calls' in message:
                items.extend(dict(type='function_call', call_id=c['id'], name=c['name'],
                                  arguments=json.dumps(c['arguments'])) for c in message['tool_calls'])
            elif role == 'tool':
                items.append(dict(type='function_call_output', call_id=message['call_id'],
                    output=json.dumps({'trust': 'untrusted_tool_result',
                                       'output': message['output'], 'error': message['error']})))
            else:
                content = message.get('content', '')
                items.append(dict(role=role, content=content if isinstance(content, str) else json.dumps(content)))
        try:
            response = await self.client.responses.create(
                model=self.model, input=items, store=False,
                include=['reasoning.encrypted_content'],
                tools=[dict(type='function', name=t['name'], description=t['description'],
                            parameters=strict_schema(t['input_schema']), strict=True) for t in request.tools],
                text={'format': {'type': 'json_schema', 'name': 'agent_output',
                                 'schema': strict_schema(request.output_schema), 'strict': True}},
                max_output_tokens=request.max_output_tokens)
        except AuthenticationError:
            raise ProviderError('LLM_AUTHENTICATION_ERROR') from None
        except APITimeoutError:
            raise TimeoutError() from None
        except (RateLimitError, APIConnectionError):
            raise TransientLLMError('Provider temporarily unavailable') from None
        except APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code in (408, 409):
                raise TransientLLMError('Provider temporarily unavailable') from None
            raise ProviderError('LLM_REQUEST_ERROR') from None
        if response.status != 'completed':
            raise ProviderError('LLM_INCOMPLETE_RESPONSE')
        output = [item.model_dump(mode='json', exclude_none=True) for item in response.output]
        if len(json.dumps(output).encode()) > request.max_output_bytes:
            raise ProviderError('MAX_OUTPUT_BYTES')
        usage = response.usage
        tokens = {key: getattr(usage, key, 0) for key in ('input_tokens', 'output_tokens', 'total_tokens')} if usage else {}
        calls, texts = [], []
        try:
            for item in output:
                if item['type'] == 'function_call':
                    calls.append(ToolCall(id=item['call_id'], name=item['name'],
                                          arguments=json.loads(item['arguments'])))
                elif item['type'] == 'message':
                    for content in item.get('content', []):
                        if content['type'] == 'refusal':
                            raise ProviderError('LLM_REFUSAL')
                        if content['type'] == 'output_text':
                            texts.append(content['text'])
            if calls:
                return LLMResponse(kind='tools', tool_calls=calls, provider_items=output, token_usage=tokens)
            return LLMResponse(kind='final', output=json.loads(''.join(texts)), token_usage=tokens)
        except (ValueError, KeyError, TypeError):
            raise ProviderError('INVALID_LLM_RESPONSE') from None
