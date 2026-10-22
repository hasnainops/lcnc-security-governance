import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

source = Path(__file__).resolve().parents[1] / "governance-api/app/functional_status.py"
spec = importlib.util.spec_from_file_location("functional_probe_tests", source)
probe = importlib.util.module_from_spec(spec)
# Provide package context for the module's relative imports.
import sys
import types

package_name = "functional_probe_test_app"
package = types.ModuleType(package_name)
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "governance-api/app")
]
sys.modules[package_name] = package
spec = importlib.util.spec_from_file_location(
    package_name + ".functional_status",
    Path(__file__).resolve().parents[1]
    / "governance-api/app/functional_status.py",
)
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)

ITEM = {
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "private-application-name",
    "platform": "appsmith",
    "owner_email": "private@example.test",
}


def run_probe(handler):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
        ) as client:
            return await probe.probe_inventory(
                client, "governance-api-a",
                probe.TARGETS["governance-api-a"],
            )
    return asyncio.run(run())


def test_success_returns_count_without_inventory_contents():
    result = run_probe(lambda request: httpx.Response(200, json=[ITEM]))
    assert result["status"] == "passed"
    assert result["application_count"] == 1
    assert result["reason"] is None
    assert result["observed_at"]
    assert result["duration_ms"] >= 0
    encoded = json.dumps(result)
    assert ITEM["name"] not in encoded
    assert ITEM["owner_email"] not in encoded
    assert ITEM["id"] not in encoded


def test_empty_inventory_is_valid():
    result = run_probe(lambda request: httpx.Response(200, json=[]))
    assert result["status"] == "passed"
    assert result["application_count"] == 0


@pytest.mark.parametrize("code", [403, 500, 502])
def test_http_failure_is_not_a_pass(code):
    result = run_probe(
        lambda request: httpx.Response(code, text="private-error-details")
    )
    assert result["status"] == "failed"
    assert result["reason"] == "http_error"
    assert result["http_status"] == code
    assert result["application_count"] is None
    assert "private-error-details" not in json.dumps(result)


@pytest.mark.parametrize("payload", [
    {},
    [None],
    [{**ITEM, "id": "invalid"}],
    [{**ITEM, "name": ""}],
    [{**ITEM, "platform": None}],
    [ITEM, ITEM],
])
def test_invalid_inventory_is_rejected(payload):
    result = run_probe(lambda request: httpx.Response(200, json=payload))
    assert result["status"] == "failed"
    assert result["reason"] == "invalid_inventory"
    assert result["application_count"] is None


def test_non_json_response_is_rejected():
    result = run_probe(
        lambda request: httpx.Response(200, text="<html>login</html>")
    )
    assert result["reason"] == "invalid_inventory"


def test_oversized_response_is_rejected(monkeypatch):
    monkeypatch.setattr(probe, "MAX_RESPONSE_BYTES", 10)
    result = run_probe(
        lambda request: httpx.Response(200, content=b" " * 11)
    )
    assert result["status"] == "failed"
    assert result["reason"] == "response_too_large"


def test_connection_failure_is_sanitized():
    def handler(request):
        raise httpx.ConnectError("private-network-details", request=request)
    result = run_probe(handler)
    assert result["reason"] == "connection_error"
    assert "private-network-details" not in json.dumps(result)


def test_total_request_timeout(monkeypatch):
    monkeypatch.setattr(probe, "PROBE_TIMEOUT_SECONDS", 0.01)

    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=[])

    result = run_probe(handler)
    assert result["status"] == "failed"
    assert result["reason"] == "timeout"


def test_redirect_is_not_followed():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(
            302, headers={"Location": "http://unexpected.example/"}
        )

    result = run_probe(handler)
    assert result["reason"] == "http_error"
    assert len(requests) == 1
