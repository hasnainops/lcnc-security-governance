import socket
import ssl
import sys

from ipaddress import ip_address
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import UUID

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "governance-api"))

from app import integration


APP_ID = UUID(
    "11111111-2222-3333-4444-555555555555"
)


def dns_answer(address):
    family = (
        socket.AF_INET6
        if ":" in address
        else socket.AF_INET
    )

    return [
        (
            family,
            socket.SOCK_STREAM,
            6,
            "",
            (address, 443),
        )
    ]


def test_dns_rebinding_to_private_address_is_blocked(
    monkeypatch,
):
    receipts = []
    calls = []

    monkeypatch.setattr(
        integration,
        "evaluate_and_persist",
        lambda *_args: {
            "event_id": "lo4-test-event",
            "decision": "allow",
            "allowed": True,
        },
    )

    monkeypatch.setattr(
        integration.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs:
            dns_answer("10.0.0.5"),
    )

    monkeypatch.setattr(
        integration.socket,
        "socket",
        lambda *_args, **_kwargs:
            calls.append("TCP attempted"),
    )

    monkeypatch.setattr(
        integration,
        "record_controlled_egress_enforcement",
        lambda event_id, outcome, status=None:
            receipts.append(
                (event_id, outcome, status)
            ),
    )

    payload = integration.ControlledEgressRequest(
        destination_url=(
            "https://approved.example/receive"
        ),
        content="synthetic",
    )

    with pytest.raises(HTTPException) as exc:
        integration.execute_controlled_egress(
            APP_ID,
            payload,
        )

    assert exc.value.status_code == 403
    assert calls == []

    assert receipts == [
        (
            "lo4-test-event",
            "blocked_before_send",
            None,
        )
    ]


def test_tcp_connect_uses_pinned_ip_without_dns(
    monkeypatch,
):
    connected = []

    class FakeSocket:
        def settimeout(self, value):
            assert value == 15.0

        def connect(self, address):
            connected.append(address)

        def setsockopt(self, *_args):
            pass

        def close(self):
            pass

    monkeypatch.setattr(
        integration.socket,
        "socket",
        lambda *_args: FakeSocket(),
    )

    monkeypatch.setattr(
        integration.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs:
            pytest.fail("Unexpected second DNS lookup"),
    )

    connection = integration._PinnedHTTPConnection(
        "approved.example",
        80,
        pinned_ip=ip_address("93.184.216.34"),
        timeout=15.0,
    )

    connection.connect()
    connection.close()

    assert connected == [
        ("93.184.216.34", 80)
    ]

    assert connection.host == "approved.example"


def test_tls_hostname_and_verification_preserved():
    connection = integration._PinnedHTTPSConnection(
        "approved.example",
        443,
        pinned_ip=ip_address("93.184.216.34"),
        timeout=15.0,
    )

    assert connection.host == "approved.example"
    assert connection._context.check_hostname is True

    assert (
        connection._context.verify_mode
        == ssl.CERT_REQUIRED
    )

    connection.close()


def test_https_sni_uses_original_hostname():
    seen = []

    class FakeSocket:
        def setsockopt(self, *_args):
            pass

        def close(self):
            pass

    class FakeTLSContext:
        def wrap_socket(
            self,
            sock,
            *,
            server_hostname,
        ):
            seen.append(server_hostname)
            return sock

    connection = integration._PinnedHTTPSConnection(
        "approved.example",
        443,
        pinned_ip="93.184.216.34",
        timeout=15.0,
        context=FakeTLSContext(),
    )

    connection._create_connection = (
        lambda *_args: FakeSocket()
    )

    connection.connect()
    connection.close()

    assert seen == ["approved.example"]


def test_environment_proxies_and_redirects_ignored(
    monkeypatch,
):
    monkeypatch.setenv(
        "HTTPS_PROXY",
        "http://127.0.0.1:9999",
    )

    monkeypatch.setenv(
        "HTTP_PROXY",
        "http://127.0.0.1:9999",
    )

    calls = []

    class FakeConnection:
        def __init__(
            self,
            hostname,
            port,
            *,
            pinned_ip,
            timeout,
        ):
            calls.append(
                (
                    "connect",
                    hostname,
                    port,
                    str(pinned_ip),
                    timeout,
                )
            )

        def request(self, method, target, body):
            calls.append(
                (
                    "request",
                    method,
                    target,
                    body,
                )
            )

        def getresponse(self):
            return SimpleNamespace(status=302)

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(
        integration,
        "_PinnedHTTPSConnection",
        FakeConnection,
    )

    monkeypatch.setattr(
        integration,
        "_classify_destination",
        lambda url, *, include_addresses: (
            urlparse(url),
            "approved_external",
            (ip_address("93.184.216.34"),),
        ),
    )

    result = integration._send_pinned_request(
        method="POST",
        url="https://approved.example/receive?q=1",
        content="safe synthetic",
        timeout=15.0,
        follow_redirects=False,
    )

    assert result.status_code == 302

    assert calls == [
        (
            "connect",
            "approved.example",
            443,
            "93.184.216.34",
            15.0,
        ),
        (
            "request",
            "POST",
            "/receive?q=1",
            b"safe synthetic",
        ),
        ("close",),
    ]


def test_mixed_public_private_dns_answer_fails_closed(
    monkeypatch,
):
    monkeypatch.setattr(
        integration.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: (
            dns_answer("93.184.216.34")
            + dns_answer("10.0.0.5")
        ),
    )

    with pytest.raises(HTTPException) as exc:
        integration._classify_destination(
            "https://approved.example/receive",
            include_addresses=True,
        )

    assert exc.value.status_code == 403


def test_pinned_connection_rejects_private_ip():
    with pytest.raises(ValueError):
        integration._PinnedHTTPSConnection(
            "approved.example",
            443,
            pinned_ip="127.0.0.1",
            timeout=15.0,
        )


def test_redirect_following_cannot_be_enabled():
    with pytest.raises(ValueError):
        integration._send_pinned_request(
            method="POST",
            url="https://approved.example",
            content="synthetic",
            timeout=15.0,
            follow_redirects=True,
        )
