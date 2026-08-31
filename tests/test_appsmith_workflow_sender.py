import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MODULE_PATH = (
    ROOT
    / "discovery"
    / "appsmith_discovery.py"
)

spec = importlib.util.spec_from_file_location(
    "appsmith_workflow_sender_test",
    MODULE_PATH,
)

discovery = importlib.util.module_from_spec(spec)

spec.loader.exec_module(discovery)


def test_sends_only_sanitized_workflow_metadata(
    monkeypatch,
):
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "canonical-application-id",
                "security_scan_status": "stale",
            }

    def fake_post(
        url,
        json,
        timeout,
    ):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout

        return FakeResponse()

    monkeypatch.setattr(
        discovery.httpx,
        "post",
        fake_post,
    )

    metadata = {
        "page_count": 1,
        "widget_count": 23,
        "action_count": 9,
        "api_action_count": 9,
        "dynamic_binding_count": 8,
        "invalid_action_count": 0,
        "http_action_count": 7,
        "https_action_count": 0,
        "sensitive_header_action_count": 0,
    }

    result = (
        discovery
        .send_workflow_security_metadata(
            "canonical-application-id",
            metadata,
        )
    )

    assert captured["url"] == (
        "http://governance-api:8000"
        "/applications/"
        "canonical-application-id"
        "/observed-workflow-security"
    )

    assert captured["json"] == metadata
    assert captured["timeout"] == 10.0

    assert (
        result["security_scan_status"]
        == "stale"
    )

    serialized = str(
        captured["json"]
    )

    assert "password" not in serialized.lower()
    assert "token" not in serialized.lower()
    assert "authorization" not in serialized.lower()
