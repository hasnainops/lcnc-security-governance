from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
import pytest

from app import appsmith_publish as publish
from app import compliance_assessment as assessment
from app import dynamic_compliance as compliance


def test_compliance_review_reuses_locked_connection(monkeypatch):
    application_id = uuid4()

    application = {
        "id": application_id,
        "name": "Transaction regression fixture",
        "platform": "appsmith",
        "external_id": "native-fixture",
        "owner_name": "Test owner",
        "owner_email": None,
        "data_classification": "internal",
        "external_integration_count": 0,
        "unapproved_integration_count": 0,
        "connector_metadata": [],
        "security_scan_status": "scanned",
        "security_scan_passed": True,
        "governance_status": "pending_review",
        "governance_outcome": "SECURITY_REVIEW",
    }

    queries = []
    connection = MagicMock()

    def execute(sql, params=None):
        normalized = " ".join(sql.lower().split())
        queries.append(normalized)

        if "from applications" in normalized:
            if "external_id=" in normalized:
                # Exercise the real publication guard's lock path,
                # then stop at its normal missing-application denial.
                return SimpleNamespace(fetchall=lambda: [])

            return SimpleNamespace(
                fetchone=lambda: application
            )

        return SimpleNamespace(fetchone=lambda: None)

    connection.execute.side_effect = execute

    @contextmanager
    def owned_connection():
        yield connection

    def unexpected_connection():
        pytest.fail("Nested database connection opened")

    monkeypatch.setattr(
        assessment, "get_connection", owned_connection
    )

    monkeypatch.setattr(
        compliance, "get_connection", unexpected_connection
    )

    monkeypatch.setattr(
        publish, "get_connection", unexpected_connection
    )

    class EvaluationCompleted(Exception):
        pass

    original = compliance.evaluate_dynamic_compliance

    def capture(app_id, **kwargs):
        assert kwargs["connection"] is connection

        result = original(app_id, **kwargs)

        ctrl07 = next(
            control for control in result["controls"]
            if control["control_id"] == "CTRL-07"
        )

        assert ctrl07["status"] == "not_assessed"

        # Stop after the complete evaluation path. Persistence is
        # covered by the existing compliance assessment suite.
        raise EvaluationCompleted

    monkeypatch.setattr(
        assessment, "evaluate_dynamic_compliance", capture
    )

    with pytest.raises(EvaluationCompleted):
        assessment.assess_if_needed(application_id)

    locks = [
        query for query in queries
        if "for update" in query
    ]

    assert len(locks) == 2
    assert all("applications" in query for query in locks)

    connection.transaction.assert_called_once_with()


def test_review_database_failure_isolated_by_savepoint(monkeypatch):
    connection = MagicMock()
    events = []

    @contextmanager
    def savepoint():
        events.append("entered")
        try:
            yield
        except psycopg.Error:
            events.append("rolled_back")
            raise

    connection.transaction.side_effect = savepoint

    def fail_review(*args, **kwargs):
        assert kwargs["connection"] is connection
        assert kwargs["record_receipt"] is False
        raise psycopg.errors.LockNotAvailable(
            "Simulated database failure"
        )

    monkeypatch.setattr(
        publish, "check_publish", fail_review
    )

    application = {
        "id": uuid4(),
        "platform": "appsmith",
        "external_id": "native-fixture",
        "governance_status": "pending_review",
        "governance_outcome": "SECURITY_REVIEW",
    }

    result = compliance.current_reviewed_release(
        application,
        connection=connection,
    )

    assert result is None
    assert events == ["entered", "rolled_back"]
