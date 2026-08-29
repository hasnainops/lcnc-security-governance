import importlib
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test:test@localhost:5432/test",
)

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_APP_DIR = ROOT / "governance-api" / "app"

package_name = "governance_api_app_handoff"
package = types.ModuleType(package_name)
package.__path__ = [str(GOVERNANCE_APP_DIR)]
package.__package__ = package_name
sys.modules[package_name] = package

handoff = importlib.import_module(
    "governance_api_app_handoff.enterprise_handoff"
)


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.application_id = uuid4()

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.calls.append((normalized, params))

        if "SELECT * FROM applications" in normalized:
            return FakeResult(None)

        if "INSERT INTO applications" in normalized:
            return FakeResult(
                {
                    "id": self.application_id,
                    "external_id": "shadow-app-001",
                    "name": "Shadow Finance Export",
                    "platform": "appsmith",
                    "registration_status": "unregistered",
                }
            )

        if "UPDATE applications" in normalized:
            return FakeResult(
                {
                    "id": self.application_id,
                    "external_id": "shadow-app-001",
                    "name": "Shadow Finance Export",
                    "platform": "appsmith",
                    "registration_status": "unregistered",
                    "ml_anomaly_status": "assessed",
                    "ml_anomalous": True,
                    "ml_decision_score": -0.271,
                    "ml_model_version": "isolation-forest-v1",
                }
            )

        return FakeResult()


class FakeConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def make_handoff_payload():
    return {
        "source": "generic_security_feed",
        "external_id": "shadow-app-001",
        "name": "Shadow Finance Export",
        "platform": "appsmith",
        "authorization_status": "unknown",
        "owner_known": False,
        "business_purpose_known": False,
        "internet_exposed": True,
        "uses_api_key": True,
        "external_integration_count": 2,
        "unapproved_integration_count": 1,
        "connector_count": 3,
        "external_domain_count": 2,
        "changes_last_24h": 4,
        "evidence": [
            "Observed by enterprise security feed",
        ],
        "observed_at": datetime.now(timezone.utc),
        "ml_result": {
            "analysis_type": "shadow-it-anomaly",
            "anomalous": True,
            "raw_decision_score": -0.271,
            "model_version": "isolation-forest-v1",
            "context_signals": [
                "application is internet exposed",
                "one or more external integrations are unapproved",
            ],
        },
    }


def test_enterprise_handoff_module_exists():
    assert hasattr(
        handoff,
        "persist_enterprise_discovery_handoff",
    )


def test_new_discovery_persists_existing_ml_result(monkeypatch):
    connection = FakeConnection()

    monkeypatch.setattr(
        handoff,
        "get_connection",
        lambda: FakeConnectionContext(connection),
        raising=False,
    )

    result = handoff.persist_enterprise_discovery_handoff(
        make_handoff_payload()
    )

    statements = [
        query
        for query, _ in connection.calls
    ]

    assert any(
        "INSERT INTO applications" in query
        for query in statements
    )

    assert any(
        "INSERT INTO ml_assessments" in query
        for query in statements
    )

    assert any(
        "UPDATE applications" in query
        for query in statements
    )

    assert result["application_id"] == connection.application_id
    assert result["action"] == "created"
    assert result["ml"]["model_version"] == "isolation-forest-v1"
    assert result["ml"]["anomalous"] is True


class FakeExistingConnection(FakeConnection):
    def __init__(self):
        super().__init__()
        self.existing_application = {
            "id": self.application_id,
            "external_id": "shadow-app-001",
            "name": "Shadow Finance Export",
            "platform": "appsmith",
            "registration_status": "registered",
        }

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.calls.append((normalized, params))

        if "SELECT * FROM applications" in normalized:
            return FakeResult(self.existing_application)

        if "INSERT INTO applications" in normalized:
            raise AssertionError(
                "Existing canonical application must not be recreated."
            )

        if "UPDATE applications" in normalized:
            return FakeResult(
                {
                    **self.existing_application,
                    "ml_anomaly_status": "assessed",
                    "ml_anomalous": True,
                    "ml_decision_score": -0.271,
                    "ml_model_version": "isolation-forest-v1",
                }
            )

        return FakeResult()


def test_repeat_discovery_updates_same_canonical_application(
    monkeypatch,
):
    connection = FakeExistingConnection()

    monkeypatch.setattr(
        handoff,
        "get_connection",
        lambda: FakeConnectionContext(connection),
    )

    result = handoff.persist_enterprise_discovery_handoff(
        make_handoff_payload()
    )

    statements = [
        query
        for query, _ in connection.calls
    ]

    assert not any(
        "INSERT INTO applications" in query
        for query in statements
    )

    assert any(
        "INSERT INTO ml_assessments" in query
        for query in statements
    )

    assert result["application_id"] == connection.application_id
    assert result["action"] == "updated"


import pytest

from fastapi import HTTPException


def test_same_external_id_different_platform_fails_closed(
    monkeypatch,
):
    connection = FakeExistingConnection()

    connection.existing_application["platform"] = "powerapps"

    monkeypatch.setattr(
        handoff,
        "get_connection",
        lambda: FakeConnectionContext(connection),
    )

    with pytest.raises(HTTPException) as exc:
        handoff.persist_enterprise_discovery_handoff(
            make_handoff_payload()
        )

    assert exc.value.status_code == 409
    assert "platform" in str(exc.value.detail).lower()

def test_anomalous_unknown_discovery_is_shadow_it_candidate(
    monkeypatch,
):
    connection = FakeConnection()

    monkeypatch.setattr(
        handoff,
        "get_connection",
        lambda: FakeConnectionContext(connection),
    )

    result = handoff.persist_enterprise_discovery_handoff(
        make_handoff_payload()
    )

    assert result["shadow_it_candidate"] is True
    assert result["shadow_it_candidate_basis"] == {
        "enterprise_discovery": True,
        "ml_anomalous": True,
        "authorization_status": "unknown",
    }

    ml_updates = [
        params
        for query, params in connection.calls
        if (
            "UPDATE applications" in query
            and "shadow_it_candidate" in query
        )
    ]

    assert len(ml_updates) == 1
    assert ml_updates[0][-2] is True


def test_authorized_anomalous_discovery_is_not_shadow_it_candidate(
    monkeypatch,
):
    connection = FakeConnection()
    payload = make_handoff_payload()
    payload["authorization_status"] = "authorized"

    monkeypatch.setattr(
        handoff,
        "get_connection",
        lambda: FakeConnectionContext(connection),
    )

    result = handoff.persist_enterprise_discovery_handoff(payload)

    assert result["shadow_it_candidate"] is False
    assert (
        result["shadow_it_candidate_basis"]["authorization_status"]
        == "authorized"
    )


def test_non_anomalous_discovery_is_not_shadow_it_candidate(
    monkeypatch,
):
    connection = FakeConnection()
    payload = make_handoff_payload()
    payload["ml_result"]["anomalous"] = False

    monkeypatch.setattr(
        handoff,
        "get_connection",
        lambda: FakeConnectionContext(connection),
    )

    result = handoff.persist_enterprise_discovery_handoff(payload)

    assert result["shadow_it_candidate"] is False
