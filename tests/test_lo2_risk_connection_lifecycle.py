from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import assessment, risk_orchestration


APPLICATION = {
    "name": "LO2 Risk Fixture",
    "registration_status": "registered",
    "owner_name": "Test Owner",
    "business_purpose": "Regression test",
    "data_classification": "internal",
    "internet_exposed": False,
    "external_integration": False,
    "integration_approved": True,
    "external_integration_count": 0,
    "unapproved_integration_count": 0,
    "credential_type": None,
    "risk_status": "stale",
}


class FakeConnection:

    def __init__(self):
        self.closed = False
        self.queries = []
        self.row = None

    def __enter__(self):
        assert not self.closed
        return self

    def __exit__(self, *_args):
        self.closed = True

    def execute(self, query, params=None):
        assert not self.closed, "Closed connection reused"
        self.queries.append(query)

        if "FROM applications" in query:
            self.row = APPLICATION.copy()

        elif "UPDATE applications" in query:
            self.row = {
                "name": APPLICATION["name"],
                "risk_status": "assessed",
                "risk_assessed_at": datetime.now(timezone.utc),
            }

        return self

    def fetchone(self):
        return self.row


@pytest.mark.parametrize("borrowed", [False, True])
def test_assessment_connection_lifecycle(monkeypatch, borrowed):

    created = []

    def connect():
        connection = FakeConnection()
        created.append(connection)
        return connection

    monkeypatch.setattr(assessment, "get_connection", connect)

    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "score": 10,
            "level": "low",
            "model_version": "test",
            "factors": [],
        },
    )

    monkeypatch.setattr(
        assessment.httpx,
        "post",
        lambda *_args, **_kwargs: response,
    )

    supplied = FakeConnection() if borrowed else None

    result = assessment.assess_and_persist(
        uuid4(),
        connection=supplied,
    )

    assert result["risk_status"] == "assessed"

    if borrowed:
        assert not created
        assert not supplied.closed
        queries = supplied.queries
    else:
        assert len(created) == 2
        assert all(c.closed for c in created)
        queries = [q for c in created for q in c.queries]

    assert any("INSERT INTO risk_assessments" in q for q in queries)
    assert any("UPDATE applications" in q for q in queries)


def test_orchestration_reuses_locked_transaction(monkeypatch):

    connection = FakeConnection()
    app_id = uuid4()

    monkeypatch.setattr(
        risk_orchestration,
        "get_connection",
        lambda: connection,
    )

    def assess(application_id, *, connection=None):
        assert application_id == app_id
        assert connection is not None
        assert not connection.closed
        assert any(
            "pg_advisory_xact_lock" in q
            for q in connection.queries
        )

        return {
            "assessment_id": uuid4(),
            "risk_status": "assessed",
            "score": 10,
            "level": "low",
        }

    monkeypatch.setattr(
        risk_orchestration,
        "assess_and_persist",
        assess,
    )

    result = risk_orchestration.assess_risk_if_needed(app_id)

    assert result["action"] == "assessed"
    assert connection.closed
