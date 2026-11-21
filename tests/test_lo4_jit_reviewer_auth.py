"""LO4: JIT mutation endpoints require verified Vault identity."""

import io
import json
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import jit, reviewer_identity


ENTITY = "b800f336-5105-4fc2-bd64-44418d568ab1"
ACTOR = "vault:" + ENTITY
RECORD_ID = UUID("d29d43bc-501b-4cbe-bc54-6857af405adb")

CASES = [
    (
        f"/privileges/requests/{RECORD_ID}/decision",
        {
            "decision": "approve",
            "actor": ACTOR,
            "reason": "LO4 isolated authorization test",
        },
    ),
    (
        f"/privileges/grants/{RECORD_ID}/revoke",
        {
            "actor": ACTOR,
            "reason": "LO4 isolated authorization test",
        },
    ),
]


@pytest.fixture
def client():
    application = FastAPI()
    application.include_router(jit.jit_router)
    return TestClient(application)


def mock_vault(monkeypatch, policies):
    opener = MagicMock()

    data = json.dumps({
        "data": {
            "entity_id": ENTITY,
            "policies": policies,
        }
    }).encode()

    opener.open.side_effect = (
        lambda *args, **kwargs: io.BytesIO(data)
    )

    monkeypatch.setattr(
        reviewer_identity,
        "build_opener",
        lambda *args: opener,
    )


@pytest.mark.parametrize("path,payload", CASES)
@pytest.mark.parametrize(
    "mode,expected_status",
    [
        ("missing", 401),
        ("wrong_policy", 403),
        ("spoofed_actor", 403),
    ],
)
def test_jit_mutation_rejected_before_database(
    monkeypatch, client, path, payload, mode, expected_status
):
    def database_forbidden():
        raise AssertionError(
            "Unauthorized JIT mutation reached database"
        )

    monkeypatch.setattr(
        jit, "get_connection", database_forbidden
    )

    policies = (
        ["default"]
        if mode == "wrong_policy"
        else ["lcnc-security-reviewer"]
    )

    mock_vault(monkeypatch, policies)

    headers = (
        {}
        if mode == "missing"
        else {"Authorization": "Bearer isolated-test-token"}
    )

    body = dict(payload)

    if mode == "spoofed_actor":
        body["actor"] = "impersonated-reviewer"

    result = client.post(
        path,
        headers=headers,
        json=body,
    )

    assert result.status_code == expected_status


@pytest.mark.parametrize("path,payload", CASES)
@pytest.mark.parametrize(
    "policy",
    [
        "lcnc-security-reviewer",
        "lcnc-senior-security-reviewer",
    ],
)
def test_verified_jit_reviewer_reaches_read_only_lookup(
    monkeypatch, client, path, payload, policy
):
    mock_vault(monkeypatch, [policy])

    calls = []

    class MissingRecordConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, params):
            assert statement.lstrip().startswith("SELECT")
            calls.append("SELECT")
            return self

        def fetchone(self):
            return None

    monkeypatch.setattr(
        jit,
        "get_connection",
        lambda: MissingRecordConnection(),
    )

    result = client.post(
        path,
        headers={
            "Authorization": "Bearer isolated-test-token"
        },
        json=payload,
    )

    # Authentication succeeds, but the isolated fixture
    # contains no request/grant. No mutation can occur.
    assert result.status_code == 404
    assert calls == ["SELECT"]


@pytest.mark.parametrize("path,_payload", CASES)
def test_authorization_header_is_part_of_route_contract(
    client, path, _payload
):
    template = path.replace(
        str(RECORD_ID),
        "{request_id}" if "/requests/" in path else "{grant_id}",
    )

    route = client.app.openapi()["paths"][template]["post"]

    headers = {
        item["name"].lower()
        for item in route.get("parameters", [])
        if item.get("in") == "header"
    }

    assert "authorization" in headers
