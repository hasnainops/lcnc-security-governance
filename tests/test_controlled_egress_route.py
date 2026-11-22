import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_API = ROOT / "governance-api"

sys.path.insert(
    0,
    str(GOVERNANCE_API),
)

from app import main as governance_main


APPLICATION_ID = (
    "11111111-2222-3333-4444-555555555555"
)


@pytest.fixture(autouse=True)
def authenticated_export_fixture(monkeypatch):
    """Existing route tests assume a valid authorized caller."""

    def verify(authorization):
        if authorization != "Bearer route-fixture":
            raise governance_main.ReviewerAccessError(
                401,
                "Access bearer credential required.",
            )

        return {
            "subject_id": (
                "vault:11111111-2222-3333-4444-555555555555"
            ),
            "role": "developer",
        }

    def permit_export(application_id, request, authorization=None):
        assert request.action == "export"
        assert authorization == "Bearer route-fixture"
        return {"allowed": True, "decision": "allow"}

    def active_grant(application_id, request, authorization=None):
        assert request.action == "export"
        assert authorization == "Bearer route-fixture"

        return {
            "active": True,
            "grant_id": (
                "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
            ),
            "granted_action": "export",
        }

    monkeypatch.setattr(
        governance_main,
        "verified_access_principal",
        verify,
    )

    monkeypatch.setattr(
        governance_main,
        "authorize_and_persist",
        permit_export,
    )

    monkeypatch.setattr(
        governance_main,
        "check_jit_privilege",
        active_grant,
    )


def test_controlled_egress_route_returns_block_without_execution(
    monkeypatch,
):
    def fake_execute(
        application_id,
        payload,
    ):
        return {
            "application_id": str(application_id),
            "decision": "block",
            "allowed": False,
            "executed": False,
            "upstream_status_code": None,
            "reasons": [
                "destination_not_approved",
            ],
        }

    monkeypatch.setattr(
        governance_main,
        "execute_controlled_egress",
        fake_execute,
    )

    monkeypatch.setattr(
        governance_main,
        "evaluate_policy_and_persist",
        lambda *_args: {"allowed": True},
    )

    client = TestClient(
        governance_main.app
    )

    destination = (
        "https"
        + ":"
        + "/"
        + "/"
        + "example.invalid/receive"
    )

    response = client.post(
        (
            f"/applications/{APPLICATION_ID}"
            "/controlled-egress"
        ),
        headers={"Authorization": "Bearer route-fixture"},
        json={
            "destination_url": destination,
            "content": "restricted test payload",
            "field_names": ["ssn"],
            "method": "POST",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["decision"] == "block"
    assert body["allowed"] is False
    assert body["executed"] is False
    assert body["upstream_status_code"] is None


def test_governance_policy_deny_prevents_egress(monkeypatch):
    monkeypatch.setattr(
        governance_main,
        "evaluate_policy_and_persist",
        lambda *_args: {"allowed": False},
    )

    executions = []
    monkeypatch.setattr(
        governance_main,
        "execute_controlled_egress",
        lambda *_args: executions.append(True),
    )

    response = TestClient(governance_main.app).post(
        f"/applications/{APPLICATION_ID}/controlled-egress",
        headers={"Authorization": "Bearer route-fixture"},
        json={
            "destination_url": "https://example.invalid/receive",
            "content": "synthetic",
        },
    )

    assert response.status_code == 403
    assert executions == []


def test_governance_policy_failure_prevents_egress(monkeypatch):
    from fastapi import HTTPException

    def unavailable(*_args):
        raise HTTPException(
            status_code=503,
            detail="OPA unavailable",
        )

    monkeypatch.setattr(
        governance_main,
        "evaluate_policy_and_persist",
        unavailable,
    )

    executions = []
    monkeypatch.setattr(
        governance_main,
        "execute_controlled_egress",
        lambda *_args: executions.append(True),
    )

    response = TestClient(governance_main.app).post(
        f"/applications/{APPLICATION_ID}/controlled-egress",
        headers={"Authorization": "Bearer route-fixture"},
        json={
            "destination_url": "https://example.invalid/receive",
            "content": "synthetic",
        },
    )

    assert response.status_code == 503
    assert executions == []
