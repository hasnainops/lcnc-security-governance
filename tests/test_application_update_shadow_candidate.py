import os
import sys
from pathlib import Path
from uuid import uuid4

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test:test@localhost:5432/test",
)

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_API = ROOT / "governance-api"

sys.path.insert(
    0,
    str(GOVERNANCE_API),
)

from app import main as governance_main
from app.models import ApplicationUpdate


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.calls.append((normalized, params))

        return FakeResult(
            {
                "id": params[-1],
                "owner_name": "Updated Owner",
                "ml_anomaly_status": "stale",
                "ml_anomalous": None,
                "shadow_it_candidate": False,
            }
        )


class FakeConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def test_application_update_clears_shadow_it_candidate(
    monkeypatch,
):
    connection = FakeConnection()

    monkeypatch.setattr(
        governance_main,
        "get_connection",
        lambda: FakeConnectionContext(connection),
    )

    application_id = uuid4()

    result = governance_main.update_application(
        application_id,
        ApplicationUpdate(
            owner_name="Updated Owner",
        ),
    )

    assert len(connection.calls) == 1

    query, params = connection.calls[0]

    assert "ml_anomaly_status = 'stale'" in query
    assert "ml_anomalous = NULL" in query
    assert "shadow_it_candidate = FALSE" in query

    assert params[-1] == application_id
    assert result["shadow_it_candidate"] is False
