"""Approval-service credential recovery, including real PostgreSQL login failures.

Vault replies are explicit fixtures. The integration tests use only the isolated
lcnc_lo1_test_* database fixture and temporary restricted LOGIN roles.
"""
import ast
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from test_lo1_classification_postgres import database_connection

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def database(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "automation_credential_test", ROOT / "governance-automation/app/database.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = {
        "vault_addr": "http://vault.test:8200",
        "db_role": "governance-automation",
        "postgres_host": "postgres.test",
        "postgres_port": 5432,
        "postgres_db": "lcnc_lo1_test_credentials",
        "postgres_sslmode": "disable",
    }
    monkeypatch.setattr(module, "_config", lambda: config)
    monkeypatch.setattr(module, "_runtime_token", lambda _: "fixture-token")
    module._db_username = "cached-user"
    module._db_password = "cached-password"
    module._db_valid_until = float("inf")
    return module


def replacement(database, monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url))
        assert method == "GET"
        assert url.endswith("/v1/database/creds/governance-automation")
        assert kwargs["token"] == "fixture-token"
        return {
            "lease_duration": 900,
            "data": {"username": "replacement-user", "password": "replacement-password"},
        }

    monkeypatch.setattr(database, "_vault_request", request)
    return calls


@pytest.mark.parametrize("error", [
    psycopg.OperationalError('FATAL: password authentication failed for user "cached-user"'),
    psycopg.OperationalError('FATAL: role "cached-user" does not exist'),
    psycopg.errors.InvalidPassword("rejected credential"),
])
def test_rejected_login_gets_one_replacement(database, monkeypatch, error):
    calls = replacement(database, monkeypatch)
    attempts = []
    connection = object()

    def connect(**kwargs):
        attempts.append(kwargs)
        if kwargs["user"] == "cached-user":
            raise error
        return connection

    monkeypatch.setattr(database.psycopg, "connect", connect)
    assert database.get_connection() is connection
    assert [item["user"] for item in attempts] == ["cached-user", "replacement-user"]
    assert len(calls) == 1
    assert all(item["connect_timeout"] == 5 for item in attempts)
    assert database.get_connection() is connection
    assert len(calls) == 1  # The replacement is reused by subsequent requests.


@pytest.mark.parametrize("message", [
    "connection refused", "timeout expired", "could not translate host name",
    "no pg_hba.conf entry for host", "SSL certificate verify failed",
])
def test_other_connection_errors_do_not_issue_credentials(database, monkeypatch, message):
    calls = replacement(database, monkeypatch)
    attempts = []
    error = psycopg.OperationalError(message)

    def connect(**kwargs):
        attempts.append(kwargs)
        raise error

    monkeypatch.setattr(database.psycopg, "connect", connect)
    with pytest.raises(psycopg.OperationalError) as caught:
        database.get_connection()
    assert caught.value is error
    assert len(attempts) == 1
    assert calls == []
    assert database._db_username == "cached-user"


def test_second_rejected_login_stops_and_is_not_cached(database, monkeypatch):
    calls = replacement(database, monkeypatch)
    attempts = []

    def connect(**kwargs):
        attempts.append(kwargs["user"])
        raise psycopg.OperationalError("password authentication failed")

    monkeypatch.setattr(database.psycopg, "connect", connect)
    with pytest.raises(psycopg.OperationalError):
        database.get_connection()
    assert attempts == ["cached-user", "replacement-user"]
    assert len(calls) == 1
    assert database._db_username is None
    assert database._db_password is None


def test_vault_failure_stops_before_another_database_attempt(database, monkeypatch):
    attempts = []

    def connect(**kwargs):
        attempts.append(kwargs["user"])
        raise psycopg.OperationalError("password authentication failed")

    def request(*args, **kwargs):
        raise TimeoutError("fixture Vault outage")

    monkeypatch.setattr(database.psycopg, "connect", connect)
    monkeypatch.setattr(database, "_vault_request", request)
    with pytest.raises(TimeoutError, match="fixture Vault outage"):
        database.get_connection()
    assert attempts == ["cached-user"]
    assert database._db_username is None


def test_concurrent_rejections_share_one_replacement(database, monkeypatch):
    calls = replacement(database, monkeypatch)
    barrier = Barrier(4)

    def connect(**kwargs):
        if kwargs["user"] == "cached-user":
            barrier.wait(timeout=5)
            raise psycopg.OperationalError("password authentication failed")
        return kwargs["user"]

    monkeypatch.setattr(database.psycopg, "connect", connect)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: database.get_connection(), range(4)))
    assert results == ["replacement-user"] * 4
    assert len(calls) == 1


def test_statement_errors_are_not_replayed(database, monkeypatch):
    calls = replacement(database, monkeypatch)
    statements = []

    def execute(statement):
        statements.append(statement)
        raise psycopg.OperationalError("password authentication failed")

    monkeypatch.setattr(database.psycopg, "connect", lambda **kwargs: SimpleNamespace(execute=execute))
    connection = database.get_connection()
    with pytest.raises(psycopg.OperationalError):
        connection.execute("fixture approval action")
    assert statements == ["fixture approval action"]
    assert calls == []


