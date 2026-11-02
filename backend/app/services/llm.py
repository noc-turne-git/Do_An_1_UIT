from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import ApplicationError

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    async def generate(self, prompt: str, response_model: type[T]) -> T:
        """Return validated structured output; raise ValidationError or ApplicationError.

        Provider adapters must enforce settings.llm_timeout_seconds and translate
        network failures; no provider implementation is enabled in this phase.
        """
        ...


class MockLLMClient:
    def __init__(self, response: str = "{}"):
        self.response = response

    async def generate(self, prompt: str, response_model: type[T]) -> T:
        return response_model.model_validate_json(self.response)


def create_llm_client(settings: Settings, *, mock_response: str = "{}") -> LLMClient:
    if settings.llm_provider != "mock":
        raise ApplicationError("llm_provider_not_implemented", "Only the mock provider is available")
    return MockLLMClient(mock_response)
