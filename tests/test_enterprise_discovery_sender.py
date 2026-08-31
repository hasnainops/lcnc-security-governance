import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test:test@localhost:5432/test",
)

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "enterprise-discovery"
    / "app"
    / "main.py"
)

spec = importlib.util.spec_from_file_location(
    "enterprise_discovery_sender_test",
    MODULE_PATH,
)

enterprise_discovery = importlib.util.module_from_spec(
    spec
)

spec.loader.exec_module(
    enterprise_discovery
)


def make_record():
    return {
        "source": "generic_security_feed",
        "external_id": "shadow-app-001",
        "name": "Shadow Finance Export",
        "platform": "appsmith",
        "authorization_status": "unknown",
        "owner_known": False,
        "business_purpose_known": False,
        "internet_exposed": True,
        "uses_api_key": True,
        "external_integration_count": 2,
        "unapproved_integration_count": 1,
        "connector_count": 3,
        "external_domain_count": 2,
        "changes_last_24h": 4,
        "evidence": [
            "Observed by enterprise security feed",
        ],
        "observed_at": datetime.now(
            timezone.utc
        ),
    }


def make_ml():
    return {
        "status": "assessed",
        "result": {
            "analysis_type": "shadow-it-anomaly",
            "anomalous": True,
            "raw_decision_score": -0.271,
            "model_version": "isolation-forest-v1",
            "context_signals": [
                "application is internet exposed",
            ],
        },
    }


def test_handoff_sends_existing_ml_result_without_reanalysis(
    monkeypatch,
):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def read(self):
            return json.dumps(
                {
                    "application_id": "canonical-app-id",
                    "action": "created",
                }
            ).encode()

    def fake_urlopen(
        request,
        timeout,
    ):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["payload"] = json.loads(
            request.data.decode()
        )
        captured["timeout"] = timeout

        return FakeResponse()

    monkeypatch.setattr(
        enterprise_discovery.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    result = (
        enterprise_discovery
        .handoff_to_governance(
            make_record(),
            make_ml(),
        )
    )

    assert captured["url"] == (
        "http://governance-api:8000"
        "/enterprise-discovery/handoff"
    )

    assert captured["method"] == "POST"

    assert (
        captured["payload"]["ml_result"]
        == make_ml()["result"]
    )

    assert (
        captured["payload"]["external_id"]
        == "shadow-app-001"
    )

    assert result["status"] == "handed_off"
    assert result["application"]["action"] == "created"