@pytest.mark.parametrize("ttl", [1, 5, 20, 30, 60, 900])
def test_cache_never_outlives_short_lease(database, monkeypatch, ttl):
    database._db_username = None
    database._db_password = None
    clock = [1000.0]
    monkeypatch.setattr(database, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    calls = []

    def request(*args, **kwargs):
        calls.append(ttl)
        clock[0] += 0.1  # Account for time spent obtaining the lease.
        return {"lease_duration": ttl, "data": {"username": "user", "password": "password"}}

    monkeypatch.setattr(database, "_vault_request", request)
    database._database_credentials(database._config())
    assert 1000.0 < database._db_valid_until < 1000.0 + ttl
    clock[0] = 1000.0 + ttl
    database._database_credentials(database._config())
    assert len(calls) == 2


@pytest.mark.parametrize("failure", ["expired_password", "wrong_password", "deleted_role"])
def test_training_gate_recovers_real_login_without_bypassing_training(
    database_connection, database, monkeypatch, failure,
):
    """The actual HTTP handler and training SQL run as a restricted LOGIN role."""
    app_id, decision_id, approval_id, assignment_id = [uuid4() for _ in range(4)]
    role = "lo1_credential_" + uuid4().hex
    rejected_role = "lo1_rejected_" + uuid4().hex
    password = "disposable-" + uuid4().hex
    with database_connection() as admin:
        admin.autocommit = True
        for name in ("014_governance_approvals.sql", "016_training_assignments.sql"):
            admin.execute((ROOT / "database/migrations" / name).read_text())
        config = database._config()
        config.update(postgres_host=admin.info.host, postgres_port=admin.info.port,
                      postgres_db=admin.info.dbname)
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(password)))
        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        admin.execute(sql.SQL("GRANT SELECT ON applications, approval_requests, training_assignments TO {}").format(
            sql.Identifier(role)))
    try:
        with database_connection() as admin:
            admin.execute("INSERT INTO applications (id, external_id, name, platform) VALUES (%s,%s,'Credential test','appsmith')",
                          (app_id, app_id.hex))
            admin.execute("INSERT INTO governance_decisions (id,application_id,outcome,status) VALUES (%s,%s,'SECURITY_REVIEW','pending_review')",
                          (decision_id, app_id))
            admin.execute("""INSERT INTO approval_requests (id,application_id,governance_decision_id,
                route_type,required_role,governance_outcome,due_at)
                VALUES (%s,%s,%s,'security_review','Security/GRC Reviewer','SECURITY_REVIEW',NOW()+INTERVAL '1 day')""",
                          (approval_id, app_id, decision_id))
            admin.execute("""INSERT INTO training_assignments (id,application_id,module_id,
                trigger_control,trigger_status,subject_id,due_at)
                VALUES (%s,%s,'fixture-training','fixture-control','required','fixture-owner',NOW()+INTERVAL '1 day')""",
                          (assignment_id, app_id))
            admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} VALID UNTIL {}").format(
                sql.Identifier(rejected_role), sql.Literal(password),
                sql.Literal("2000-01-01" if failure == "expired_password" else "infinity")))
            if failure == "deleted_role":
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(rejected_role)))

        bad_password = "incorrect-fixture-password" if failure == "wrong_password" else password
        # Guard against trust authentication making a password regression pass falsely.
        try:
            probe = psycopg.connect(host=config["postgres_host"], port=config["postgres_port"],
                                    dbname=config["postgres_db"], user=rejected_role,
                                    password=bad_password, connect_timeout=5)
        except psycopg.OperationalError:
            pass
        else:
            probe.close()
            pytest.skip("Password rejection test requires password-authenticated test PostgreSQL")

        database._db_username = rejected_role
        database._db_password = bad_password
        calls = []

        def request(*args, **kwargs):
            calls.append("replacement")
            return {"lease_duration": 900, "data": {"username": role, "password": password}}

        monkeypatch.setattr(database, "_vault_request", request)
        source = ast.parse((ROOT / "governance-automation/app/main.py").read_text())
        names = {"approval_training_gate", "get_training_gate", "health"}
        nodes = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
        for node in nodes:
            node.decorator_list = []
        namespace = {"UUID": UUID, "HTTPException": HTTPException, "get_connection": database.get_connection}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<actual approval handlers>", "exec"), namespace)
        app = FastAPI()
        app.get("/approvals/{approval_id}/training-gate")(namespace["approval_training_gate"])
        app.get("/health")(namespace["health"])
        with TestClient(app) as client:
            response = client.get(f"/approvals/{approval_id}/training-gate")
            assert response.status_code == 200
            gate = response.json()
            assert gate["approval_id"] == str(approval_id)
            assert gate["approval_ready"] is False
            assert gate["required_incomplete_count"] == 1
            assert gate["blocking_assignments"][0]["id"] == str(assignment_id)
            assert client.get("/health").status_code == 200
        assert calls == ["replacement"]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with database.get_connection() as runtime:
                runtime.execute("UPDATE applications SET data_classification='internal' WHERE id=%s", (app_id,))
        with database_connection() as admin:
            approval = admin.execute("SELECT status,human_decision FROM approval_requests WHERE id=%s", (approval_id,)).fetchone()
            assert approval == {"status": "pending", "human_decision": None}
            assert admin.execute("SELECT COUNT(*) AS n FROM approval_events WHERE approval_request_id=%s", (approval_id,)).fetchone()["n"] == 0
    finally:
        with database_connection() as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(rejected_role)))
