import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "governance-api"),
)

from app import ml


@pytest.mark.parametrize(
    "platform,registration,anomalous,diagnostic,previous,expected",
    [
        ("appsmith", "unregistered", True, False, False, True),
        ("appsmith", "registered", True, False, False, False),
        ("appsmith", "unregistered", False, False, False, False),
        ("appsmith", "unregistered", True, True, False, False),
        ("powerapps", "unregistered", True, False, True, True),
    ],
)
def test_shadow_candidate_persistence_bindings(
    monkeypatch,
    platform,
    registration,
    anomalous,
    diagnostic,
    previous,
    expected,
):
    application_id = uuid4()
    application = {
        "id": application_id,
        "name": "LO1 Synthetic Verification",
        "platform": platform,
        "registration_status": registration,
        "owner_name": "Test Owner",
        "owner_email": None,
        "business_purpose": "Security validation",
        "internet_exposed": False,
        "credential_type": None,
        "shadow_it_candidate": previous,
        **{feature: 1 for feature in ml.OBSERVED_FEATURES},
    }

    updates = []

    class Result:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def execute(self, query, params=None):
            normalized = " ".join(query.split())

            if "SELECT * FROM applications" in normalized:
                return Result(application)

            if "INSERT INTO ml_assessments" in normalized:
                return Result()

            if "UPDATE applications" in normalized:
                updates.append((normalized, params))

                assert "shadow_it_candidate = CASE" in normalized
                assert "LOWER(platform) = 'appsmith'" in normalized
                assert "registration_status = 'unregistered'" in normalized
                assert "ELSE shadow_it_candidate" in normalized

                assert len(params) == 7
                assert params[0] == (
                    "diagnostic" if diagnostic else "assessed"
                )
                assert params[1] is anomalous
                assert params[2] == params[0]
                assert params[3] is anomalous
                assert params[-1] == application_id

                return Result({
                    **application,
                    "ml_anomaly_status": params[0],
                    "ml_assessed_at": "synthetic-test",
                    "shadow_it_candidate": expected,
                })

            raise AssertionError("Unexpected SQL statement")

    @contextmanager
    def fake_connection():
        yield Connection()

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "analysis_type": "isolation_forest",
                "anomalous": anomalous,
                "raw_decision_score": -0.03,
                "model_version": "synthetic-test",
                "context_signals": [],
            }

    monkeypatch.setattr(ml, "get_connection", fake_connection)
    monkeypatch.setattr(
        ml.httpx,
        "post",
        lambda *args, **kwargs: Response(),
    )

    options = {}
    if diagnostic:
        options = {
            "diagnostic_features": {
                feature: 1 for feature in ml.OBSERVED_FEATURES
            },
            "diagnostic_provenance": {
                "assessment_tier": "cold_start_witnessed",
                "certified_24h": False,
                "witnessed_changes": 1,
                "observation_fingerprint": "synthetic",
                "source_observation_id": "synthetic-observation",
            },
        }

    result = ml.analyze_and_persist(
        application_id,
        **options,
    )

    assert len(updates) == 1
    assert result["ml_anomaly_status"] == (
        "diagnostic" if diagnostic else "assessed"
    )
    assert result["shadow_it_candidate"] is expected
