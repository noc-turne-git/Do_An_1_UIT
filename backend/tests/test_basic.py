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


def test_config_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    env = tmp_path / ".env"
    env.write_text("LLM_MODEL=from-file\n", encoding="utf-8")
    assert Settings(_env_file=env, database_url=None).llm_model == "from-file"


def test_invalid_config():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite:///test.db")


def test_mock_llm():
    class Output(BaseModel):
        answer: int

    mock = create_llm_client(Settings(_env_file=None), mock_response='{"answer":42}')
    assert asyncio.run(mock.generate("unused", Output)).answer == 42
    with pytest.raises(ValidationError):
        asyncio.run(MockLLMClient('{"answer":"bad"}').generate("unused", Output))
    with pytest.raises(ApplicationError):
        create_llm_client(Settings(_env_file=None, llm_provider="real-provider"))


def test_contracts():
    payload = json.loads((Path(__file__).resolve().parents[2] / "shared/samples/trip_request.json").read_text(encoding="utf-8"))
    request = TripRequest.model_validate(payload)
    assert request.budget.amount == 3000000
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        TripRequest.model_validate(payload)
    payload.pop("unexpected")
    payload["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        TripRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        CostRange(min=2, max=1)
    with pytest.raises(ValidationError):
        CostRange(min=0.5, max=1)
    with pytest.raises(ValidationError):
        TravelMatrix(locations=["a"], mode="walking", unit="minutes", values=[[0, 1]])


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
