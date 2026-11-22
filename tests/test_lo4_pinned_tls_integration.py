"""LO4.3: Real TLS verification for the pinned egress transport.

All network connections in these tests terminate on loopback.
No public outbound connection or database is required.
"""

import http.server
import socket
import ssl
import subprocess
import sys
import threading

from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "governance-api"))

from app import integration


HOSTNAME = "lo4-egress.example"
PINNED_IP = "93.184.216.34"


@pytest.fixture
def local_https(monkeypatch, tmp_path):

    cert = tmp_path / "certificate.pem"
    key = tmp_path / "private-key.pem"
    config = tmp_path / "openssl.cnf"

    config.write_text(
        "[req]\n"
        "distinguished_name = dn\n"
        "prompt = no\n"
        "x509_extensions = v3_req\n"
        "[dn]\n"
        f"CN = {HOSTNAME}\n"
        "[v3_req]\n"
        f"subjectAltName = DNS:{HOSTNAME}\n"
        "basicConstraints = critical,CA:TRUE\n"
        "keyUsage = digitalSignature,keyEncipherment,keyCertSign\n"
    )

    subprocess.run(
        [
            "openssl", "req",
            "-x509",
            "-newkey", "rsa:2048",
            "-nodes",
            "-days", "1",
            "-keyout", str(key),
            "-out", str(cert),
            "-config", str(config),
            "-extensions", "v3_req",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    received = []
    sni_names = []
    dialed = []

    class Handler(http.server.BaseHTTPRequestHandler):

        def do_POST(self):

            length = int(
                self.headers.get("Content-Length", "0")
            )

            body = self.rfile.read(length)

            received.append({
                "path": self.path,
                "host": self.headers.get("Host"),
                "body": body,
            })

            self.send_response(302)
            self.send_header(
                "Location",
                "https://redirect.invalid/should-not-run",
            )
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args):
            pass

    class Server(http.server.ThreadingHTTPServer):

        daemon_threads = True

        def handle_error(self, *_args):
            # Expected when a client rejects a TLS certificate.
            pass

    server = Server(("127.0.0.1", 0), Handler)

    server_context = ssl.SSLContext(
        ssl.PROTOCOL_TLS_SERVER
    )

    server_context.load_cert_chain(
        certfile=str(cert),
        keyfile=str(key),
    )

    server_context.set_servername_callback(
        lambda _sock, name, _context:
            sni_names.append(name)
    )

    server.socket = server_context.wrap_socket(
        server.socket,
        server_side=True,
    )

    worker = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )

    worker.start()

    def classify(url, *, include_addresses=False):

        assert include_addresses is True

        return (
            urlparse(url),
            "approved_external",
            (ip_address(PINNED_IP),),
        )

    def local_dial(
        self,
        address,
        timeout,
        source_address=None,
    ):

        assert source_address is None
        assert address == (self.host, self.port)
        assert str(self._pinned_ip) == PINNED_IP
        assert self.port == 443

        dialed.append(str(self._pinned_ip))

        # Test-only transport redirection.
        # The production dialer is not modified.
        return socket.create_connection(
            ("127.0.0.1", server.server_port),
            timeout=timeout,
        )

    monkeypatch.setattr(
        integration,
        "_classify_destination",
        classify,
    )

    monkeypatch.setattr(
        integration._PinnedSocketDialer,
        "_dial_pinned",
        local_dial,
    )

    try:
        yield {
            "certificate": cert,
            "received": received,
            "sni": sni_names,
            "dialed": dialed,
        }

    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def send(url):

    return integration._send_pinned_request(
        method="POST",
        url=url,
        content="LO4 synthetic HTTPS payload",
        timeout=5.0,
        follow_redirects=False,
    )


def test_trusted_https_preserves_hostname_and_does_not_redirect(
    local_https,
):
    original = ssl.create_default_context

    certificate = local_https["certificate"]

    def trusted_context():
        return original(
            cafile=str(certificate)
        )

    with patch.object(
        integration.ssl,
        "create_default_context",
        side_effect=trusted_context,
    ):

        response = send(
            f"https://{HOSTNAME}/receive?test=lo4"
        )

    assert response.status_code == 302

    assert local_https["received"] == [{
        "path": "/receive?test=lo4",
        "host": HOSTNAME,
        "body": b"LO4 synthetic HTTPS payload",
    }]

    assert local_https["sni"] == [HOSTNAME]
    assert local_https["dialed"] == [PINNED_IP]


def test_wrong_certificate_hostname_is_rejected(
    local_https,
):
    original = ssl.create_default_context

    certificate = local_https["certificate"]

    def trusted_context():
        return original(
            cafile=str(certificate)
        )

    with patch.object(
        integration.ssl,
        "create_default_context",
        side_effect=trusted_context,
    ):

        with pytest.raises(
            ssl.SSLCertVerificationError
        ):

            send(
                "https://wrong-host.example/receive"
            )

    assert local_https["received"] == []


def test_untrusted_certificate_is_rejected(
    local_https,
):
    with pytest.raises(
        ssl.SSLCertVerificationError
    ):

        send(
            f"https://{HOSTNAME}/receive"
        )

    assert local_https["received"] == []
