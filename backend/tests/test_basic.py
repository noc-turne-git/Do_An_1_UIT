import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from shared.errors import ApplicationError
from app.main import create_app
from shared.contracts import CostRange, TravelMatrix, TripRequest
from ai.orchestration.llm import MockLLMClient, create_llm_client


@pytest.mark.smoke
def test_health_and_cors():
    with TestClient(create_app(Settings(_env_file=None, database_url=None))) as client:
        response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        denied = client.get("/api/v1/health", headers={"Origin": "https://untrusted.example"})
        assert "access-control-allow-origin" not in denied.headers
        assert client.get("/missing").json()["error"]["code"] == "http_error"


def test_config_environment(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("LLM_API_KEY", "test-secret")
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    settings = Settings(_env_file=None, database_url=None)
    assert settings.llm_model == "test-model"
    assert settings.llm_timeout_seconds == 4
    assert settings.cors_origins == ["http://localhost:3000"]
    assert "test-secret" not in repr(settings)


def test_exception_handlers():
    app = create_app(Settings(_env_file=None, database_url=None))

    @app.get("/test-error")
    def error():
        raise RuntimeError("private details")

    @app.get("/test-component-error")
    def component_error():
        raise ApplicationError("external_api_error", "Provider unavailable", retryable=True)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-error")
        assert response.status_code == 500
        assert "private details" not in response.text
        assert client.get("/test-component-error").status_code == 503
