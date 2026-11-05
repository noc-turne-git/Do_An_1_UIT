"""Registered callables only. Tool failures are data; cancellation propagates."""
import asyncio
import inspect
from time import monotonic
from typing import Any, Callable
from pydantic import Field, TypeAdapter, ValidationError, field_validator
from ai.agents.contracts import Contract, AgentError

class ToolDefinition(Contract):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: Any
    output_schema: Any
    handler: Callable
    timeout: float = Field(default=5, gt=0, allow_inf_nan=False)
    side_effects: bool = True

    @field_validator('input_schema', 'output_schema')
    @classmethod
    def schema(cls, value):
        TypeAdapter(value).json_schema()
        return value

class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, tool: ToolDefinition):
        if tool.name in self._tools:
            raise ValueError(f'Duplicate tool: {tool.name}')
        self._tools[tool.name] = tool

    def lookup(self, name):
        return self._tools.get(name)

    def list(self):
        return tuple(self._tools.values())

class ToolResult(Contract):
    call_id: str
    tool_name: str
    output: Any = None
    error: AgentError | None = None
    duration: float = 0

class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, name, arguments, *, allowed_tools, call_id, timeout=5):
        start = monotonic()
        def fail(code):
            return ToolResult(call_id=call_id, tool_name=name,
                error=AgentError(code=code, message='Tool execution failed'), duration=monotonic()-start)
        if name not in allowed_tools:
            return fail('TOOL_NOT_ALLOWED')
        tool = self.registry.lookup(name)
        if tool is None:
            return fail('TOOL_NOT_FOUND')
        try:
            validated = TypeAdapter(tool.input_schema).validate_python(arguments)
        except (ValidationError, TypeError, ValueError):
            return fail('INVALID_TOOL_ARGUMENTS')
        try:
            async with asyncio.timeout(min(timeout, tool.timeout)):
                if inspect.iscoroutinefunction(tool.handler):
                    raw = await tool.handler(validated)
                else:
                    raw = await asyncio.to_thread(tool.handler, validated)
                    if inspect.isawaitable(raw):
                        raw = await raw
        except TimeoutError:
            return fail('TOOL_TIMEOUT')
        except Exception:
            return fail('TOOL_EXECUTION_ERROR')
        try:
            output = TypeAdapter(tool.output_schema).validate_python(raw)
            output = TypeAdapter(tool.output_schema).dump_python(output, mode='json')
        except (ValidationError, TypeError, ValueError):
            return fail('INVALID_TOOL_OUTPUT')
        return ToolResult(call_id=call_id, tool_name=name, output=output, duration=monotonic()-start)
