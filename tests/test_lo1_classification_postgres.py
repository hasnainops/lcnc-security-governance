"""Real SQL tests. Set LO1_TEST_DATABASE_URL to a dedicated lcnc_lo1_test_* DB.

The suite creates and drops its own database. It never defaults to DATABASE_URL.
Migrations run unchanged in public, including explicitly qualified table names.
ML replies are explicit test fixtures; live Appsmith acceptance is separate.
"""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

from fastapi import HTTPException
import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

from lo1_classification_support import ROOT, declaration, mock_ml, model_result, modules, observation


@pytest.fixture(scope="module")
def database_connection():
    dsn = os.getenv("LO1_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set LO1_TEST_DATABASE_URL to a dedicated lcnc_lo1_test_* database")
    if not conninfo_to_dict(dsn).get("dbname", "").startswith("lcnc_lo1_test_"):
        pytest.fail("Refusing a database name without the lcnc_lo1_test_ prefix")
    database = "lcnc_lo1_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(
            sql.Identifier(database)))
    def connect():
        return psycopg.connect(dsn, dbname=database, row_factory=dict_row,
                               options="-c search_path=public")
    connect.multi_session = True
    connect.schema = "public"
    try:
        with connect() as connection:
            # Files containing BEGIN/COMMIT manage their own transaction.
            connection.autocommit = True
            for path in ["database/init.sql", "database/migrations/019_discovery_observations.sql",
                         "database/migrations/020_application_data_field_evidence.sql",
                         "database/migrations/022_owner_context_classification.sql",
                         "database/migrations/026_discovery_feature_evidence.sql"]:
                connection.execute((ROOT / path).read_text())
        yield connect
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(
                sql.Identifier(database)))


@pytest.fixture
def scenario(database_connection, monkeypatch):
    service = modules(monkeypatch)
    for module in (service.owner_context, service.automatic_classification, service.discovery_presence):
        monkeypatch.setattr(module, "get_connection", database_connection)
    app_id, credential_id = uuid4(), uuid4()
    # Tokens are unique per fixture, with the same production length/format.
    import secrets
    token = "lo1_" + secrets.token_urlsafe(32)
    external = "lo1-test-" + app_id.hex
    with database_connection() as connection:
        connection.execute("INSERT INTO applications (id,external_id,name,platform) VALUES (%s,%s,%s,%s);",
                           (app_id, external, "Purchase requests", "appsmith"))
        connection.execute(
            """INSERT INTO application_owner_credentials
               (id,application_id,token_sha256,subject_id,owner_name,owner_email,issued_by,expires_at)
               VALUES (%s,%s,%s,'test-owner','Test owner','owner@example.test','test-operator',NOW()+INTERVAL '1 day');""",
            (credential_id, app_id, hashlib.sha256(token.encode()).hexdigest()))
    def observe(age=0, fields=None):
        now = datetime.now(timezone.utc) - timedelta(seconds=age)
        payload = observation(external, now)
        if fields is not None:
            payload["data_field_evidence"]["field_identifiers"] = fields
        with database_connection() as connection:
            connection.execute(
                """INSERT INTO discovery_observations (id,application_id,source,observed_at,payload,payload_sha256)
                   VALUES (%s,%s,'appsmith',%s,%s,%s);""",
                (uuid4(), app_id, now, Jsonb(payload), hashlib.sha256(json.dumps(payload).encode()).hexdigest()))
        return payload
    def save(payload=None):
        return service.owner_context.save_owner_context(
            app_id, service.owner_context.OwnerContextRequest.model_validate(payload or declaration()), "Bearer " + token)
    def history():
        with database_connection() as connection:
            return connection.execute("SELECT * FROM classification_assessments WHERE application_id=%s;", (app_id,)).fetchall()
    return service, database_connection, app_id, credential_id, token, observe, save, history


