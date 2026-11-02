"""Opt-in integration tests. Only a dedicated, empty TEST_DATABASE_URL is migrated."""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.config import Settings
from app.db.session import Database

ROOT = Path(__file__).parents[1]


def test_database_without_configuration():
    db = Database(Settings(_env_file=None, database_url=None))
    assert db.engine is None
    db.dispose()


@pytest.mark.postgres
def test_database_connection():
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("No DATABASE_URL or TEST_DATABASE_URL supplied")
    db = Database(Settings(_env_file=None, database_url=url))
    try:
        with db.engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        db.dispose()


@pytest.mark.postgres
def test_migration_on_empty_test_database():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated empty disposable PostgreSQL database")
    db = Database(Settings(_env_file=None, database_url=url))
    try:
        with db.engine.connect() as connection:
            assert not inspect(connection).get_table_names(), "Refusing to migrate a nonempty test database"
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["database_url"] = url
        upgraded = False
        try:
            command.upgrade(config, "head")
            upgraded = True
            with db.engine.begin() as connection:
                assert {"trips", "workflows", "artifacts"} <= set(inspect(connection).get_table_names())
                connection.execute(text("INSERT INTO trips (trip_id) VALUES ('trip_test')"))
                connection.execute(text("INSERT INTO workflows (request_id, trip_id, schema_version, state, revision) VALUES ('req_test', 'trip_test', '1.0', '{}'::jsonb, 1)"))
                connection.execute(text("INSERT INTO artifacts (artifact_id, request_id, kind, schema_version, payload) VALUES ('art_test','req_test','trip_request','1.0','{}'::jsonb)"))
            from sqlalchemy.exc import DBAPIError
            with pytest.raises(DBAPIError):
                with db.engine.begin() as connection:
                    connection.execute(text("UPDATE artifacts SET payload='{}'::jsonb WHERE artifact_id='art_test'"))
            verify_postgres_crud_constraints_and_rollback(db)
            command.check(config)
        finally:
            if upgraded:
                command.downgrade(config, "base")
        with db.engine.begin() as connection:
            assert set(inspect(connection).get_table_names()) == {"alembic_version"}
            # This test required an empty DB; remove its own version table too.
            connection.execute(text("DROP TABLE alembic_version"))
            assert not inspect(connection).get_table_names()
    finally:
        db.dispose()


def verify_postgres_crud_constraints_and_rollback(db):
    """Runs only inside the guarded, migrated disposable test database above."""
    from sqlalchemy.exc import IntegrityError, DBAPIError
    from app.db.models import TripRecord, WorkflowRecord
    from app.models import TripRequest
    from app.repositories.artifacts import ArtifactRepository
    import json

    request = TripRequest.model_validate(json.loads(
        (ROOT / "fixtures/trip_request.json").read_text(encoding="utf-8")))
    with db.sessions.begin() as session:
        trip = TripRecord(trip_id="orm_trip")
        workflow = WorkflowRecord(request_id="orm_request", trip=trip,
                                  schema_version="1.0", state={"status": "parsing"})
        session.add(workflow)
        session.flush()
        ArtifactRepository(session).add("orm_artifact", "orm_request", "trip_request", request)
    with db.sessions.begin() as session:
        workflow = session.get(WorkflowRecord, "orm_request")
        assert workflow.trip.trip_id == "orm_trip"
        assert len(workflow.artifacts) == 1
        assert ArtifactRepository(session).get("orm_artifact").payload == request.model_dump(mode="json")
        workflow.state = {"status": "planning"}
    with db.sessions() as session:
        workflow = session.get(WorkflowRecord, "orm_request")
        assert workflow.revision == 2 and workflow.state == {"status": "planning"}
    with pytest.raises(RuntimeError, match="rollback probe"):
        with db.sessions.begin() as session:
            session.add(TripRecord(trip_id="rolled_back_trip"))
            session.flush()
            raise RuntimeError("rollback probe")
    with db.sessions() as session:
        assert session.get(TripRecord, "rolled_back_trip") is None
    # Independent transactions so one expected violation cannot poison the next.
    for statement in [
        "INSERT INTO trips (trip_id) VALUES ('orm_trip')",
        "INSERT INTO workflows (request_id,trip_id,schema_version,state,revision) VALUES ('bad_fk','missing','1.0','{}'::jsonb,1)",
        "INSERT INTO workflows (request_id,trip_id,schema_version,state,revision) VALUES ('bad_revision','orm_trip','1.0','{}'::jsonb,0)",
        "INSERT INTO artifacts (artifact_id,request_id,kind,schema_version,payload) VALUES ('bad_kind','orm_request','invalid','1.0','{}'::jsonb)",
    ]:
        with pytest.raises(IntegrityError):
            with db.engine.begin() as connection:
                connection.execute(text(statement))
    with pytest.raises(DBAPIError):
        with db.engine.begin() as connection:
            connection.execute(text("DELETE FROM artifacts WHERE artifact_id='orm_artifact'"))
    with db.sessions.begin() as session:
        session.add(TripRecord(trip_id="delete_probe"))
    with db.sessions.begin() as session:
        session.delete(session.get(TripRecord, "delete_probe"))
    with db.sessions() as session:
        assert session.get(TripRecord, "delete_probe") is None
