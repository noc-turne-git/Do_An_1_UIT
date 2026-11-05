"""AI configuration independent of FastAPI and backend database settings."""
from pathlib import Path
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class AISettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    graph_max_clarifications: int = Field(default=3, ge=0)
    graph_max_revisions: int = Field(default=8, ge=0)
    graph_max_retries: int = Field(default=3, ge=0)
    graph_max_transitions: int = Field(default=80, ge=1)
    graph_max_candidates: int = Field(default=400, ge=100)
    llm_provider: str = "mock"
    agent_runtime_enabled: bool = False
    llm_model: str = "mock-model"
    llm_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None
    llm_timeout_seconds: float = Field(default=30, gt=0)

    @field_validator('openai_base_url', 'openai_model', mode='before')
    @classmethod
    def optional_openai_setting(cls, value):
        return value.strip() or None if isinstance(value, str) else value
