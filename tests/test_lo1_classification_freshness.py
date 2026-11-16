"""Classification freshness unit tests; these do not execute PostgreSQL SQL."""

import copy
import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
APPLICATION_ID = UUID("11111111-2222-3333-4444-555555555555")
ASSESSED_AT = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def classification(monkeypatch):
    # Isolate this service's generic "app" package from other service tests.
    package_name = "_lo1_classification_freshness_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT / "governance-api/app")]
    database = types.ModuleType(f"{package_name}.database")
    database.get_connection = Mock(
        side_effect=AssertionError("Unexpected real database access")
    )
    monkeypatch.setitem(sys.modules, package_name, package)
    monkeypatch.setitem(sys.modules, database.__name__, database)
    spec = importlib.util.spec_from_file_location(
        f"{package_name}.classification",
        ROOT / "governance-api/app/classification.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def application_row():
    return {
        "id": APPLICATION_ID,
        "name": "Example purchase form",
        "business_purpose": "Manage purchase requests",
        "data_fields": "request_id, amount",
        "connector_metadata": "Purchasing API",
        "data_classification": "unknown",
        "ml_classification_status": "not_assessed",
        "ml_classified_at": None,
    }


def ml_result():
    return {
        "suggested_classification": "internal",
        "confidence": 0.9,
        "review_required": False,
        "review_threshold": 0.8,
        "model_version": "test-model-v1",
        "class_probabilities": {"internal": 0.9, "public": 0.1},
        "authority": "test-advisory-authority",
    }


class FakeResult:
    def __init__(self, row=None):
        self.row = copy.deepcopy(row)

    def fetchone(self):
        return copy.deepcopy(self.row)


class FakeDatabase:
    def __init__(self):
        self.application = application_row()
        self.history = []
        self.connections = []
        self.active = 0
        self.fail_update = False

    def connect(self):
        connection = FakeConnection(self)
        self.connections.append(connection)
        return connection


class FakeConnection:
    def __init__(self, database):
        self.database = database
        self.calls = []
        self.pending_history = []
        self.pending_application = None
        self.locked = False
        self.rolled_back = False

    def __enter__(self):
        self.database.active += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.database.active -= 1
        self.rolled_back = exc_type is not None
        if exc_type is None:
            self.database.history.extend(self.pending_history)
            if self.pending_application is not None:
                self.database.application = self.pending_application
        return False

    def execute(self, sql, values):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, values))
        if normalized.startswith("SELECT"):
            assert values == (APPLICATION_ID,)
            if "FOR UPDATE" in normalized:
                self.locked = True
            return FakeResult(self.database.application)
        if normalized.startswith("INSERT INTO classification_assessments"):
            self.pending_history.append(values)
            return FakeResult()
        if normalized.startswith("UPDATE applications"):
            if self.database.fail_update:
                raise RuntimeError("Simulated application write failure")
            updated = copy.deepcopy(self.database.application)
            updated.update(
                ml_suggested_classification=values[0],
                ml_classification_confidence=values[1],
                ml_classification_review_required=values[2],
                ml_classification_model_version=values[3],
                ml_classification_status="assessed",
                ml_classified_at=ASSESSED_AT,
            )
            assert values[4] == APPLICATION_ID
            self.pending_application = updated
            return FakeResult(updated)
        raise AssertionError("Unexpected SQL operation")


