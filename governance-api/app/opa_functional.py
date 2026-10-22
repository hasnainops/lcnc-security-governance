"""Bounded synthetic policy checks; no application mutations or JIT issuance."""

import asyncio
import json
import time
from datetime import datetime, timezone

import httpx

OPA_BASE = "http://opa:8181/v1/data/lcnc"
PROBE_TIMEOUT_SECONDS = 3
MAX_RESPONSE_BYTES = 64 * 1024

ACCESS = {
    "role": "viewer",
    "action": "export",
    "registration_status": "registered",
    "data_classification": "confidential",
}
JIT = {"active": True, "granted_action": "export"}

CASES = (
    ("governance", {
        "data_classification": "internal",
        "external_integration": False,
    }, True, []),
    ("governance", {
        "data_classification": "confidential",
        "external_integration_count": 3,
        "unapproved_integration_count": 1,
    }, False, [
        "Confidential data cannot use an unapproved external integration."
    ]),
    ("access", ACCESS, False, [
        "Role is not permitted to perform this action."
    ]),
    ("access", {**ACCESS, "jit": JIT}, True, []),
    ("access", {
        **ACCESS, "data_classification": "restricted", "jit": JIT,
    }, False, ["JIT grants cannot export restricted applications."]),
    ("access", {
        **ACCESS, "registration_status": "unregistered", "jit": JIT,
    }, False, ["Privileged actions require a registered application."]),
)


def matches_decision(body, policy, payload, allowed, reasons):
    if not isinstance(body, dict):
        return False
    result = body.get("result")
    if not isinstance(result, dict):
        return False
    if (
        result.get("allow") is not allowed
        or result.get("action") != ("allow" if allowed else "deny")
        or result.get("reasons") != reasons
    ):
        return False
    if policy == "access":
        return (
            result.get("role") == payload["role"]
            and result.get("requested_action") == payload["action"]
            and result.get("jit_grant_used") is ("jit" in payload)
        )
    return True


async def probe_opa(client):
    started = time.monotonic()
    result = {
        "service": "opa",
        "check": "policy_decisions",
        "status": "failed",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": None,
        "http_status": None,
        "application_count": None,
        "cases_passed": 0,
        "cases_total": len(CASES),
        "reason": None,
    }

    try:
        # One deadline for all requests and response bodies.
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            for policy, payload, allowed, reasons in CASES:
                async with client.stream(
                    "POST", f"{OPA_BASE}/{policy}/decision",
                    json={"input": payload},
                ) as response:
                    result["http_status"] = response.status_code
                    if response.status_code != 200:
                        result["reason"] = "http_error"
                        break

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            result["reason"] = "response_too_large"
                            break
                        body.extend(chunk)

                    if result["reason"]:
                        break

                    if not matches_decision(
                        json.loads(body), policy, payload, allowed, reasons
                    ):
                        result["reason"] = "decision_mismatch"
                        break

                    result["cases_passed"] += 1
            else:
                result["status"] = "passed"

    except (TimeoutError, httpx.TimeoutException):
        result["reason"] = "timeout"
    except httpx.RequestError:
        result["reason"] = "connection_error"
    except (ValueError, TypeError, RecursionError):
        result["reason"] = "invalid_decision"
    except Exception:
        result["reason"] = "probe_error"

    result["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
    return result
