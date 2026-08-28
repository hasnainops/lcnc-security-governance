import sys
from pathlib import Path
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_API = ROOT / "governance-api"

sys.path.insert(
    0,
    str(GOVERNANCE_API),
)

from app import integration


APPLICATION_ID = UUID(
    "11111111-2222-3333-4444-555555555555"
)


def test_blocked_transfer_never_executes_outbound_request(
    monkeypatch,
):
    outbound_called = False

    def fake_evaluate(
        application_id,
        payload,
    ):
        assert application_id == APPLICATION_ID

        return {
            "event_id": (
                "22222222-3333-4444-5555-666666666666"
            ),
            "application_id": application_id,
            "application_name": "Controlled Egress Test",
            "destination": {
                "scheme": "https",
                "host": "example.invalid",
                "trust": "unapproved_external",
            },
            "declared_classification": "restricted",
            "effective_sensitivity": "restricted",
            "decision": "block",
            "allowed": False,
            "reasons": [
                "destination_not_approved",
                "restricted_data_external_transfer",
            ],
            "dlp": {
                "engine_version": "dlp-v1",
                "sensitive_data_detected": True,
                "finding_count": 1,
                "highest_sensitivity": "restricted",
                "detected_types": [
                    "social_security_number",
                ],
            },
            "evaluated_at": None,
        }

    def fake_request(*args, **kwargs):
        nonlocal outbound_called
        outbound_called = True

        raise AssertionError(
            "Blocked transfer executed outbound HTTP"
        )

    monkeypatch.setattr(
        integration,
        "evaluate_and_persist",
        fake_evaluate,
    )

    monkeypatch.setattr(
        integration.httpx,
        "request",
        fake_request,
    )

    payload = integration.ControlledEgressRequest(
        destination_url=(
            "https://example.invalid/receive"
        ),
        destination_trust="unapproved_external",
        content="SSN 123-45-6789",
        field_names=["ssn"],
    )

    result = integration.execute_controlled_egress(
        APPLICATION_ID,
        payload,
    )

    assert result["executed"] is False
    assert result["decision"] == "block"
    assert outbound_called is False


def test_allowed_transfer_executes_exactly_one_outbound_request(
    monkeypatch,
):
    calls = []

    def fake_evaluate(
        application_id,
        payload,
    ):
        assert application_id == APPLICATION_ID

        return {
            "event_id": (
                "33333333-4444-5555-6666-777777777777"
            ),
            "application_id": application_id,
            "application_name": "Controlled Egress Test",
            "destination": {
                "scheme": "https",
                "host": "example.invalid",
                "trust": "approved_external",
            },
            "declared_classification": "internal",
            "effective_sensitivity": "internal",
            "decision": "allow",
            "allowed": True,
            "reasons": [
                "policy_requirements_satisfied",
            ],
            "dlp": {
                "engine_version": "dlp-v1",
                "sensitive_data_detected": False,
                "finding_count": 0,
                "highest_sensitivity": None,
                "detected_types": [],
            },
            "evaluated_at": None,
        }

    class FakeResponse:
        status_code = 202

    def fake_request(
        *,
        method,
        url,
        content,
        timeout,
        follow_redirects,
    ):
        calls.append(
            {
                "method": method,
                "url": url,
                "content": content,
                "timeout": timeout,
                "follow_redirects": follow_redirects,
            }
        )

        return FakeResponse()

    monkeypatch.setattr(
        integration,
        "evaluate_and_persist",
        fake_evaluate,
    )

    monkeypatch.setattr(
        integration.httpx,
        "request",
        fake_request,
    )

    payload = integration.ControlledEgressRequest(
        destination_url=(
            "https://example.invalid/receive"
        ),
        destination_trust="approved_external",
        content="non-sensitive payload",
        field_names=["message"],
    )

    result = integration.execute_controlled_egress(
        APPLICATION_ID,
        payload,
    )

    assert result["executed"] is True
    assert result["decision"] == "allow"
    assert result["upstream_status_code"] == 202

    assert len(calls) == 1

    assert calls[0] == {
        "method": "POST",
        "url": "https://example.invalid/receive",
        "content": "non-sensitive payload",
        "timeout": 15.0,
        "follow_redirects": False,
    }