@pytest.fixture
def harness(classification, monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(classification, "get_connection", database.connect)
    return classification, database, monkeypatch


def mock_inference(harness, during_inference=None):
    module, database, monkeypatch = harness

    def infer(url, **kwargs):
        # Do not hold the read transaction or row lock across an HTTP request.
        assert database.active == 0
        assert not any(item.locked for item in database.connections)
        if during_inference is not None:
            during_inference(database)
        return httpx.Response(
            200, json=ml_result(), request=httpx.Request("POST", url)
        )

    request = Mock(side_effect=infer)
    monkeypatch.setattr(module.httpx, "post", request)
    return request


def assert_no_persistence(database):
    assert database.history == []
    assert not any(
        sql.startswith(("INSERT", "UPDATE"))
        for connection in database.connections
        for sql, _ in connection.calls
    )


def test_current_inputs_produce_one_advisory_assessment(harness):
    module, database, _ = harness
    request = mock_inference(harness)
    result = module.classify_and_persist(APPLICATION_ID)
    assert len(database.history) == 1
    assert result["assessment_id"] == database.history[0][0]
    assert database.history[0][8].obj == request.call_args.kwargs["json"]
    assert result["suggested_classification"] == "internal"
    assert result["authoritative_classification"] == "unknown"
    assert database.application["data_classification"] == "unknown"
    assert result["ml_classification_status"] == "assessed"
    assert database.connections[-1].locked
    request.assert_called_once()


@pytest.mark.parametrize("field", [
    "name", "business_purpose", "data_fields", "connector_metadata",
])
def test_changed_inference_inputs_reject_the_old_result(harness, field):
    module, database, _ = harness

    def change(store):
        store.application[field] = "Changed while ML was running"
        store.application["ml_classification_status"] = "stale"

    mock_inference(harness, change)
    with pytest.raises(HTTPException) as error:
        module.classify_and_persist(APPLICATION_ID)
    assert error.value.status_code == 409
    assert error.value.detail["reason"] == "classification_inputs_changed"
    assert database.application[field] == "Changed while ML was running"
    assert database.application["ml_classification_status"] == "stale"
    assert_no_persistence(database)


def test_newer_assessment_cannot_be_overwritten(harness):
    module, database, _ = harness

    def assess_elsewhere(store):
        store.application.update(
            ml_classified_at=ASSESSED_AT,
            ml_classification_status="assessed",
            ml_suggested_classification="restricted",
        )

    mock_inference(harness, assess_elsewhere)
    with pytest.raises(HTTPException) as error:
        module.classify_and_persist(APPLICATION_ID)
    assert error.value.status_code == 409
    assert error.value.detail["reason"] == "classification_request_superseded"
    assert database.application["ml_suggested_classification"] == "restricted"
    assert database.application["ml_classified_at"] == ASSESSED_AT
    assert_no_persistence(database)


def test_classification_reset_during_inference_requires_a_retry(harness):
    module, database, _ = harness
    database.application["ml_classified_at"] = ASSESSED_AT - timedelta(days=1)

    def invalidate(store):
        store.application.update(
            ml_classified_at=None, ml_classification_status="stale"
        )

    mock_inference(harness, invalidate)
    with pytest.raises(HTTPException) as error:
        module.classify_and_persist(APPLICATION_ID)
    assert error.value.status_code == 409
    assert database.application["ml_classification_status"] == "stale"
    assert_no_persistence(database)


def test_application_deleted_during_inference_returns_not_found(harness):
    module, database, _ = harness
    mock_inference(harness, lambda store: setattr(store, "application", None))
    with pytest.raises(HTTPException) as error:
        module.classify_and_persist(APPLICATION_ID)
    assert error.value.status_code == 404
    assert_no_persistence(database)


def test_unrelated_change_does_not_discard_valid_classification(harness):
    module, database, _ = harness
    mock_inference(
        harness,
        lambda store: store.application.update(business_unit="Purchasing"),
    )
    module.classify_and_persist(APPLICATION_ID)
    assert len(database.history) == 1
    assert database.application["business_unit"] == "Purchasing"


@pytest.mark.parametrize("field", [
    "business_purpose", "data_fields", "connector_metadata",
])
@pytest.mark.parametrize("missing", [None, " \t "])
def test_missing_inputs_never_call_ml_or_write_history(harness, field, missing):
    module, database, _ = harness
    database.application[field] = missing
    request = mock_inference(harness)
    with pytest.raises(HTTPException) as error:
        module.classify_and_persist(APPLICATION_ID)
    assert error.value.status_code == 409
    assert error.value.detail["missing_fields"] == [field]
    request.assert_not_called()
    assert_no_persistence(database)


def test_unavailable_ml_does_not_touch_existing_assessment(harness):
    module, database, monkeypatch = harness
    before = copy.deepcopy(database.application)
    monkeypatch.setattr(
        module.httpx, "post", Mock(side_effect=httpx.ConnectError("test error"))
    )
    with pytest.raises(HTTPException) as error:
        module.classify_and_persist(APPLICATION_ID)
    assert error.value.status_code == 503
    assert database.application == before
    assert_no_persistence(database)


def test_write_failure_escapes_the_transaction_context(harness):
    module, database, _ = harness
    before = copy.deepcopy(database.application)
    database.fail_update = True
    mock_inference(harness)
    with pytest.raises(RuntimeError, match="Simulated application write failure"):
        module.classify_and_persist(APPLICATION_ID)
    assert database.connections[-1].rolled_back
    assert database.history == []
    assert database.application == before
