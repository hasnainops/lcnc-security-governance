"""Real Caddy boundary tests against isolated HTTP fixtures, never Appsmith.

Set CADDY_BIN to a Caddy 2.11.4 executable to run these tests.
"""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import appsmith_publish as gate
from app.appsmith_publish import publish_target


CADDY = os.environ.get("CADDY_BIN")
pytestmark = pytest.mark.skipif(not CADDY, reason="Set CADDY_BIN for the real proxy test")
URI = "/api/v1/applications/publish/6afabf4265d61d1e1b332ac1"


@pytest.fixture
def proxy(tmp_path):
    state = {"status": 403, "native_status": 200, "upstream": [], "auth": []}
    class Quiet(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def finish_response(self, status, body=b"", headers=None):
            self.send_response(status)
            for name, value in (headers or {}).items():
                if name.lower() != "content-length":
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    class Auth(Quiet):
        def do_GET(self):
            state["auth"].append(dict(self.headers))
            try:
                target = publish_target(self.headers.get("X-LCNC-Original-Method"),
                                        self.headers.get("X-LCNC-Original-Uri"),
                                        self.headers.get("X-LCNC-Appsmith-Branch", ""))
                code = state["status"] if target else 204
            except ValueError:
                code = 403
            self.finish_response(code, state.get("body", b""), state.get("headers"))
    class Native(Quiet):
        def do_POST(self):
            state["upstream"].append((self.command, self.path, dict(self.headers),
                                      self.rfile.read(int(self.headers.get("Content-Length", "0")))))
            self.finish_response(state["native_status"])
        do_GET = do_POST
    servers = [ThreadingHTTPServer(("127.0.0.1", 0), handler) for handler in (Auth, Native)]
    state["auth_server"] = servers[0]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    source = Path(__file__).resolve().parents[1] / "appsmith/publish-guard.Caddyfile"
    config = source.read_text().replace("\n:80 {\n", f"\nhttp://127.0.0.1:{port} {{\n")
    config = config.replace("governance-api:8000", f"127.0.0.1:{servers[0].server_port}")
    config = config.replace("appsmith:80", f"127.0.0.1:{servers[1].server_port}")
    path = tmp_path / "Caddyfile"
    path.write_text(config)
    with (tmp_path / "caddy.log").open("w") as log:
        process = subprocess.Popen([CADDY, "run", "--config", str(path), "--adapter", "caddyfile"],
                                   stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.1):
                        break
                except OSError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        pytest.fail((tmp_path / "caddy.log").read_text())
                    time.sleep(.05)
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
                yield state, client
        finally:
            process.terminate()
            process.wait(timeout=5)
            for server in servers:
                server.shutdown()
                server.server_close()


@pytest.mark.parametrize("status", [403, 500, 503])
def test_denial_or_guard_failure_does_not_contact_appsmith(proxy, status):
    state, client = proxy
    state["status"] = status
    assert client.post(URI).status_code == status
    assert not state["upstream"]


@pytest.mark.parametrize("unavailable", [False, True])
def test_appsmith_error_envelope_survives_proxy_without_publish(proxy, monkeypatch, unavailable):
    state, client = proxy
    app = FastAPI()
    app.include_router(gate.router)
    def check(_):
        if unavailable:
            raise RuntimeError("private upstream detail")
        return {"allowed": False, "reasons": ["review_required"], "decision_id": "receipt-123"}
    monkeypatch.setattr(gate, "check_publish", check)
    with TestClient(app) as api:
        result = api.get("/internal/appsmith/publish-preflight", headers={
            "X-LCNC-Original-Method": "POST", "X-LCNC-Original-Uri": URI,
        })
    state.update(status=result.status_code, body=result.content, headers=dict(result.headers))
    response = client.post(URI)
    assert response.status_code == (503 if unavailable else 403)
    assert response.content == result.content
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["responseMeta"]["success"] is False
    assert response.json()["responseMeta"]["error"]["message"]
    if not unavailable:
        assert response.headers["x-lcnc-publish-decision"] == "receipt-123"
    assert not state["upstream"]


def test_forward_preserves_native_session_body_and_authorization(proxy):
    state, client = proxy
    state["status"], state["native_status"] = 204, 401
    response = client.post(URI, content=b'{"fixture":true}', headers={
        "Cookie": "SESSION=fixture", "Authorization": "Bearer fixture",
        "X-LCNC-Original-Uri": "/", "X-LCNC-Original-Method": "GET",
    })
    # Native authentication remains authoritative even after policy permits forwarding.
    assert response.status_code == 401
    assert len(state["upstream"]) == 1
    method, uri, headers, body = state["upstream"][0]
    assert (method, uri, body) == ("POST", URI, b'{"fixture":true}')
    assert headers["Cookie"] == "SESSION=fixture"
    assert headers["Authorization"] == "Bearer fixture"
    auth = {k.lower(): v for k, v in state["auth"][-1].items()}
    assert "cookie" not in auth and "authorization" not in auth
    assert auth["x-lcnc-original-uri"] == URI
    assert auth["x-lcnc-original-method"] == "POST"


def test_approved_preflight_forwards_once_and_preserves_native_success(proxy):
    state, client = proxy
    state["status"], state["native_status"] = 204, 200
    response = client.post(URI, content=b'{"approved_fixture":true}')
    assert response.status_code == 200
    assert len(state["auth"]) == 1
    assert len(state["upstream"]) == 1
    method, path, _, body = state["upstream"][0]
    assert (method, path, body) == ("POST", URI, b'{"approved_fixture":true}')


@pytest.mark.parametrize("uri", [
    "/api/v1/applications", "/api/v1/applications/clone/6afabf4265d61d1e1b332ac1",
])
def test_auto_publish_routes_do_not_reach_native_upstream(proxy, uri):
    state, client = proxy
    state["status"] = 204
    assert client.post(uri).status_code == 403
    assert not state["upstream"]


def test_spoofed_headers_and_branch_cannot_skip_gate(proxy):
    state, client = proxy
    assert client.post(URI, headers={"X-LCNC-Original-Uri": "/", "X-LCNC-Original-Method": "GET"}).status_code == 403
    state["status"] = 204
    assert client.post(URI, headers={"branchName": "main"}).status_code == 403
    assert not state["upstream"]


def test_encoded_publish_path_cannot_skip_gate(proxy):
    state, client = proxy
    assert client.post(URI.replace("publish", "%70ublish")).status_code == 403
    assert not state["upstream"]


def test_ui_read_can_pass_without_publish_approval(proxy):
    state, client = proxy
    assert client.get("/api/v1/applications").status_code == 200
    assert len(state["upstream"]) == 1


def test_guard_connection_failure_never_contacts_appsmith(proxy):
    state, client = proxy
    state["auth_server"].shutdown()
    state["auth_server"].server_close()
    assert client.post(URI).status_code == 502
    assert not state["upstream"]