def test_real_sql_owner_to_classification_history_and_idempotency(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    declaration_result = save()
    assert save()["action"] == "unchanged"
    calls = mock_ml(monkeypatch, service.automatic_classification)
    result = service.automatic_classification.classify_if_needed(app_id)
    assert result["action"] == "assessed"
    assert result["authoritative_classification"] == "unknown"
    assert result["provenance"]["owner_context_id"] == str(declaration_result["context_id"])
    observe()  # A new poll with identical content must not repeat inference.
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "unchanged"
    assert len(history()) == len(calls) == 1
    assert service.automatic_classification.classification_state(app_id)["suggested_classification"] == "internal"


def test_observed_rename_keeps_identity_and_governed_facts_and_reclassifies(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    calls = mock_ml(monkeypatch, service.automatic_classification)
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "assessed"
    with connect() as connection:
        connection.execute("UPDATE applications SET shadow_it_candidate=TRUE, last_seen_at=NOW()-INTERVAL '2 minutes' WHERE id=%s;", (app_id,))
        before = connection.execute("SELECT * FROM applications WHERE id=%s;", (app_id,)).fetchone()
    payload = service.discovery_presence.AppsmithSeenRequest(
        source="appsmith", external_id=before["external_id"], name="Renamed purchase requests",
    )
    after = service.discovery_presence.persist_application_seen(app_id, payload)
    assert after["name"] == payload.name
    assert after["last_seen_at"] > before["last_seen_at"]
    for field in ("id", "external_id", "platform", "first_discovered_at", "registration_status",
                  "data_classification", "shadow_it_candidate", "owner_context_id", "owner_name",
                  "owner_email", "business_purpose", "data_fields", "risk_status", "risk_score",
                  "risk_level", "governance_status", "governance_outcome"):
        assert after[field] == before[field], field
    assert after["ml_classification_status"] == "stale"
    assert after["ml_suggested_classification"] is None
    assert len(history()) == 1
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "assessed"
    assert calls[-1]["application_name"] == payload.name
    assert len(history()) == 2
    again = service.discovery_presence.persist_application_seen(app_id, payload)
    assert again["ml_classification_status"] == "assessed"
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "unchanged"
    assert len(history()) == len(calls) == 2


def test_legacy_seen_updates_timestamp_without_invalidating_classification(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    mock_ml(monkeypatch, service.automatic_classification)
    service.automatic_classification.classify_if_needed(app_id)
    before = service.automatic_classification.classification_state(app_id)
    after = service.discovery_presence.persist_application_seen(app_id)
    assert after["ml_classification_status"] == "assessed"
    assert after["ml_suggested_classification"] == before["suggested_classification"]
    assert len(history()) == 1


@pytest.mark.parametrize("case", ["wrong_external_id", "wrong_platform", "missing_application"])
def test_seen_identity_mismatch_cannot_rename_or_refresh_another_record(scenario, case):
    service, connect, app_id, _, _, _, _, _ = scenario
    with connect() as connection:
        if case == "wrong_platform":
            connection.execute("UPDATE applications SET platform='other' WHERE id=%s;", (app_id,))
        before = connection.execute("SELECT * FROM applications WHERE id=%s;", (app_id,)).fetchone()
    payload = service.discovery_presence.AppsmithSeenRequest(
        source="appsmith", external_id="other-source" if case == "wrong_external_id" else before["external_id"],
        name="Must not replace the saved name",
    )
    with pytest.raises(HTTPException) as error:
        service.discovery_presence.persist_application_seen(uuid4() if case == "missing_application" else app_id, payload)
    assert error.value.status_code == (404 if case == "missing_application" else 409)
    with connect() as connection:
        after = connection.execute("SELECT * FROM applications WHERE id=%s;", (app_id,)).fetchone()
    assert after == before


@pytest.mark.parametrize("kind", ["missing", "wrong_application", "expired", "revoked"])
def test_owner_credential_boundary(scenario, kind):
    service, connect, app_id, credential_id, token, _, save, _ = scenario
    target, auth = app_id, "Bearer " + token
    if kind == "missing":
        auth = None
    elif kind == "wrong_application":
        target = uuid4()
    else:
        with connect() as connection:
            if kind == "expired":
                connection.execute("UPDATE application_owner_credentials SET issued_at=NOW()-INTERVAL '2 days', expires_at=NOW()-INTERVAL '1 day' WHERE id=%s;", (credential_id,))
            else:
                connection.execute("UPDATE application_owner_credentials SET revoked_at=NOW() WHERE id=%s;", (credential_id,))
    with pytest.raises(HTTPException) as error:
        service.owner_context.save_owner_context(target, service.owner_context.OwnerContextRequest(**declaration()), auth)
    assert error.value.status_code == (403 if kind == "wrong_application" else 401)
    with connect() as connection:
        assert connection.execute("SELECT COUNT(*) AS count FROM application_owner_contexts WHERE application_id=%s;", (app_id,)).fetchone()["count"] == 0


def test_no_attestation_stays_pending_without_ml(scenario, monkeypatch):
    service, _, app_id, _, _, observe, _, history = scenario
    observe()
    monkeypatch.setattr(service.automatic_classification.httpx, "get", lambda *a, **k: pytest.fail("ML called without declaration"))
    result = service.automatic_classification.classify_if_needed(app_id)
    assert result["pending_reasons"] == ["owner_attestation_required"]
    assert not history()


def test_owner_change_during_inference_cannot_publish_old_result(scenario, monkeypatch):
    service, _, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    mock_ml(monkeypatch, service.automatic_classification,
            during=lambda: save({**declaration(), "business_purpose": "Handle confidential employee payroll records"}))
    result = service.automatic_classification.classify_if_needed(app_id)
    assert result["action"] == "superseded"
    assert not history()
    mock_ml(monkeypatch, service.automatic_classification)
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "assessed"
    assert "payroll" in history()[0]["inputs"]["business_purpose"]


def test_new_widget_evidence_during_inference_requires_retry(scenario, monkeypatch):
    service, _, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    mock_ml(monkeypatch, service.automatic_classification, during=lambda: observe(fields=["salary"]))
    result = service.automatic_classification.classify_if_needed(app_id)
    assert result["pending_reasons"] == ["source_changed_during_inference"]
    assert not history()


def test_second_request_observes_lease_without_duplicate_inference(scenario, monkeypatch):
    service, _, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    nested = []
    calls = mock_ml(monkeypatch, service.automatic_classification,
                    during=lambda: nested.append(service.automatic_classification.classify_if_needed(app_id)))
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "assessed"
    assert nested[0]["action"] == "in_progress"
    assert len(calls) == len(history()) == 1


def test_simultaneous_requests_across_postgres_sessions(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    if not getattr(connect, "multi_session", False):
        pytest.skip("Requires a PostgreSQL server accepting multiple sessions")
    observe()
    save()
    started, release = Event(), Event()
    def hold_inference():
        started.set()
        assert release.wait(10)
    calls = mock_ml(monkeypatch, service.automatic_classification, during=hold_inference)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.automatic_classification.classify_if_needed, app_id)
        try:
            assert started.wait(10)
            second = executor.submit(service.automatic_classification.classify_if_needed, app_id)
            assert second.result(timeout=10)["action"] == "in_progress"
        finally:
            release.set()
        assert first.result(timeout=10)["action"] == "assessed"
    assert len(calls) == len(history()) == 1


def test_expired_worker_lease_is_recoverable(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    with connect() as connection:
        connection.execute("UPDATE applications SET ml_classification_status='assessing', ml_classification_lease_id=%s, ml_classification_lease_until=NOW()-INTERVAL '1 second' WHERE id=%s;", (uuid4(), app_id))
    assert service.automatic_classification.classification_state(app_id)["pending_reasons"] == ["inference_lease_expired"]
    mock_ml(monkeypatch, service.automatic_classification)
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "assessed"
    assert len(history()) == 1


@pytest.mark.parametrize("failure", ["offline", "malformed", "changed_model"])
def test_ml_failure_preserves_inventory_and_declaration_then_retries(scenario, monkeypatch, failure):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    declared = save()
    if failure == "offline":
        mock_ml(monkeypatch, service.automatic_classification)
        def unavailable(*args, **kwargs):
            raise httpx.ConnectError("test unavailable")
        monkeypatch.setattr(service.automatic_classification.httpx, "post", unavailable)
    else:
        fixture = model_result(authority="authoritative") if failure == "malformed" else model_result(model_sha256="b" * 64)
        mock_ml(monkeypatch, service.automatic_classification, result=fixture)
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "pending"
    with connect() as connection:
        row = connection.execute("SELECT * FROM applications WHERE id=%s;", (app_id,)).fetchone()
    assert row["owner_context_id"] == declared["context_id"]
    assert row["data_classification"] == "unknown"
    assert not history()
    mock_ml(monkeypatch, service.automatic_classification)
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "assessed"
    assert len(history()) == 1


def test_stale_observation_hides_current_result_but_preserves_history(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe(age=250)
    save()
    # The state endpoint must not display an old suggestion merely because it
    # remains in the application or its assessment history.
    with connect() as connection:
        connection.execute("UPDATE applications SET ml_classification_status='assessed', ml_suggested_classification='public' WHERE id=%s;", (app_id,))
    state = service.automatic_classification.classification_state(app_id)
    assert state["suggested_classification"] is None
    assert state["pending_reasons"] == ["appsmith_observation_stale"]
    mock_ml(monkeypatch, service.automatic_classification)
    observe()
    service.automatic_classification.classify_if_needed(app_id)
    assert len(history()) == 1
    observe(fields=["salary"])
    state = service.automatic_classification.classification_state(app_id)
    assert state["ml_classification_status"] == "stale"
    assert state["suggested_classification"] is None
    assert len(history()) == 1


def test_high_sensitivity_always_requires_review(scenario, monkeypatch):
    service, _, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    mock_ml(monkeypatch, service.automatic_classification, result=model_result(
        suggested_classification="restricted", class_probabilities={"public": .1, "internal": .05, "confidential": .05, "restricted": .8}))
    result = service.automatic_classification.classify_if_needed(app_id)
    assert result["review_required"] is True
    assert result["authoritative_classification"] == "unknown"
    assert "high_sensitivity_requires_human_review" in history()[0]["source_evidence"]["review_reasons"]


def test_history_and_current_result_rollback_together(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    name = "fail_lo1_" + uuid4().hex
    with connect() as connection:
        connection.execute(f"""CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN IF NEW.id='{app_id}'::uuid AND NEW.ml_classification_status='assessed' THEN
          RAISE EXCEPTION 'test write failure'; END IF; RETURN NEW; END $$;""")
        connection.execute(f"CREATE TRIGGER {name} BEFORE UPDATE ON applications FOR EACH ROW EXECUTE FUNCTION {name}();")
    mock_ml(monkeypatch, service.automatic_classification)
    try:
        with pytest.raises(Exception):
            service.automatic_classification.classify_if_needed(app_id)
        assert not history()
    finally:
        with connect() as connection:
            connection.execute(f"DROP TRIGGER {name} ON applications;")
            connection.execute(f"DROP FUNCTION {name}();")


def test_api_role_can_declare_without_credential_write_permission(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    role = "lo1_test_" + uuid4().hex
    schema = getattr(connect, "schema", "public")
    with connect() as connection:
        connection.execute(f'CREATE ROLE "{role}";')
        connection.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}";')
        connection.execute(f'GRANT SELECT ON application_owner_credentials, discovery_observations TO "{role}";')
        connection.execute(f'GRANT SELECT, INSERT ON application_owner_contexts, classification_assessments TO "{role}";')
        connection.execute(f'GRANT SELECT, UPDATE ON applications TO "{role}";')
    @contextmanager
    def workload_connection():
        with connect() as connection:
            connection.execute(f'SET LOCAL ROLE "{role}";')
            yield connection
    try:
        for module in (service.owner_context, service.automatic_classification):
            monkeypatch.setattr(module, "get_connection", workload_connection)
        assert save()["action"] == "saved"
        mock_ml(monkeypatch, service.automatic_classification)
        assert service.automatic_classification.classify_if_needed(app_id)["action"] == "assessed"
        with pytest.raises(Exception):
            with workload_connection() as connection:
                connection.execute("UPDATE application_owner_credentials SET revoked_at=NOW() WHERE application_id=%s;", (app_id,))
    finally:
        with connect() as connection:
            connection.execute(f'DROP OWNED BY "{role}";')
            connection.execute(f'DROP ROLE "{role}";')


@pytest.fixture(scope="module")
def receipt_connection(database_connection):
    """Verify the pending LO2 migrations alongside the LO1 schema."""
    with database_connection() as connection:
        connection.autocommit = True
        for name in (
            "021_controlled_egress_enforcement_receipts.sql",
            "023_complete_egress_receipts.sql",
            "023_complete_egress_receipts.sql",  # Repeat application is safe.
        ):
            connection.execute((ROOT / "database/migrations" / name).read_text())
    return database_connection


def insert_receipt_fixture(connection, outcome, allowed, enforced_at, status):
    app_id, event_id = uuid4(), uuid4()
    connection.execute(
        "INSERT INTO applications (id,external_id,name,platform) VALUES (%s,%s,'Receipt fixture','appsmith');",
        (app_id, "receipt-test-" + app_id.hex),
    )
    connection.execute(
        """INSERT INTO integration_transfer_events (
           id,application_id,destination_scheme,destination_host,destination_trust,
           declared_classification,decision,allowed,reasons,dlp_sensitive_data_detected,
           dlp_finding_count,dlp_detected_types,gateway_version,dlp_engine_version,
           enforcement_outcome,enforced_at,upstream_status_code)
           VALUES (%s,%s,'https','example.test','approved_external','internal',
                   %s,%s,'[]',FALSE,0,'[]','test-v1','test-v1',%s,%s,%s);""",
        (event_id, app_id, "allow" if allowed else "block", allowed,
         outcome, enforced_at, status),
    )
    return app_id, event_id


@pytest.mark.parametrize("outcome,allowed,has_time,status,accepted", [
    (None, True, False, None, True),
    (None, False, False, None, True),
    ("blocked_before_send", False, True, None, True),
    ("delivery_unconfirmed", True, True, None, True),
    ("forwarded_upstream", True, True, 100, True),
    ("forwarded_upstream", True, True, 599, True),
    (None, True, True, None, False),
    (None, False, True, None, False),
    (None, True, False, 200, False),
    (None, True, True, 200, False),
    ("forwarded_upstream", True, True, None, False),
    ("forwarded_upstream", True, False, 200, False),
    ("forwarded_upstream", False, True, 200, False),
    ("forwarded_upstream", True, True, 99, False),
    ("forwarded_upstream", True, True, 600, False),
    ("blocked_before_send", True, True, None, False),
    ("blocked_before_send", False, False, None, False),
    ("blocked_before_send", False, True, 200, False),
    ("delivery_unconfirmed", False, True, None, False),
    ("delivery_unconfirmed", True, False, None, False),
    ("delivery_unconfirmed", True, True, 200, False),
    ("unsupported_outcome", True, True, None, False),
])
def test_lo2_receipt_integrity_with_classification_schema(
    receipt_connection, outcome, allowed, has_time, status, accepted,
):
    when = datetime.now(timezone.utc) if has_time else None
    def persist():
        with receipt_connection() as connection:
            return insert_receipt_fixture(connection, outcome, allowed, when, status)
    if accepted:
        _, event_id = persist()
        with receipt_connection() as connection:
            row = connection.execute(
                "SELECT enforcement_outcome,allowed,enforced_at,upstream_status_code FROM integration_transfer_events WHERE id=%s;",
                (event_id,),
            ).fetchone()
        assert tuple(row.values()) == (outcome, allowed, when, status)
    else:
        with pytest.raises(psycopg.errors.CheckViolation):
            persist()


def test_lo2_receipt_migration_preserves_invalid_existing_evidence(receipt_connection):
    """An invalid old receipt stops migration rather than being rewritten."""
    migration = (ROOT / "database/migrations/023_complete_egress_receipts.sql").read_text()
    with receipt_connection() as connection:
        connection.execute("ALTER TABLE integration_transfer_events DROP CONSTRAINT ck_transfer_enforcement_receipt_complete;")
        app_id, event_id = insert_receipt_fixture(
            connection, "forwarded_upstream", True, datetime.now(timezone.utc), None,
        )
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            with receipt_connection() as connection:
                connection.autocommit = True
                connection.execute(migration)
        with receipt_connection() as connection:
            row = connection.execute(
                "SELECT enforcement_outcome,upstream_status_code FROM integration_transfer_events WHERE id=%s;",
                (event_id,),
            ).fetchone()
            assert row == {"enforcement_outcome": "forwarded_upstream", "upstream_status_code": None}
            assert not connection.execute(
                "SELECT 1 FROM pg_constraint WHERE conrelid='integration_transfer_events'::regclass AND conname='ck_transfer_enforcement_receipt_complete';",
            ).fetchone()
    finally:
        # Remove only this synthetic fixture, then restore the test constraint.
        with receipt_connection() as connection:
            connection.execute("DELETE FROM applications WHERE id=%s;", (app_id,))
        with receipt_connection() as connection:
            connection.autocommit = True
            connection.execute(migration)


# Regression: a source outage must hide current evidence without causing a
# second inference when the same semantic inputs become fresh again.
def _expire_observations(connect, app_id):
    with connect() as connection:
        connection.execute("""UPDATE discovery_observations
            SET observed_at = observed_at - INTERVAL '10 minutes',
                payload = jsonb_set(payload, '{observed_at}',
                    to_jsonb(observed_at - INTERVAL '10 minutes'))
            WHERE application_id = %s;""", (app_id,))


def test_recovery_reuses_history_and_preserves_inference_timestamp(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    calls = mock_ml(monkeypatch, service.automatic_classification)
    original = service.automatic_classification.classify_if_needed(app_id)
    original_history = history()
    for _ in range(3):
        _expire_observations(connect, app_id)
        pending = service.automatic_classification.classify_if_needed(app_id)
        assert pending["pending_reasons"] == ["appsmith_observation_stale"]
        assert pending["suggested_classification"] is None
        assert service.automatic_classification.classification_state(app_id)["suggested_classification"] is None
        observe()
        result = service.automatic_classification.classify_if_needed(app_id)
        assert result["action"] == "revalidated"
        assert result["assessment_id"] == original["assessment_id"]
        assert result["classified_at"] == original["classified_at"]
        assert result["authoritative_classification"] == "unknown"
        assert result["provenance"]["reused_assessment_id"] == str(original["assessment_id"])
        assert result["provenance"]["observation_id"] != original["provenance"]["observation_id"]
        assert result["provenance"]["inference_observation_id"] == original["provenance"]["observation_id"]
        assert "revalidated_at" in result["provenance"]
        assert service.automatic_classification.classify_if_needed(app_id)["action"] == "unchanged"
    assert history() == original_history
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["fields", "purpose", "model", "threshold"])
def test_recovery_changed_inputs_or_model_runs_new_inference(scenario, monkeypatch, change):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    calls = mock_ml(monkeypatch, service.automatic_classification)
    service.automatic_classification.classify_if_needed(app_id)
    _expire_observations(connect, app_id)
    service.automatic_classification.classify_if_needed(app_id)
    observe(fields=["salary"] if change == "fields" else None)
    if change == "purpose":
        payload = declaration()
        payload["business_purpose"] = "Manage payroll processing for employees"
        save(payload)
    if change in {"model", "threshold"}:
        digest = "b" * 64 if change == "model" else "a" * 64
        threshold = 0.9 if change == "threshold" else 0.6
        monkeypatch.setattr(service.automatic_classification.httpx, "get", lambda url, **kw:
            httpx.Response(200, json={"classification_model_version": "synthetic-test-v1",
                "classification_model_sha256": digest,
                "classification_review_threshold": threshold}, request=httpx.Request("GET", url)))
        def changed_model(url, **kwargs):
            calls.append(kwargs["json"])
            return httpx.Response(200, json=model_result(model_sha256=digest, review_threshold=threshold),
                                  request=httpx.Request("POST", url))
        monkeypatch.setattr(service.automatic_classification.httpx, "post", changed_model)
    result = service.automatic_classification.classify_if_needed(app_id)
    assert result["action"] == "assessed"
    assert len(calls) == len(history()) == 2


def test_model_health_outage_withholds_then_reuses(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    calls = mock_ml(monkeypatch, service.automatic_classification)
    original = service.automatic_classification.classify_if_needed(app_id)
    with monkeypatch.context() as patch:
        def unavailable(*args, **kwargs):
            raise httpx.ConnectError("synthetic outage")
        patch.setattr(service.automatic_classification.httpx, "get", unavailable)
        pending = service.automatic_classification.classify_if_needed(app_id)
        assert pending["pending_reasons"] == ["ml_identity_unavailable"]
        assert pending["suggested_classification"] is None
    result = service.automatic_classification.classify_if_needed(app_id)
    assert result["action"] == "revalidated"
    assert result["assessment_id"] == original["assessment_id"]
    assert len(history()) == len(calls) == 1


def test_concurrent_recovery_does_not_duplicate_inference(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    calls = mock_ml(monkeypatch, service.automatic_classification)
    service.automatic_classification.classify_if_needed(app_id)
    _expire_observations(connect, app_id)
    service.automatic_classification.classify_if_needed(app_id)
    observe()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.automatic_classification.classify_if_needed, app_id) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(result["action"] for result in results) == ["revalidated", "unchanged"]
    assert len(history()) == len(calls) == 1


@pytest.mark.parametrize("damage", ["model", "inputs", "probabilities"])
def test_invalid_history_is_not_reused(scenario, monkeypatch, damage):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    calls = mock_ml(monkeypatch, service.automatic_classification)
    service.automatic_classification.classify_if_needed(app_id)
    _expire_observations(connect, app_id)
    service.automatic_classification.classify_if_needed(app_id)
    with connect() as connection:
        if damage == "model":
            connection.execute("UPDATE classification_assessments SET source_evidence=source_evidence-'model_sha256' WHERE application_id=%s;", (app_id,))
        elif damage == "inputs":
            connection.execute("UPDATE classification_assessments SET inputs='{}'::jsonb WHERE application_id=%s;", (app_id,))
        else:
            connection.execute("UPDATE classification_assessments SET class_probabilities='{}'::jsonb WHERE application_id=%s;", (app_id,))
    observe()
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "assessed"
    assert len(history()) == len(calls) == 2


def test_recovery_preserves_low_confidence_review(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    calls = mock_ml(monkeypatch, service.automatic_classification, result=model_result(
        confidence=0.4, review_required=True,
        class_probabilities={"public": .2, "internal": .4, "confidential": .2, "restricted": .2}))
    original = service.automatic_classification.classify_if_needed(app_id)
    _expire_observations(connect, app_id)
    service.automatic_classification.classify_if_needed(app_id)
    observe()
    restored = service.automatic_classification.classify_if_needed(app_id)
    assert restored["action"] == "revalidated"
    assert restored["review_required"] is True
    assert restored["provenance"]["review_reasons"] == original["provenance"]["review_reasons"]
    assert len(history()) == len(calls) == 1



def test_recovery_respects_active_inference_lease(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    calls = mock_ml(monkeypatch, service.automatic_classification)
    service.automatic_classification.classify_if_needed(app_id)
    lease_id = uuid4()
    with connect() as connection:
        connection.execute("""UPDATE applications SET ml_classification_status='assessing',
            ml_classification_lease_id=%s, ml_classification_lease_until=NOW()+INTERVAL '1 minute'
            WHERE id=%s;""", (lease_id, app_id))
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "in_progress"
    with connect() as connection:
        row = connection.execute("SELECT ml_classification_lease_id FROM applications WHERE id=%s;", (app_id,)).fetchone()
    assert row["ml_classification_lease_id"] == lease_id
    assert len(history()) == len(calls) == 1


def test_recovery_write_failure_rolls_back_without_touching_history(scenario, monkeypatch):
    service, connect, app_id, _, _, observe, save, history = scenario
    observe()
    save()
    calls = mock_ml(monkeypatch, service.automatic_classification)
    service.automatic_classification.classify_if_needed(app_id)
    original_history = history()
    _expire_observations(connect, app_id)
    service.automatic_classification.classify_if_needed(app_id)
    observe()
    name = "fail_revalidation_" + uuid4().hex
    with connect() as connection:
        connection.execute(f"""CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN IF NEW.id='{app_id}'::uuid AND NEW.ml_classification_status='assessed' THEN
          RAISE EXCEPTION 'test recovery failure'; END IF; RETURN NEW; END $$;""")
        connection.execute(f"CREATE TRIGGER {name} BEFORE UPDATE ON applications FOR EACH ROW EXECUTE FUNCTION {name}();")
    try:
        with pytest.raises(psycopg.errors.RaiseException):
            service.automatic_classification.classify_if_needed(app_id)
        with connect() as connection:
            row = connection.execute("SELECT ml_classification_status FROM applications WHERE id=%s;", (app_id,)).fetchone()
        assert row["ml_classification_status"] == "pending"
        assert history() == original_history
        assert len(calls) == 1
    finally:
        with connect() as connection:
            connection.execute(f"DROP TRIGGER {name} ON applications;")
            connection.execute(f"DROP FUNCTION {name}();")
    assert service.automatic_classification.classify_if_needed(app_id)["action"] == "revalidated"
