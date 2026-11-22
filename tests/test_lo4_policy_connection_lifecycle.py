"""Regression for the closed connection in LO4.3 governance."""

import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "governance-api"))

from app import policy


APPLICATION = {
    "name": "Synthetic LO4 fixture",
    "registration_status": "registered",
    "data_classification": "confidential",
    "internet_exposed": False,
    "external_integration": False,
    "integration_approved": False,
    "external_integration_count": 0,
    "unapproved_integration_count": 0,
    "credential_type": "none",
    "risk_score": 10,
    "risk_level": "low",
}


class FakeConnection:

    def __init__(self):
        self.closed = False
        self.operations = []

    def execute(self, sql, params):

        assert not self.closed, (
            "Attempted to reuse a closed database connection"
        )

        if "SELECT" in sql:
            self.operations.append("read")
            return SimpleNamespace(
                fetchone=lambda: APPLICATION
            )

        if "INSERT INTO policy_decisions" in sql:
            self.operations.append("write")

            decision = {
                "id": params[0],
                "action": params[2],
                "allowed": params[3],
                "reasons": [],
                "policy_version": params[5],
                "evaluated_at": None,
            }

            return SimpleNamespace(
                fetchone=lambda: decision
            )

        raise AssertionError("Unexpected SQL")


@pytest.mark.parametrize("caller_owned", [False, True])
@pytest.mark.parametrize("persist", [False, True])
def test_policy_connection_lifecycle(
    monkeypatch,
    caller_owned,
    persist,
):
    opened = []

    @contextmanager
    def get_connection():
        connection = FakeConnection()
        opened.append(connection)

        try:
            yield connection
        finally:
            connection.closed = True

    monkeypatch.setattr(
        policy,
        "get_connection",
        get_connection,
    )

    monkeypatch.setattr(
        policy.httpx,
        "post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "result": {
                    "action": "allow",
                    "allow": True,
                    "reasons": [],
                }
            },
        ),
    )

    external = (
        FakeConnection()
        if caller_owned
        else None
    )

    result = policy.evaluate_and_persist(
        uuid4(),
        connection=external,
        persist=persist,
    )

    assert result["allowed"] is True

    expected = (
        ["read", "write"]
        if persist
        else ["read"]
    )

    if caller_owned:
        assert opened == []
        assert external.closed is False
        assert external.operations == expected

    else:
        assert len(opened) == (2 if persist else 1)

        assert all(
            connection.closed
            for connection in opened
        )

        actual = [
            operation
            for connection in opened
            for operation in connection.operations
        ]

        assert actual == expected
