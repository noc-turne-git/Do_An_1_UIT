"""Offline QA: contracts, component boundaries, API and storage infrastructure.

These tests do not certify the mock Engine/Validator business algorithms.
"""
import asyncio
import importlib
import inspect
import pkgutil
import socket
from copy import deepcopy
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateTable

import app
from ai.agents import interfaces
from app.core.config import Settings
from shared.errors import ApplicationError
from app.db.base import Base
from app.db.models import ArtifactRecord, TripRecord, WorkflowRecord
from app.db.session import Database, postgres_url
from app.main import create_app
from app.models import (CostedPlaceCandidate, DestinationResult, Itinerary,
                        PlaceCandidate, PlanningInput, TimeConstraints, TripRequest,
                        ValidationResult, WorkflowState)
from app.repositories.artifacts import ArtifactRepository
from ai.planning.constraint_planner import DeterministicConstraintPlanner, PlannerDefaults
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.graph_workflow import LangGraphOrchestrator, GraphRun
from ai.orchestration.workflow_state import STEPS

METHODS = ("parse", "select", "build", "find", "estimate", "build", "plan", "validate", "explain")
CONTRACTS = (
    (TripRequest, "trip_request", "trip"),
    (DestinationResult, "destination_result", "selected_region"),
    (PlaceCandidate, "place_candidates", "location"),
    (CostedPlaceCandidate, "costed_place_candidates", "price_status"),
    (TimeConstraints, "time_constraints", "days"),
    (PlanningInput, "planning_input", "candidate_places"),
    (Itinerary, "itinerary", "summary"),
    (ValidationResult, "validation_result", "recomputed"),
    (WorkflowState, None, "status"),
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Block external connections; Windows asyncio needs a loopback socketpair."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        return denied()
    def connect_ex(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect_ex(sock, address)
        return denied()
    def denied(*args, **kwargs):
        raise AssertionError("Network is forbidden in offline backend QA")
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "create_connection", denied)


def execute(components=None, data=None, **kwargs):
    return asyncio.run(LangGraphOrchestrator(components or mock_components(),
        defaults=fixture("planner_defaults")).run(
        TripRequest.model_validate(data or fixture("trip_request")),
        current_date=date(2026, 11, 2), **kwargs))


def contract_data(model, name):
    if name is None:
        return execute().state.model_dump(mode="json")
    data = fixture(name)
    return data[0] if isinstance(data, list) else data


@pytest.mark.parametrize("model,name,required", CONTRACTS)
@pytest.mark.parametrize("mutation", ["missing", "null", "extra", "version", "roundtrip"])
def test_all_contract_boundaries(model, name, required, mutation):
    data = contract_data(model, name)
    if mutation == "roundtrip":
        parsed = model.model_validate(data)
        assert model.model_validate_json(parsed.model_dump_json()) == parsed
        assert model.model_json_schema()["type"] == "object"
        return
    if mutation == "missing":
        del data[required]
    elif mutation == "null":
        # selected_region is nullable only for a non-selected result.
        data[required] = None
    elif mutation == "extra":
        data["unrecognized"] = 1
    else:
        data["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, 1.01])
def test_confidence_limits(value):
    data = fixture("costed_place_candidates")[0]
    data["price_confidence_score"] = value
    with pytest.raises(ValidationError):
        CostedPlaceCandidate.model_validate(data)


@pytest.mark.parametrize("mutation", ["latitude", "longitude", "rating", "duration", "nested_extra"])
def test_place_nested_invalid(mutation):
    data = fixture("place_candidates")[0]
    if mutation in {"latitude", "longitude"}:
        data["location"][mutation] = 181
    elif mutation == "rating":
        data["rating"] = 5.01
    elif mutation == "duration":
        data["visit_duration"]["confidence"] = None
    else:
        data["opening_hours"]["extra"] = True
    with pytest.raises(ValidationError):
        PlaceCandidate.model_validate(data)


def test_request_arrival_departure_timezone_order():
    data = fixture("trip_request")
    data["trip"]["arrival"]["datetime"] = "2026-11-14T10:00:00+07:00"
    data["trip"]["departure"]["datetime"] = "2026-11-14T02:00:00+00:00"
    with pytest.raises(ValidationError):
        TripRequest.model_validate(data)
    data["trip"]["departure"]["datetime"] = "2026-11-14T03:00:00+00:00"
    assert TripRequest.model_validate(data).trip.arrival.datetime == TripRequest.model_validate(data).trip.departure.datetime


@pytest.mark.parametrize("mutation", ["empty", "date_gap", "day_gap"])
def test_time_constraints_consecutive(mutation):
    data = fixture("time_constraints")
    if mutation == "empty":
        data["days"] = []
    elif mutation == "date_gap":
        data["days"][1]["date"] = "2026-11-17"
    else:
        data["days"][1]["day"] = 3
    with pytest.raises(ValidationError):
        TimeConstraints.model_validate(data)


@pytest.mark.parametrize("mutation", ["duplicate", "unknown_price", "matrix_mode", "matrix_negative", "matrix_duplicate"])
def test_planning_input_integrity(mutation):
    data = fixture("planning_input")
    if mutation == "duplicate":
        data["candidate_places"].append(deepcopy(data["candidate_places"][0]))
    elif mutation == "unknown_price":
        data["candidate_places"][0]["price_status"] = "UNKNOWN"
    elif mutation == "matrix_mode":
        data["travel_distance_matrix"]["mode"] = "walking"
    elif mutation == "matrix_negative":
        data["travel_time_matrix"]["values"][0][1] = -1
    else:
        data["travel_time_matrix"]["locations"][1] = data["travel_time_matrix"]["locations"][0]
    with pytest.raises(ValidationError):
        PlanningInput.model_validate(data)


def test_planning_coordinates_reject_out_of_range():
    """Open contract gap: Location rejects this, PlanningPlace currently accepts it."""
    data = fixture("planning_input")
    data["candidate_places"][0]["latitude"] = 999
    with pytest.raises(ValidationError):
        PlanningInput.model_validate(data)


def test_itinerary_status_agrees_with_solver_diagnostics():
    """Open contract gap: a feasible itinerary must not claim solver infeasible."""
    data = fixture("itinerary")
    data["diagnostics"]["solver_status"] = "infeasible"
    with pytest.raises(ValidationError):
        Itinerary.model_validate(data)


def test_planner_repeated_results_and_configuration_unchanged():
    request = TripRequest.model_validate(fixture("trip_request"))
    defaults = PlannerDefaults.model_validate(fixture("planner_defaults"))
    before = request.model_dump_json(), defaults.model_dump_json()
    planner = DeterministicConstraintPlanner()
    assert planner.plan(request, defaults) == planner.plan(request, defaults)
    assert before == (request.model_dump_json(), defaults.model_dump_json())


@pytest.mark.parametrize("step,method", list(zip(STEPS, METHODS)))
def test_exception_at_every_step_stops_downstream(step, method):
    components = mock_components()
    index = STEPS.index(step)
    setattr(getattr(components, step), method, AsyncMock(side_effect=RuntimeError("PRIVATE_SENTINEL")))
    spies = []
    for later, later_method in zip(STEPS[index + 1:], METHODS[index + 1:]):
        spy = AsyncMock(wraps=getattr(getattr(components, later), later_method))
        setattr(getattr(components, later), later_method, spy)
        spies.append(spy)
    result = execute(components)
    assert result.state.status == "failed"
    assert result.state.current_step == step
    assert result.state.completed_steps == list(STEPS[:index])
    assert result.errors[-1].message.startswith("[module_exception]")
    assert "PRIVATE_SENTINEL" not in result.model_dump_json()
    assert result.final_result is None
    for spy in spies:
        spy.assert_not_awaited()


def test_invalid_constraint_input_stops_before_places():
    components = mock_components()
    components.place_agent.find = AsyncMock()
    data = fixture("trip_request")
    data["daily_preferences"][0]["activity_start"] = "13:00"
    result = execute(components, data)
    assert result.state.status == "failed"
    assert result.state.current_step == "constraint_planner"
    assert result.errors[-1].message.startswith("[constraint_planning_failed]")
    components.place_agent.find.assert_not_awaited()


def test_place_cost_id_mismatch_stops_before_engine():
    components = mock_components()
    original = components.budget_module.estimate
    async def mismatched(*args, **kwargs):
        result = await original(*args, **kwargs)
        result.places[0].place_id = "different_id"
        return result
    components.budget_module.estimate = mismatched
    components.planning_engine.plan = AsyncMock()
    result = execute(components)
    assert result.state.status == "failed"
    assert result.state.current_step == "budget_module"
    assert result.errors[-1].message.startswith("[retry_or_revision_limit]")
    assert result.visits["place_agent"] > 1
    assert "planning_input_builder" not in result.state.completed_steps
    components.planning_engine.plan.assert_not_awaited()


def test_engine_trip_id_mismatch_stops_before_validator():
    components = mock_components()
    components.planning_engine.plan = AsyncMock(return_value=fixture("itinerary"))
    components.validator.validate = AsyncMock(wraps=components.validator.validate)
    result = execute(components)
    assert result.state.status == "failed"
    assert result.errors[-1].message.startswith("[planning_input_inconsistent]")
    components.validator.validate.assert_not_awaited()
    assert "planning_engine" not in result.state.completed_steps
    assert result.state.artifacts.itinerary_id is None


@pytest.mark.parametrize("step,method,ref", [
    ("planning_input_builder", "build", "planning_input_id"),
    ("validator", "validate", "validation_result_id"),
])
def test_cross_module_trip_id_rejected_before_saving(step, method, ref):
    components = mock_components()
    original = getattr(getattr(components, step), method)
    async def changed_id(*args, **kwargs):
        output = await original(*args, **kwargs)
        return output.model_copy(update={"trip_id": __import__("uuid").uuid4()})
    setattr(getattr(components, step), method, changed_id)
    result = execute(components)
    assert result.state.status == "failed"
    assert result.state.current_step == step
    assert result.errors[-1].message.startswith("[planning_input_inconsistent]")
    assert getattr(result.state.artifacts, ref) is None
    assert step not in result.state.completed_steps


def test_multiday_workflow_preserves_daily_constraints_and_rejects_unsupported_fixture():
    data = fixture("trip_request")
    daily = deepcopy(data["daily_preferences"][0])
    daily.update(day=3, activity_start="10:00", activity_end="16:00", return_by=None,
                 pace_override="busy")
    data["daily_preferences"].append(daily)
    for key, value in daily.items():
        if key != "day" and value is not None:
            data["meta"]["field_sources"][f"daily_preferences.1.{key}"] = "user"
    result = execute(data=data)
    times = result.artifacts[result.state.artifacts.time_constraints_id]
    planning = result.artifacts[result.state.artifacts.planning_input_id]
    for before, after in zip(times["days"], planning["time_constraints"]["days"]):
        assert {k: v for k, v in after.items() if k not in {"start_location_id", "end_location_id"}} == {
            k: v for k, v in before.items() if k not in {"start_location_id", "end_location_id"}}
    assert times["days"][1]["activity_window"]["end"]["value"] == "12:00"
    assert times["days"][2]["activity_window"]["start"]["value"] == "10:00"
    assert times["days"][2]["pace"] == {"value": "busy", "is_hard": True}
    assert result.state.status == "failed"
    assert result.state.current_step == "planning_engine"
    assert result.errors[-1].message.startswith("[mock_fixture_unsupported]")


def test_engine_error_status_cannot_complete_with_mock_accept():
    components = mock_components()
    async def engine(planning_input):
        output = fixture("itinerary")
        output.update(trip_id=planning_input.trip_id, status="error")
        output["diagnostics"]["solver_status"] = "error"
        return output
    components.planning_engine.plan = engine
    components.explainer.explain = AsyncMock()
    result = execute(components)
    assert result.state.status == "failed"
    assert result.attempts[-1].result == "error"
    components.explainer.explain.assert_not_awaited()


def test_corrupt_constructed_model_is_revalidated():
    components = mock_components()
    output = DestinationResult.model_validate(fixture("destination_result"))
    output = output.model_copy(update={"selection_status": "WRONG"})
    components.destination_agent.select = AsyncMock(return_value=output)
    result = execute(components)
    assert result.errors[-1].message.startswith("[output_schema_invalid]")
    assert result.state.artifacts.destination_result_id is None


def test_cancellation_propagates():
    components = mock_components()
    components.place_agent.find = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        execute(components)


def test_workflow_artifacts_roundtrip_and_snapshot_independence():
    result = execute()
    assert GraphRun.model_validate_json(result.model_dump_json()) == result
    assert len(set(result.state.artifacts.model_dump().values())) == 8
    first = result.checkpoints[0].model_dump_json()
    itinerary = result.artifacts[result.state.artifacts.itinerary_id]
    result.final_result.summary.summary_message = "changed locally"
    assert itinerary["summary"]["summary_message"] != "changed locally"
    result.state.completed_steps.clear()
    assert result.checkpoints[0].model_dump_json() == first


def test_protocol_signatures_accept_mock_adapters():
    components = mock_components()
    protocols = (interfaces.RequestParser, interfaces.DestinationAgent,
        interfaces.ConstraintPlanner, interfaces.PlaceAgent, interfaces.BudgetModule,
        interfaces.PlanningInputBuilder, interfaces.PlanningEngine, interfaces.Validator,
        interfaces.Explainer)
    for step, method, protocol in zip(STEPS, METHODS, protocols):
        adapter = getattr(getattr(components, step), method)
        signature = inspect.signature(getattr(protocol, method))
        args, kwargs = [], {}
        for name, parameter in signature.parameters.items():
            if name == "self":
                continue
            if parameter.kind == inspect.Parameter.KEYWORD_ONLY:
                kwargs[name] = object()
            else:
                args.append(object())
        inspect.signature(adapter).bind(*args, **kwargs)
        assert inspect.iscoroutinefunction(adapter)


def test_import_every_app_module():
    for module in pkgutil.walk_packages(app.__path__, "app."):
        importlib.import_module(module.name)


@pytest.mark.parametrize("body,status", [({}, 422), (None, 422), ([], 422)])
def test_api_invalid_request_envelope(body, status):
    with TestClient(create_app(Settings(_env_file=None, database_url=None))) as client:
        response = client.post("/api/v1/dev/workflows/mock-run", json=body)
        assert response.status_code == status
        assert response.json()["error"]["code"] == "invalid_request"


def test_api_lifespan_cors_preflight_and_failed_workflow():
    api = create_app(Settings(_env_file=None, database_url=None))
    with TestClient(api) as client:
        database = api.state.database
        database.dispose = MagicMock(wraps=database.dispose)
        for origin, status in [("http://localhost:5173", 200), ("https://denied.example", 400)]:
            response = client.options("/api/v1/dev/workflows/mock-run", headers={
                "Origin": origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type"})
            assert response.status_code == status
        assert client.put("/api/v1/health").status_code == 405
        assert client.get("/unknown").status_code == 404
        data = fixture("trip_request")
        data["budget"]["currency"] = "USD"
        response = client.post("/api/v1/dev/workflows/mock-run", json=data)
        assert response.status_code == 200  # Workflow domain failure, per demo API contract.
        assert response.json()["state"]["status"] == "failed"
        assert response.json()["final_result"] is None
        data["budget"]["amount"] = None
        assert client.post("/api/v1/dev/workflows/mock-run", json=data).json()["state"]["status"] == "clarifying"
    database.dispose.assert_called_once()


def test_config_environment_overrides_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("LLM_MODEL=file-model\n", encoding="utf-8")
    monkeypatch.setenv("LLM_MODEL", "environment-model")
    assert Settings(_env_file=env, database_url=None).llm_model == "environment-model"


def test_orm_metadata_postgresql_ddl_and_relationships():
    configure_mappers()
    assert len(Base.metadata.tables) == 20
    assert 'workflows' not in Base.metadata.tables and 'artifacts' not in Base.metadata.tables
    for table in Base.metadata.sorted_tables:
        assert 'CREATE TABLE' in str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert 'state' not in WorkflowRecord.__table__.c
    assert ArtifactRecord.__tablename__ == 'workflow_artifacts'


@pytest.mark.parametrize("failure", [False, True])
def test_session_transaction_context_and_cleanup(failure, monkeypatch):
    monkeypatch.setattr('app.db.session.event.listen', lambda *args: None)
    database = Database(Settings(_env_file=None, database_url=None))
    session = MagicMock()
    session.info = {}
    session.__enter__.return_value = session
    factory = MagicMock(return_value=session)
    database.sessions = factory
    transaction = session.begin.return_value
    generator = database.session()
    assert next(generator) is session
    if failure:
        with pytest.raises(RuntimeError, match="rollback"):
            generator.throw(RuntimeError("rollback"))
        assert transaction.__exit__.call_args.args[0] is RuntimeError
    else:
        with pytest.raises(StopIteration):
            next(generator)
        assert transaction.__exit__.call_args.args == (None, None, None)
    session.__exit__.assert_called_once()


def test_database_no_config_and_connection_error():
    database = Database(Settings(_env_file=None, database_url=None))
    with pytest.raises(ApplicationError) as error:
        next(database.session())
    assert error.value.code == "database_not_configured"
    database.sessions = MagicMock(side_effect=OperationalError("offline", {}, Exception("connection refused")))
    with pytest.raises(OperationalError):
        next(database.session())
    assert postgres_url("postgresql://u:p@localhost/test").drivername == "postgresql+psycopg"
    with pytest.raises(ValueError):
        postgres_url("sqlite:///test.db")


def test_repository_add_and_get_without_implicit_commit():
    from uuid import uuid4
    session, user, request = MagicMock(), uuid4(), uuid4()
    session.scalar.side_effect = [WorkflowRecord(request_id=request), None]
    repository = ArtifactRepository(session, user)
    payload = TripRequest.model_validate(fixture("trip_request"))
    record = repository.add(request, "trip_request", payload)
    assert record.payload == payload.model_dump(mode="json")
    session.add.assert_called_once_with(record)
    session.flush.assert_called_once()
    session.commit.assert_not_called()


def test_legacy_migration_is_preserved_without_execution():
    from pathlib import Path
    source = (Path(__file__).parents[1] / 'alembic/versions/0001_initial.py').read_text(encoding='utf-8')
    assert 'revision = "0001"' in source
    assert '"workflows"' in source and '"artifacts"' in source
