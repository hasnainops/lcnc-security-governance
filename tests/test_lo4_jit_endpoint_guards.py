"""LO4 authentication for JIT read and maintenance routes."""

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

APP_ID = UUID("12c59ac4-4f59-4a47-ac7c-a8e528e52c42")

CHECK = (
    f"/privileges/check?application_id={APP_ID}"
    f"&subject_id={SUBJECT}&action=export"
)

ROUTES = [
    ("get", "/privileges/requests"),
    ("get", "/privileges/grants"),
    ("post", "/privileges/expire/run"),
    ("get", CHECK),
]


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(jit.jit_router)
    return TestClient(app)


def mock_vault(monkeypatch, policies):
    opener = MagicMock()

    response = json.dumps({
        "data": {
            "entity_id": ENTITY,
            "policies": policies,
        }
    }).encode()

    opener.open.side_effect = (
        lambda *args, **kwargs: io.BytesIO(response)
    )

    monkeypatch.setattr(
        reviewer_identity,
        "build_opener",
        lambda *args: opener,
    )


@pytest.mark.parametrize("method,path", ROUTES)
@pytest.mark.parametrize(
    "mode,expected",
    [("missing", 401), ("wrong_policy", 403)],
)
def test_unauthorized_routes_do_not_touch_database(
    monkeypatch, client, method, path, mode, expected
):
    mock_vault(monkeypatch, ["default"])

    def forbidden():
        raise AssertionError(
            "Unauthorized request touched operational state"
        )

    monkeypatch.setattr(jit, "get_connection", forbidden)
    monkeypatch.setattr(jit, "expire_grants", forbidden)

    headers = (
        {}
        if mode == "missing"
        else {"Authorization": "Bearer isolated-test-token"}
    )

    response = getattr(client, method)(
        path, headers=headers
    )

    assert response.status_code == expected


def test_grant_check_prevents_subject_impersonation(
    monkeypatch, client
):
    mock_vault(
        monkeypatch, ["lcnc-access-developer"]
    )

    def forbidden():
        raise AssertionError(
            "Impersonated grant lookup reached database"
        )

    monkeypatch.setattr(jit, "get_connection", forbidden)

    response = client.get(
        "/privileges/check",
        params={
            "application_id": str(APP_ID),
            "subject_id": "different-user",
            "action": "export",
        },
        headers={
            "Authorization": "Bearer isolated-test-token"
        },
    )

    assert response.status_code == 403


def test_authenticated_subject_can_check_own_grants(
    monkeypatch, client
):
    mock_vault(
        monkeypatch, ["lcnc-access-developer"]
    )

    statements = []

    class NoGrantConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):
            assert sql.lstrip().startswith("SELECT")
            assert params[1] == SUBJECT
            statements.append(sql)
            return self

        def fetchone(self):
            return None

    monkeypatch.setattr(
        jit,
        "get_connection",
        lambda: NoGrantConnection(),
    )

    response = client.get(
        CHECK,
        headers={
            "Authorization": "Bearer isolated-test-token"
        },
    )

    assert response.status_code == 200
    assert response.json()["active"] is False
    assert len(statements) == 1


@pytest.mark.parametrize(
    "policy",
    [
        "lcnc-security-reviewer",
        "lcnc-senior-security-reviewer",
    ],
)
@pytest.mark.parametrize(
    "method,path",
    ROUTES[:3],
)
def test_reviewer_can_reach_admin_routes(
    monkeypatch, client, policy, method, path
):
    mock_vault(monkeypatch, [policy])

    class EmptyConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            assert sql.lstrip().startswith("SELECT")
            return self

        def fetchall(self):
            return []

    monkeypatch.setattr(
        jit,
        "get_connection",
        lambda: EmptyConnection(),
    )

    monkeypatch.setattr(
        jit,
        "expire_grants",
        lambda: 0,
    )

    response = getattr(client, method)(
        path,
        headers={
            "Authorization": "Bearer isolated-test-token"
        },
    )

    assert response.status_code == 200


def test_all_guarded_routes_expose_auth_header(client):
    paths = [
        ("/privileges/requests", "get"),
        ("/privileges/grants", "get"),
        ("/privileges/check", "get"),
        ("/privileges/expire/run", "post"),
    ]

    openapi = client.app.openapi()

    for path, method in paths:
        operation = openapi["paths"][path][method]

        headers = {
            item["name"].lower()
            for item in operation.get("parameters", [])
            if item.get("in") == "header"
        }

        assert "authorization" in headers
