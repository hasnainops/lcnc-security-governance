"""LO4.3 controlled-egress authorization boundary tests.

All execution, Vault, OPA, JIT, and persistence dependencies
are mocked. No real outbound requests are permitted.
"""

import sys
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "governance-api"))

from app import main as governance_main
from app.access_identity import ReviewerAccessError


APP_ID = UUID("11111111-2222-3333-4444-555555555555")
OTHER_APP_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

ENDPOINT = f"/applications/{APP_ID}/controlled-egress"

PAYLOAD = {
    "destination_url": "https://example.invalid/receive",
    "content": "Synthetic LO4.3 test content",
    "field_names": [],
    "method": "POST",
}


@pytest.fixture
def boundary(monkeypatch):
    calls = {
        "identity": [],
        "access": [],
        "jit": [],
        "governance": [],
        "execute": [],
    }

    state = {
        "access_allowed": True,
        "jit_active": True,
        "jit_action": "export",
        "jit_app_id": APP_ID,
        "jit_grant_id": "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb",
    }

    principal = {
        "subject_id": (
            "vault:11111111-2222-3333-4444-555555555555"
        ),
        "role": "developer",
    }

    def verify_identity(authorization):
        calls["identity"].append(True)

        if authorization is None:
            raise ReviewerAccessError(
                401,
                "An access bearer credential is required.",
            )

        if authorization != "Bearer lo4-fixture":
            raise ReviewerAccessError(
                403,
                "Access credential refused.",
            )

        return principal

    def authorize(application_id, request, authorization=None):
        calls["access"].append(
            (application_id, request, authorization)
        )

        return {
            "allowed": state["access_allowed"],
            "decision": (
                "allow"
                if state["access_allowed"]
                else "deny"
            ),
        }

    def check_jit(application_id, request, authorization=None):
        calls["jit"].append(
            (application_id, request, authorization)
        )

        active = (
            state["jit_active"]
            and application_id == state["jit_app_id"]
        )

        return {
            "active": active,
            "grant_id": (
                state["jit_grant_id"] if active else None
            ),
            "granted_action": (
                state["jit_action"] if active else None
            ),
        }

    def governance_policy(application_id):
        calls["governance"].append(application_id)
        return {"allowed": True}

    def execute(application_id, payload):
        calls["execute"].append(application_id)

        # Simulate a DLP BLOCK without an actual HTTP request.
        return {
            "application_id": str(application_id),
            "decision": "block",
            "allowed": False,
            "executed": False,
            "upstream_status_code": None,
            "reasons": ["restricted_data_external_transfer"],
        }

    monkeypatch.setattr(
        governance_main,
        "verified_access_principal",
        verify_identity,
    )

    monkeypatch.setattr(
        governance_main,
        "authorize_and_persist",
        authorize,
        raising=False,
    )

    monkeypatch.setattr(
        governance_main,
        "check_jit_privilege",
        check_jit,
        raising=False,
    )

    monkeypatch.setattr(
        governance_main,
        "evaluate_policy_and_persist",
        governance_policy,
    )

    monkeypatch.setattr(
        governance_main,
        "execute_controlled_egress",
        execute,
    )

    return TestClient(governance_main.app), calls, state


def test_missing_identity_blocks_before_any_execution(boundary):
    client, calls, _ = boundary

    response = client.post(
        ENDPOINT,
        json=PAYLOAD,
    )

    assert response.status_code == 401
    assert calls["access"] == []
    assert calls["jit"] == []
    assert calls["governance"] == []
    assert calls["execute"] == []


def test_invalid_identity_blocks_before_any_execution(boundary):
    client, calls, _ = boundary

    response = client.post(
        ENDPOINT,
        json=PAYLOAD,
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 403
    assert calls["access"] == []
    assert calls["jit"] == []
    assert calls["governance"] == []
    assert calls["execute"] == []


def test_valid_identity_without_export_grant_is_denied(boundary):
    client, calls, state = boundary
    state["jit_active"] = False

    response = client.post(
        ENDPOINT,
        json=PAYLOAD,
        headers={"Authorization": "Bearer lo4-fixture"},
    )

    assert response.status_code == 403
    assert calls["execute"] == []


def test_grant_for_another_application_cannot_export(boundary):
    client, calls, state = boundary
    state["jit_app_id"] = OTHER_APP_ID

    response = client.post(
        ENDPOINT,
        json=PAYLOAD,
        headers={"Authorization": "Bearer lo4-fixture"},
    )

    assert response.status_code == 403
    assert calls["execute"] == []


def test_opa_export_denial_prevents_execution(boundary):
    client, calls, state = boundary
    state["access_allowed"] = False

    response = client.post(
        ENDPOINT,
        json=PAYLOAD,
        headers={"Authorization": "Bearer lo4-fixture"},
    )

    assert response.status_code == 403
    assert calls["execute"] == []


def test_authorized_request_reaches_dlp_boundary(boundary):
    client, calls, _ = boundary

    response = client.post(
        ENDPOINT,
        json=PAYLOAD,
        headers={"Authorization": "Bearer lo4-fixture"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["decision"] == "block"
    assert body["executed"] is False

    assert len(calls["identity"]) == 1
    assert len(calls["access"]) == 1
    assert len(calls["jit"]) == 1
    assert calls["governance"] == [APP_ID]
    assert calls["execute"] == [APP_ID]

    application_id, request, authorization = calls["access"][0]

    assert application_id == APP_ID
    assert request.action == "export"
    assert request.role == "developer"
    assert request.subject_id.startswith("vault:")
    assert authorization == "Bearer lo4-fixture"

    jit_application, jit_request, jit_authorization = calls["jit"][0]

    assert jit_application == APP_ID
    assert jit_request.action == "export"
    assert jit_authorization == "Bearer lo4-fixture"


def test_non_export_grant_cannot_execute(boundary):
    client, calls, state = boundary
    state["jit_action"] = "read"

    response = client.post(
        ENDPOINT,
        json=PAYLOAD,
        headers={"Authorization": "Bearer lo4-fixture"},
    )

    assert response.status_code == 403
    assert calls["execute"] == []


def test_missing_jit_grant_identifier_denied(boundary):
    client, calls, state = boundary
    state["jit_grant_id"] = None

    response = client.post(
        ENDPOINT,
        json=PAYLOAD,
        headers={"Authorization": "Bearer lo4-fixture"},
    )

    assert response.status_code == 403
    assert calls["execute"] == []
