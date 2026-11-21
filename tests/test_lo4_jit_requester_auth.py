"""LO4 JIT requester identity and role authorization tests."""

import io
import json
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import jit, reviewer_identity


ENTITY = "a84be332-d855-42cb-a442-419509c5d26f"
SUBJECT = "vault:" + ENTITY
APPLICATION = UUID("12c59ac4-4f59-4a47-ac7c-a8e528e52c42")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(jit.jit_router)
    return TestClient(app)


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
        reviewer_identity,
        "build_opener",
        lambda *args: opener,
    )


def request_body(subject=SUBJECT, role="developer"):
    return {
        "application_id": str(APPLICATION),
        "subject_id": subject,
        "base_role": role,
        "requested_action": "export",
        "justification": "Isolated LO4 authorization test",
        "requested_duration_minutes": 15,
    }


@pytest.mark.parametrize(
    "mode,status",
    [
        ("missing", 401),
        ("unauthorized_policy", 403),
        ("subject_spoof", 403),
        ("role_spoof", 403),
        ("invalid_entity", 403),
    ],
)
def test_unauthorized_jit_request_never_reaches_database(
    monkeypatch, client, mode, status
):
    policies = (
        ["default"]
        if mode == "unauthorized_policy"
        else ["lcnc-access-developer"]
    )

    entity = "" if mode == "invalid_entity" else ENTITY

    mock_vault(monkeypatch, policies, entity)

    def forbidden_database():
        raise AssertionError(
            "Unauthorized request reached PostgreSQL"
        )

    monkeypatch.setattr(
        jit, "get_connection", forbidden_database
    )

    headers = (
        {}
        if mode == "missing"
        else {"Authorization": "Bearer isolated-token"}
    )

    body = request_body()

    if mode == "subject_spoof":
        body["subject_id"] = "another-user"

    if mode == "role_spoof":
        body["base_role"] = "security_admin"

    response = client.post(
        "/privileges/requests",
        json=body,
        headers=headers,
    )

    assert response.status_code == status


@pytest.mark.parametrize(
    "policy,role",
    [
        ("lcnc-access-viewer", "viewer"),
        ("lcnc-access-developer", "developer"),
        ("lcnc-security-reviewer", "security_admin"),
        ("lcnc-senior-security-reviewer", "security_admin"),
    ],
)
def test_verified_requester_reaches_only_application_lookup(
    monkeypatch, client, policy, role
):
    mock_vault(monkeypatch, [policy])

    statements = []

    class MissingApplication:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):
            assert sql.lstrip().startswith("SELECT")
            statements.append(sql)
            return self

        def fetchone(self):
            return None

    monkeypatch.setattr(
        jit,
        "get_connection",
        lambda: MissingApplication(),
    )

    response = client.post(
        "/privileges/requests",
        headers={
            "Authorization": "Bearer isolated-token"
        },
        json=request_body(role=role),
    )

    assert response.status_code == 404
    assert len(statements) == 1


def test_jit_request_exposes_authorization_header(client):
    operation = client.app.openapi()["paths"][
        "/privileges/requests"
    ]["post"]

    headers = {
        parameter["name"].lower()
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "header"
    }

    assert "authorization" in headers
