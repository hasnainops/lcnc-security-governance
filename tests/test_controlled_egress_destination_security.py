import socket
import sys

from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_API = ROOT / "governance-api"

sys.path.insert(
    0,
    str(GOVERNANCE_API),
)

from app import integration


def _addr(ip):
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            6,
            "",
            (ip, 443),
        )
    ]


def test_private_destination_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        integration.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _addr("10.0.0.10"),
    )

    with pytest.raises(HTTPException) as exc:
        integration._classify_destination(
            "https://internal.example/receive"
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["decision"] == "block"
    assert (
        exc.value.detail["reason"]
        == "unsafe_destination"
    )


def test_loopback_destination_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        integration.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _addr("127.0.0.1"),
    )

    with pytest.raises(HTTPException) as exc:
        integration._classify_destination(
            "https://localhost/receive"
        )

    assert exc.value.status_code == 403
    assert (
        exc.value.detail["reason"]
        == "unsafe_destination"
    )


def test_server_allowlist_marks_public_host_approved(
    monkeypatch,
):
    monkeypatch.setenv(
        "CONTROLLED_EGRESS_APPROVED_HOSTS",
        "approved.example",
    )

    monkeypatch.setattr(
        integration.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _addr("93.184.216.34"),
    )

    parsed, trust = integration._classify_destination(
        "https://approved.example/receive"
    )

    assert parsed.hostname == "approved.example"
    assert trust == "approved_external"


def test_public_host_not_on_allowlist_is_unapproved(
    monkeypatch,
):
    monkeypatch.setenv(
        "CONTROLLED_EGRESS_APPROVED_HOSTS",
        "approved.example",
    )

    monkeypatch.setattr(
        integration.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _addr("93.184.216.34"),
    )

    _, trust = integration._classify_destination(
        "https://other.example/receive"
    )

    assert trust == "unapproved_external"


def test_caller_cannot_supply_destination_trust():
    with pytest.raises(ValidationError) as exc:
        integration.ControlledEgressRequest(
            destination_url="https://example.com",
            destination_trust="approved_external",
            content="test",
        )

    errors = exc.value.errors()

    assert len(errors) == 1
    assert errors[0]["type"] == "extra_forbidden"
    assert errors[0]["loc"] == ("destination_trust",)
