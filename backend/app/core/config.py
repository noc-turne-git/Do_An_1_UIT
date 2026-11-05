from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")
    app_name: str = "Travel Planning API"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    database_url: SecretStr | None = None
    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
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

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: SecretStr | None) -> SecretStr | None:
        if value and make_url(value.get_secret_value()).get_backend_name() != "postgresql":
            raise ValueError("DATABASE_URL must use PostgreSQL")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
