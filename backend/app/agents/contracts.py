"""Provider independent execution contracts; business schemas stay in models.contracts."""
from enum import StrEnum
from typing import Any, Protocol
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)

class AgentStatus(StrEnum):
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'
    NEEDS_INPUT = 'NEEDS_INPUT'

class AgentError(Contract):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False

class ExecutionLimits(Contract):
    max_steps: int = Field(default=8, ge=1)
    max_tool_calls: int = Field(default=12, ge=0)
    max_retries: int = Field(default=2, ge=0)
    timeout: float = Field(default=30, gt=0, allow_inf_nan=False)
    llm_timeout: float = Field(default=10, gt=0, allow_inf_nan=False)
    tool_timeout: float = Field(default=5, gt=0, allow_inf_nan=False)
    max_context_bytes: int = Field(default=262144, ge=1)
    max_output_bytes: int = Field(default=65536, ge=1)
    max_output_tokens: int = Field(default=4096, ge=1)
    max_total_tokens: int = Field(default=100000, ge=1)
    retry_backoff: float = Field(default=0.1, ge=0, allow_inf_nan=False)

class AgentDefinition(Contract):
    name: str = Field(min_length=1, pattern=r'^\S+$')
    description: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    allowed_tools: frozenset[str] = frozenset()
    allowed_skills: frozenset[str] = frozenset()
    output_schema: Any
    limits: ExecutionLimits = Field(default_factory=ExecutionLimits)

    @field_validator('output_schema')
    @classmethod
    def schema(cls, value):
        TypeAdapter(value).json_schema()
        return value

class AgentContext(Contract):
    request_id: str = Field(min_length=1)
    conversation_id: str | None = None
    user_id: str | None = None
    input_data: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)

class ExecutionEvent(Contract):
    event: str
    agent_name: str
    request_id: str
    step: int = 0
    tool_name: str | None = None
    duration: float = 0
    error_code: str | None = None

class AgentResult(Contract):
    status: AgentStatus
    output: Any = None
    error: AgentError | None = None
    pending_fields: list[str] = Field(default_factory=list)
    events: list[ExecutionEvent] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode='after')
    def consistent(self):
        if (self.status == AgentStatus.FAILED) != (self.error is not None):
            raise ValueError('Only FAILED requires an error')
        if self.status != AgentStatus.SUCCESS and self.output is not None:
            raise ValueError('Only SUCCESS has output')
        if (self.status == AgentStatus.NEEDS_INPUT) != bool(self.pending_fields):
            raise ValueError('Only NEEDS_INPUT requires pending fields')
        return self

class AgentInterface(Protocol):
    async def run(self, definition: AgentDefinition, context: AgentContext, *, skills=()) -> AgentResult: ...
