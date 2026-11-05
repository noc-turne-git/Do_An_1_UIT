"""Provider-independent conversation boundary and scripted offline adapter."""
from typing import Any, Literal, Protocol
from pydantic import Field, model_validator
from app.agents.contracts import Contract

class ToolCall(Contract):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, Any]

class LLMResponse(Contract):
    kind: Literal['final', 'tools', 'needs_input']
    output: Any = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    pending_fields: list[str] = Field(default_factory=list)
    provider_items: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode='after')
    def consistent(self):
        if (self.kind == 'tools') != bool(self.tool_calls):
            raise ValueError('Tool calls required only for tools response')
        if (self.kind == 'needs_input') != bool(self.pending_fields):
            raise ValueError('Pending fields required only for needs_input')
        if self.kind != 'final' and self.output is not None:
            raise ValueError('Only final may have output')
        return self

class LLMRequest(Contract):
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    output_schema: dict[str, Any]
    max_output_tokens: int = 4096
    max_output_bytes: int = 65536

class LLMAdapter(Protocol):
    async def respond(self, request: LLMRequest) -> LLMResponse: ...

class TransientLLMError(Exception):
    """Adapter explicitly signals a retryable provider failure; message is never logged."""

class ProviderError(Exception):
    """Safe stable code, never a provider payload."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)

class MockLLMAdapter:
    """Scripted response stream. Create one instance per invocation."""
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    async def respond(self, request):
        self.requests.append(request.model_copy(deep=True))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return LLMResponse.model_validate(response)

