import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "opa_probe_tests", ROOT / "governance-api/app/opa_functional.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def run_probe(handler):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            return await probe.probe_opa(client)
    return asyncio.run(run())


def success_handler(request):
    payload = json.loads(request.content)["input"]
    policy = request.url.path.split("/")[-2]
    case = next(
        case for case in probe.CASES
        if case[0] == policy and case[1] == payload
    )
    _, _, allowed, reasons = case
    decision = {
        "allow": allowed,
        "action": "allow" if allowed else "deny",
        "reasons": reasons,
    }
    if policy == "access":
        decision.update(
            role=payload["role"],
            requested_action=payload["action"],
            jit_grant_used="jit" in payload,
        )
    return httpx.Response(200, json={"result": decision})


def test_all_six_decisions_required():
    requests = []

    def handler(request):
        requests.append(request)
        return success_handler(request)

    result = run_probe(handler)
    assert result["status"] == "passed"
    assert result["reason"] is None
    assert result["cases_passed"] == result["cases_total"] == 6
    assert result["application_count"] is None
    assert len(requests) == 6
    assert all(r.method == "POST" and r.url.host == "opa" for r in requests)


@pytest.mark.parametrize("field,value", [
    ("allow", False),
    ("allow", 1),
    ("action", "deny"),
    ("reasons", ["unexpected"]),
])
def test_incorrect_decision_is_rejected(field, value):
    def handler(request):
        body = success_handler(request).json()
        body["result"][field] = value
        return httpx.Response(200, json=body)

    result = run_probe(handler)
    assert result["status"] == "failed"
    assert result["reason"] == "decision_mismatch"
    assert result["cases_passed"] == 0


def test_later_failure_never_claims_full_success():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 6:
            return httpx.Response(200, json={"result": {}})
        return success_handler(request)

    result = run_probe(handler)
    assert result["status"] == "failed"
    assert result["cases_passed"] == 5
    assert result["reason"] == "decision_mismatch"


@pytest.mark.parametrize("body", [{}, {"result": None}, {"result": []}])
def test_missing_or_invalid_result_is_rejected(body):
    result = run_probe(lambda request: httpx.Response(200, json=body))
    assert result["status"] == "failed"
    assert result["reason"] == "decision_mismatch"


def test_non_json_is_rejected():
    result = run_probe(
        lambda request: httpx.Response(200, text="private-response-body")
    )
    assert result["reason"] == "invalid_decision"
    assert "private-response-body" not in json.dumps(result)


@pytest.mark.parametrize("code", [302, 403, 500])
def test_http_failure_and_redirect_are_rejected(code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            code, headers={"Location": "http://unexpected.example/"}
        )

    result = run_probe(handler)
    assert result["status"] == "failed"
    assert result["reason"] == "http_error"
    assert len(calls) == 1


def test_oversized_response_is_rejected(monkeypatch):
    monkeypatch.setattr(probe, "MAX_RESPONSE_BYTES", 10)
    result = run_probe(
        lambda request: httpx.Response(200, content=b" " * 11)
    )
    assert result["reason"] == "response_too_large"
    assert result["status"] == "failed"


def test_connection_error_is_sanitized():
    def handler(request):
        raise httpx.ConnectError("private-details", request=request)

    result = run_probe(handler)
    assert result["reason"] == "connection_error"
    assert "private-details" not in json.dumps(result)


def test_total_timeout(monkeypatch):
    monkeypatch.setattr(probe, "PROBE_TIMEOUT_SECONDS", 0.01)

    async def handler(request):
        await asyncio.sleep(1)
        return success_handler(request)

    result = run_probe(handler)
    assert result["status"] == "failed"
    assert result["reason"] == "timeout"


@pytest.mark.parametrize("field,value", [
    ("role", "security_admin"),
    ("requested_action", "read"),
    ("jit_grant_used", True),
])
def test_access_context_mismatch_is_rejected(field, value):
    def handler(request):
        body = success_handler(request).json()
        if request.url.path.endswith("/access/decision"):
            body["result"][field] = value
        return httpx.Response(200, json=body)

    result = run_probe(handler)
    assert result["status"] == "failed"
    assert result["reason"] == "decision_mismatch"
    assert result["cases_passed"] == 2
