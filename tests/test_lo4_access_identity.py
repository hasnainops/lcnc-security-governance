"""LO4: authenticated access-evaluation boundary."""

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app import access_identity, main


ENTITY = "a84be332-d855-42cb-a442-419509c5d26f"
SUBJECT = "vault:" + ENTITY
APP_ID = UUID("12c59ac4-4f59-4a47-ac7c-a8e528e52c42")

URL = f"/applications/{APP_ID}/authorize"


@pytest.fixture
def client():
    return TestClient(main.app)


def mock_vault(monkeypatch, policies, entity=ENTITY):
    opener = MagicMock()

    encoded = json.dumps({
        "data": {
            "entity_id": entity,
            "policies": policies,
        }
    }).encode()

    opener.open.side_effect = (
        lambda *args, **kwargs: io.BytesIO(encoded)
    )

    monkeypatch.setattr(
        access_identity,
        "build_opener",
        lambda *args: opener,
    )


def access_body(subject=SUBJECT, role="developer"):
    return {
        "subject_id": subject,
        "role": role,
        "action": "read",
    }


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("missing", 401),
        ("invalid_token_format", 401),
        ("unauthorized_policy", 403),
        ("invalid_identity", 403),
        ("subject_spoof", 403),
        ("role_spoof", 403),
    ],
)
def test_unauthorized_access_never_reaches_evaluation(
    monkeypatch, client, scenario, expected
):
    policies = (
        ["default"]
        if scenario == "unauthorized_policy"
        else ["lcnc-access-developer"]
    )

    entity = (
        ""
        if scenario == "invalid_identity"
        else ENTITY
    )

    mock_vault(monkeypatch, policies, entity)

    def forbidden_evaluation(*args, **kwargs):
        raise AssertionError(
            "Unauthorized caller reached access evaluation"
        )

    monkeypatch.setattr(
        main,
        "authorize_and_persist",
        forbidden_evaluation,
    )

    body = access_body()

    if scenario == "subject_spoof":
        body["subject_id"] = "another-user"

    if scenario == "role_spoof":
        body["role"] = "security_admin"

    if scenario == "missing":
        headers = {}
    elif scenario == "invalid_token_format":
        headers = {"Authorization": "Bearer invalid token"}
    else:
        headers = {
            "Authorization": "Bearer isolated-test-token"
        }

    response = client.post(
        URL,
        json=body,
        headers=headers,
    )

    assert response.status_code == expected


@pytest.mark.parametrize(
    "policy,role",
    [
        ("lcnc-access-viewer", "viewer"),
        ("lcnc-access-developer", "developer"),
        ("lcnc-security-reviewer", "security_admin"),
        ("lcnc-senior-security-reviewer", "security_admin"),
    ],
)
def test_verified_principal_reaches_access_evaluation(
    monkeypatch, client, policy, role
):
    mock_vault(monkeypatch, [policy])

    calls = []

    def fake_evaluation(application_id, payload, authorization=None):
        calls.append((application_id, payload))
        return {
            "application_id": str(application_id),
            "subject_id": payload.subject_id,
            "role": payload.role,
            "allowed": False,
            "decision": "deny",
        }

    monkeypatch.setattr(
        main,
        "authorize_and_persist",
        fake_evaluation,
    )

    response = client.post(
        URL,
        headers={
            "Authorization": "Bearer isolated-test-token"
        },
        json=access_body(role=role),
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == APP_ID
    assert calls[0][1].subject_id == SUBJECT
    assert calls[0][1].role == role
    assert response.status_code == 200


def test_authorization_header_is_in_api_contract(client):
    route = client.app.openapi()["paths"][
        "/applications/{application_id}/authorize"
    ]["post"]

    headers = {
        parameter["name"].lower()
        for parameter in route.get("parameters", [])
        if parameter.get("in") == "header"
    }

    assert "authorization" in headers


def test_role_mapping_matches_automation():
    path = Path(
        "governance-automation/app/reviewer_identity.py"
    )

    spec = importlib.util.spec_from_file_location(
        "lo4_automation_identity_parity", path
    )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert access_identity.ACCESS_ROLE_POLICIES == (
        module.ACCESS_ROLE_POLICIES
    )
