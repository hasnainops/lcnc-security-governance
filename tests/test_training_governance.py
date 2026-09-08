import importlib
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test:test@localhost:5432/test",
)

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_APP_DIR = ROOT / "governance-api" / "app"

PACKAGE_NAME = "governance_api_training_app"

package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(GOVERNANCE_APP_DIR)]
sys.modules[PACKAGE_NAME] = package

training = importlib.import_module(
    f"{PACKAGE_NAME}.training"
)


APPLICATION_ID = UUID(
    "11111111-2222-3333-4444-555555555555"
)

SUBJECT_ID = "citizen@example.com"


class FakeResult:
    def __init__(self, *, one=None, all_rows=None):
        self.one = one
        self.all_rows = (
            all_rows
            if all_rows is not None
            else []
        )

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.all_rows


class ScriptedConnection:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.committed = False

    def execute(self, sql, values=None):
        self.calls.append(
            {
                "sql": sql,
                "values": values,
            }
        )

        if not self.results:
            raise AssertionError(
                "Unexpected database execute call."
            )

        return self.results.pop(0)

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False


def test_complete_training_rejects_unknown_module():
    payload = training.TrainingCompletionRequest(
        subject_id=SUBJECT_ID,
        module_id="not-a-real-module",
    )

    with pytest.raises(HTTPException) as exc:
        training.complete_training(
            APPLICATION_ID,
            payload,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == (
        "Unknown citizen-developer training module."
    )


def test_complete_training_returns_404_for_missing_application(
    monkeypatch,
):
    connection = ScriptedConnection(
        [
            FakeResult(one=None),
        ]
    )

    monkeypatch.setattr(
        training,
        "get_connection",
        lambda: connection,
    )

    payload = training.TrainingCompletionRequest(
        subject_id=SUBJECT_ID,
        module_id="integration-security",
    )

    with pytest.raises(HTTPException) as exc:
        training.complete_training(
            APPLICATION_ID,
            payload,
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Application not found"


def test_complete_training_persists_completion_and_assignment(
    monkeypatch,
):
    completion_id = uuid4()
    assignment_id = uuid4()
    completed_at = datetime.now(timezone.utc)

    completion = {
        "id": completion_id,
        "module_id": "integration-security",
        "completed_at": completed_at,
    }

    assignment = {
        "id": assignment_id,
        "application_id": APPLICATION_ID,
        "subject_id": SUBJECT_ID,
        "module_id": "integration-security",
        "status": "completed",
        "required": True,
    }

    connection = ScriptedConnection(
        [
            FakeResult(
                one={
                    "id": APPLICATION_ID,
                }
            ),
            FakeResult(one=completion),
            FakeResult(one=assignment),
            FakeResult(),
        ]
    )

    monkeypatch.setattr(
        training,
        "get_connection",
        lambda: connection,
    )

    expected_status = {
        "completion_rate": 100,
        "approval_ready": True,
    }

    monkeypatch.setattr(
        training,
        "get_training_status",
        lambda application_id, subject_id: (
            expected_status
        ),
    )

    payload = training.TrainingCompletionRequest(
        subject_id=SUBJECT_ID,
        module_id="integration-security",
    )

    result = training.complete_training(
        APPLICATION_ID,
        payload,
    )

    assert result["completion"] == completion
    assert result["assignment"] == assignment
    assert (
        result["training_status"]
        == expected_status
    )

    assert connection.committed is True

    sql = "\n".join(
        call["sql"]
        for call in connection.calls
    )

    assert "training_completions" in sql
    assert "status = 'completed'" in sql
    assert "training_events" in sql


def test_refresh_overdue_assignments_records_event(
    monkeypatch,
):
    assignment_id = uuid4()

    assignment = {
        "id": assignment_id,
        "module_id": "integration-security",
        "subject_id": SUBJECT_ID,
        "due_at": (
            datetime.now(timezone.utc)
            - timedelta(days=1)
        ),
    }

    connection = ScriptedConnection(
        [
            FakeResult(
                all_rows=[assignment]
            ),
            FakeResult(),
        ]
    )

    monkeypatch.setattr(
        training,
        "get_connection",
        lambda: connection,
    )

    count = training.refresh_overdue_assignments(
        APPLICATION_ID
    )

    assert count == 1
    assert connection.committed is True

    assert (
        "UPDATE training_assignments"
        in connection.calls[0]["sql"]
    )

    assert (
        "application_id = %s"
        in connection.calls[0]["sql"]
    )

    assert (
        "INSERT INTO training_events"
        in connection.calls[1]["sql"]
    )

    event_values = connection.calls[1][
        "values"
    ]

    assert event_values[1] == assignment_id
    assert event_values[2] == "training_overdue"


def test_get_training_status_calculates_progress_and_gate(
    monkeypatch,
):
    guidance = {
        "application_id": APPLICATION_ID,
        "application_name": "Training Demo",
        "security_score": 80,
        "badge": "silver",
        "recommended_training": [
            {
                "module_id": (
                    "integration-security"
                ),
            },
            {
                "module_id": (
                    "data-classification"
                ),
            },
        ],
    }

    monkeypatch.setattr(
        training,
        "build_guidance",
        lambda application_id: guidance,
    )

    monkeypatch.setattr(
        training,
        "refresh_overdue_assignments",
        lambda application_id=None: 0,
    )

    completed = [
        {
            "module_id": (
                "integration-security"
            ),
            "completed_at": (
                datetime.now(timezone.utc)
            ),
        }
    ]

    assignments = [
        {
            "id": uuid4(),
            "module_id": (
                "data-classification"
            ),
            "subject_id": SUBJECT_ID,
            "required": True,
            "status": "assigned",
        }
    ]

    connection = ScriptedConnection(
        [
            FakeResult(
                all_rows=completed
            ),
            FakeResult(
                all_rows=assignments
            ),
        ]
    )

    monkeypatch.setattr(
        training,
        "get_connection",
        lambda: connection,
    )

    result = training.get_training_status(
        APPLICATION_ID,
        SUBJECT_ID,
    )

    assert result["completion_rate"] == 50
    assert (
        result["achievement"]
        == "security_progress"
    )
    assert (
        result["completed_recommended_count"]
        == 1
    )
    assert (
        result["required_incomplete_count"]
        == 1
    )
    assert result["approval_ready"] is False


def test_assign_required_training_creates_new_assignment(
    monkeypatch,
):
    recommendation = {
        "module_id": "integration-security",
        "trigger_control": "CTRL-03",
        "control_status": "fail",
        "reason": (
            "Unapproved integration detected."
        ),
    }

    guidance = {
        "application_id": APPLICATION_ID,
        "application_name": "Training Demo",
        "recommended_training": [
            recommendation
        ],
    }

    monkeypatch.setattr(
        training,
        "build_guidance",
        lambda application_id: guidance,
    )

    assignment_id = uuid4()

    assignment = {
        "id": assignment_id,
        "application_id": APPLICATION_ID,
        "subject_id": SUBJECT_ID,
        "module_id": "integration-security",
        "required": True,
        "status": "assigned",
    }

    connection = ScriptedConnection(
        [
            FakeResult(
                one={
                    "id": APPLICATION_ID,
                    "name": "Training Demo",
                    "owner_name": "Citizen Developer",
                    "owner_email": SUBJECT_ID,
                }
            ),
            FakeResult(
                all_rows=[]
            ),
            FakeResult(
                one=assignment
            ),
            FakeResult(),
        ]
    )

    monkeypatch.setattr(
        training,
        "get_connection",
        lambda: connection,
    )

    monkeypatch.setattr(
        training,
        "refresh_overdue_assignments",
        lambda application_id=None: 0,
    )

    monkeypatch.setattr(
        training,
        "get_training_assignments",
        lambda application_id: {
            "application_id": application_id,
            "application_name": (
                "Training Demo"
            ),
            "count": 1,
            "assignments": [
                assignment
            ],
        },
    )

    result = training.assign_required_training(
        APPLICATION_ID
    )

    assert result["status"] == "evaluated"
    assert result["subject_id"] == SUBJECT_ID
    assert (
        result["recommended_training_count"]
        == 1
    )
    assert (
        result["required_incomplete_count"]
        == 1
    )
    assert result["approval_ready"] is False

    assert connection.committed is True

    sql = "\n".join(
        call["sql"]
        for call in connection.calls
    )

    assert (
        "INSERT INTO training_assignments"
        in sql
    )

    assert "INSERT INTO training_events" in sql
