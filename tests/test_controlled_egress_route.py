import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_API = ROOT / "governance-api"

sys.path.insert(
    0,
    str(GOVERNANCE_API),
)

from app import main as governance_main


APPLICATION_ID = (
    "11111111-2222-3333-4444-555555555555"
)


def test_controlled_egress_route_returns_block_without_execution(
    monkeypatch,
):
    def fake_execute(
        application_id,
        payload,
    ):
        return {
            "application_id": str(application_id),
            "decision": "block",
            "allowed": False,
            "executed": False,
            "upstream_status_code": None,
            "reasons": [
                "destination_not_approved",
            ],
        }

    monkeypatch.setattr(
        governance_main,
        "execute_controlled_egress",
        fake_execute,
    )

    client = TestClient(
        governance_main.app
    )

    destination = (
        "https"
        + ":"
        + "/"
        + "/"
        + "example.invalid/receive"
    )

    response = client.post(
        (
            f"/applications/{APPLICATION_ID}"
            "/controlled-egress"
        ),
        json={
            "destination_url": destination,
            "content": "restricted test payload",
            "field_names": ["ssn"],
            "method": "POST",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["decision"] == "block"
    assert body["allowed"] is False
    assert body["executed"] is False
    assert body["upstream_status_code"] is None
