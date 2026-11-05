"""Per-task identity propagation without changing stable component signatures."""
from contextvars import ContextVar
execution_identity: ContextVar[dict | None] = ContextVar('agent_execution_identity', default=None)
