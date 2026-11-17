"""AI configuration independent of FastAPI and backend database settings."""
from pathlib import Path
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from ai.orchestration.clarification_policy import (
    ApprovedPreferenceDefaults, ClarificationPolicy, TripRequestDefaults,
)

class AISettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    graph_max_clarifications: int = Field(default=3, ge=0)
    max_destination_rounds: int = Field(default=2, ge=2, le=2)
    clarification_defaults: TripRequestDefaults = Field(default_factory=TripRequestDefaults)
    clarification_preference_defaults: ApprovedPreferenceDefaults | None = None
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
    openai_include_encrypted_reasoning: bool = False
    llm_timeout_seconds: float = Field(default=30, gt=0)

    def build_clarification_policy(self) -> ClarificationPolicy:
        # Revalidate and detach configuration, including nested values.
        return ClarificationPolicy.model_validate(dict(
            max_clarification_rounds=self.graph_max_clarifications,
            max_destination_rounds=self.max_destination_rounds,
            trip_request_defaults=self.clarification_defaults.model_dump(by_alias=True),
            preference_defaults=(self.clarification_preference_defaults.model_dump()
                                 if self.clarification_preference_defaults is not None else None)))

    @field_validator('openai_base_url', 'openai_model', mode='before')
    @classmethod
    def optional_openai_setting(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator('llm_provider', mode='before')
    @classmethod
    def normalize_llm_provider(cls, value):
        return value.strip().lower() if isinstance(value, str) else value
