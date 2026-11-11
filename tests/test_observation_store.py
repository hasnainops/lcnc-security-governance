import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "governance-api"))

from app import observation_store as store
from app.discovery_observation import AppsmithObservation

APPLICATION_ID = UUID("11111111-2222-3333-4444-555555555555")
OBSERVATION_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def sample():
    return AppsmithObservation(
        contract_version="appsmith-observation-v1",
        source="appsmith",
        external_id="app-1",
        collector_version="collector-v1",
        observed_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        collection_complete=True,
        pending_reasons=[],
        connectors=[
            {
                "connector_id": "b",
                "destination_state": "unresolved",
            },
            {
                "connector_id": "a",
                "destination_state": "unsupported",
            },
        ],
    )


class FakeConnection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.exit_type = None

    def execute(self, sql, parameters):
        self.calls.append((sql, parameters))
        self.row = self.rows.pop(0)
        if isinstance(self.row, Exception):
            raise self.row
        return self

    def fetchone(self):
        return self.row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_type = exc_type
        return False


def record(observation, digest):
    return {
        "id": OBSERVATION_ID,
        "application_id": APPLICATION_ID,
        "source": "appsmith",
        "observed_at": observation.observed_at,
        "received_at": datetime.now(timezone.utc),
        "payload_sha256": digest,
    }


def test_insert_binds_application_and_sanitized_payload(monkeypatch):
    observation = sample()
    document, digest = store.canonical_observation(observation)
    connection = FakeConnection([
        {"external_id": "app-1", "platform": "appsmith"},
        record(observation, digest),
        {"id": OBSERVATION_ID},
        {"connector_metadata": None},
        None,
    ])
    monkeypatch.setattr(store, "get_connection", lambda: connection)

    result = store.persist_discovery_observation(
        APPLICATION_ID, observation
    )

    assert result["created"] is True
    assert result["id"] == OBSERVATION_ID
    parameters = connection.calls[1][1]
    assert parameters[1] == APPLICATION_ID
    assert parameters[4].obj == document
    assert parameters[5] == digest
    assert connection.exit_type is None


@pytest.mark.parametrize("application,status", [
    (None, 404),
    ({"external_id": "different-app", "platform": "appsmith"}, 409),
    ({"external_id": "app-1", "platform": "another-platform"}, 409),
])
def test_identity_failure_prevents_insert(
    monkeypatch, application, status
):
    connection = FakeConnection([application])
    monkeypatch.setattr(store, "get_connection", lambda: connection)

    with pytest.raises(HTTPException) as caught:
        store.persist_discovery_observation(APPLICATION_ID, sample())

    assert caught.value.status_code == status
    assert len(connection.calls) == 1
    assert connection.exit_type is HTTPException


def test_identical_retry_returns_existing_record(monkeypatch):
    observation = sample()
    _, digest = store.canonical_observation(observation)
    existing = record(observation, digest)
    connection = FakeConnection([
        {"external_id": "app-1", "platform": "appsmith"},
        None,
        existing,
    ])
    monkeypatch.setattr(store, "get_connection", lambda: connection)

    result = store.persist_discovery_observation(
        APPLICATION_ID, observation
    )

    assert result == {
        **existing,
        "created": False,
        "risk_invalidated": False,
        "connector_metadata_updated": False,
        "data_field_evidence_updated": False,
    }


def test_conflicting_retry_is_rejected(monkeypatch):
    observation = sample()
    connection = FakeConnection([
        {"external_id": "app-1", "platform": "appsmith"},
        None,
        record(observation, "0" * 64),
    ])
    monkeypatch.setattr(store, "get_connection", lambda: connection)

    with pytest.raises(HTTPException) as caught:
        store.persist_discovery_observation(
            APPLICATION_ID, observation
        )

    assert caught.value.status_code == 409
    assert connection.exit_type is HTTPException


@pytest.mark.parametrize("rows", [
    [RuntimeError("database unavailable")],
    [None, None],
])
def test_database_failure_is_not_reported_as_success(
    monkeypatch, rows
):
    connection = FakeConnection([
        {"external_id": "app-1", "platform": "appsmith"},
        *rows,
    ])
    monkeypatch.setattr(store, "get_connection", lambda: connection)

    with pytest.raises(RuntimeError):
        store.persist_discovery_observation(APPLICATION_ID, sample())

    assert connection.exit_type is RuntimeError


def test_canonical_hash_ignores_order_and_equivalent_timezone():
    observation = sample()
    before = observation.model_dump(mode="json")
    reordered = observation.model_dump(mode="json")
    reordered["connectors"].reverse()
    reordered["observed_at"] = observation.observed_at.astimezone(
        timezone(timedelta(hours=2))
    ).isoformat()
    equivalent = AppsmithObservation.model_validate(reordered)

    assert (
        store.canonical_observation(observation)
        == store.canonical_observation(equivalent)
    )
    assert observation.model_dump(mode="json") == before


def test_changed_evidence_changes_hash():
    observation = sample()
    data = observation.model_dump(mode="json")
    data["connectors"][0]["uses_api_key"] = True
    changed = AppsmithObservation.model_validate(data)

    assert (
        store.canonical_observation(observation)[1]
        != store.canonical_observation(changed)[1]
    )


def test_future_timestamp_is_rejected_before_database_access(
    monkeypatch,
):
    data = sample().model_dump(mode="json")
    data["observed_at"] = (
        datetime.now(timezone.utc) + timedelta(days=1)
    )
    observation = AppsmithObservation.model_validate(data)

    def unexpected_connection():
        raise AssertionError("Database must not be accessed")

    monkeypatch.setattr(store, "get_connection", unexpected_connection)

    with pytest.raises(HTTPException) as caught:
        store.persist_discovery_observation(
            APPLICATION_ID, observation
        )

    assert caught.value.status_code == 422
