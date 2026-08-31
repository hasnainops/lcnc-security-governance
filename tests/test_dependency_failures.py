import importlib
import os
import sys
import types
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException


# governance-api/app/database.py reads DATABASE_URL during import.
# These tests mock get_connection, so no real database connection is made.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test:test@localhost:5432/test",
)

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_APP_DIR = ROOT / "governance-api" / "app"

# Load governance-api/app under a unique package name so it does not
# collide with risk-engine/app, which is also named "app".
package = types.ModuleType("governance_api_app")
package.__path__ = [str(GOVERNANCE_APP_DIR)]
sys.modules["governance_api_app"] = package

assessment = importlib.import_module("governance_api_app.assessment")
policy = importlib.import_module("governance_api_app.policy")


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row

    def execute(self, *args, **kwargs):
        return FakeResult(self.row)


class FakeConnectionContext:
    def __init__(self, row):
        self.connection = FakeConnection(row)

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def make_application():
    return {
        "id": uuid4(),
        "name": "Dependency Failure Test",
        "registration_status": "registered",
        "owner_name": "Test Owner",
        "business_purpose": "Security validation",
        "data_classification": "confidential",
        "internet_exposed": False,
        "external_integration": True,
        "integration_approved": False,
        "external_integration_count": 1,
        "unapproved_integration_count": 1,
        "credential_type": "api_key",
        "risk_score": 90,
        "risk_level": "critical",
    }


def test_risk_engine_connection_failure_returns_503(monkeypatch):
    application = make_application()

    monkeypatch.setattr(
        assessment,
        "get_connection",
        lambda: FakeConnectionContext(application),
    )

    def fail_request(*args, **kwargs):
        request = httpx.Request(
            "POST",
            "http://risk-engine:8001/assess",
        )
        raise httpx.ConnectError(
            "Risk Engine unavailable",
            request=request,
        )

    monkeypatch.setattr(assessment.httpx, "post", fail_request)

    with pytest.raises(HTTPException) as exc:
        assessment.assess_and_persist(application["id"])

    assert exc.value.status_code == 503
    assert exc.value.detail == (
        "Risk Engine unavailable. Governance evaluation failed closed."
    )


def test_opa_connection_failure_returns_503(monkeypatch):
    application = make_application()

    monkeypatch.setattr(
        policy,
        "get_connection",
        lambda: FakeConnectionContext(application),
    )

    def fail_request(*args, **kwargs):
        request = httpx.Request(
            "POST",
            "http://opa:8181/v1/data/lcnc/governance/decision",
        )
        raise httpx.ConnectError(
            "OPA unavailable",
            request=request,
        )

    monkeypatch.setattr(policy.httpx, "post", fail_request)

    with pytest.raises(HTTPException) as exc:
        policy.evaluate_and_persist(application["id"])

    assert exc.value.status_code == 503
    assert exc.value.detail == (
        "OPA policy engine unavailable. Governance evaluation failed closed."
    )
