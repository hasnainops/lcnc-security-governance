from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException

from app import integration


APP_ID = UUID("11111111-2222-3333-4444-555555555555")
EVENT_ID = UUID("22222222-3333-4444-5555-666666666666")


def test_enforcement_receipt_persisted(monkeypatch):
    calls = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            calls.append((query, params))
            return self

        def fetchone(self):
            return {"id": EVENT_ID}

    monkeypatch.setattr(
        integration,
        "get_connection",
        FakeConnection,
    )

    integration.record_controlled_egress_enforcement(
        EVENT_ID,
        "blocked_before_send",
    )

    assert len(calls) == 1
    query, params = calls[0]
    assert "UPDATE integration_transfer_events" in query
    assert "enforcement_outcome IS NULL" in query
    assert params == (
        "blocked_before_send",
        None,
        EVENT_ID,
    )


def test_receipt_missing_or_already_recorded_fails(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _query, _params):
            return self

        def fetchone(self):
            return None

    monkeypatch.setattr(
        integration,
        "get_connection",
        FakeConnection,
    )

    with pytest.raises(HTTPException) as exc:
        integration.record_controlled_egress_enforcement(
            EVENT_ID,
            "blocked_before_send",
        )

    assert exc.value.status_code == 500


@pytest.mark.parametrize(
    "error_type",
    [httpx.ConnectError, httpx.TimeoutException],
)
def test_outbound_failure_records_uncertain_delivery(
    monkeypatch, error_type
):
    receipts = []

    monkeypatch.setattr(
        integration,
        "evaluate_and_persist",
        lambda *_args: {
            "event_id": EVENT_ID,
            "allowed": True,
            "decision": "allow",
        },
    )

    def fail_request(**_kwargs):
        request = httpx.Request(
            "POST",
            "https://example.invalid/receive",
        )
        raise error_type(
            "Simulated delivery failure",
            request=request,
        )

    monkeypatch.setattr(
        integration.httpx,
        "request",
        fail_request,
    )

    monkeypatch.setattr(
        integration,
        "record_controlled_egress_enforcement",
        lambda event_id, outcome, upstream_status_code=None:
            receipts.append(
                (event_id, outcome, upstream_status_code)
            ),
    )

    payload = integration.ControlledEgressRequest(
        destination_url="https://example.invalid/receive",
        content="synthetic test payload",
        field_names=["test"],
    )

    with pytest.raises(HTTPException) as exc:
        integration.execute_controlled_egress(
            APP_ID,
            payload,
        )

    assert exc.value.status_code == 502
    assert exc.value.detail["executed"] is False
    assert receipts == [
        (EVENT_ID, "delivery_unconfirmed", None)
    ]
