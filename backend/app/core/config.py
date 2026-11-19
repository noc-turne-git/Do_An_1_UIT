from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from ai.config import AISettings
from ai.logging import DEFAULT_TRACE_ROOT

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(AISettings):
    """Inherits canonical clarification config and validation from AISettings.

    Backend env loading must not redefine the fixed destination budget or supply
    unapproved preference defaults. build_clarification_policy() returns a copy.
    """
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")
    app_name: str = "Travel Planning API"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    ai_trace_root: Path = DEFAULT_TRACE_ROOT
    ai_log_file: Path | None = None  # Deprecated location alias; no file is written.
    log_max_bytes: int = Field(default=5_242_880, ge=1)
    log_backup_count: int = Field(default=5, ge=1)
    diagnostic_retention_days: int = Field(default=30, ge=1, le=3650)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    database_url: SecretStr | None = None
    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: SecretStr | None) -> SecretStr | None:
        if value and make_url(value.get_secret_value()).get_backend_name() != "postgresql":
            raise ValueError("DATABASE_URL must use PostgreSQL")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
