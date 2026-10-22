"""Bounded, read-only inventory probes against fixed internal targets."""

import asyncio
import json
import time
from datetime import datetime, timezone
from uuid import UUID

import httpx

from .opa_functional import probe_opa

TARGETS = {
    "governance-api-a": "http://governance-api-a:8000/applications",
    "governance-api-b": "http://governance-api-b:8000/applications",
    "governance-api": "http://governance-api:8000/applications",
    "governance-portal": "http://governance-portal:8080/api/applications",
}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
PROBE_TIMEOUT_SECONDS = 3
STALE_AFTER_SECONDS = 30


def inventory_count(payload):
    """Validate inventory structure; never return application records."""
    if not isinstance(payload, list):
        raise ValueError("Expected inventory list")

    identifiers = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Invalid inventory entry")
        identifier = item.get("id")
        if not isinstance(identifier, str):
            raise ValueError("Missing application ID")
        identifier = str(UUID(identifier))
        if identifier in identifiers:
            raise ValueError("Duplicate application ID")
        identifiers.add(identifier)
        for field in ("name", "platform"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError("Invalid application field")

    # An empty inventory is a valid successful database read.
    return len(payload)


async def probe_inventory(client, service, url):
    observed_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    result = {
        "service": service,
        "check": "inventory_read",
        "status": "failed",
        "observed_at": observed_at,
        "duration_ms": None,
        "http_status": None,
        "application_count": None,
        "reason": None,
    }

    try:
        # Bounds the complete request, including a slowly streamed body.
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            async with client.stream("GET", url) as response:
                result["http_status"] = response.status_code
                if response.status_code != 200:
                    result["reason"] = "http_error"
                else:
                    payload = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(payload) + len(chunk) > MAX_RESPONSE_BYTES:
                            result["reason"] = "response_too_large"
                            break
                        payload.extend(chunk)
                    else:
                        result["application_count"] = inventory_count(
                            json.loads(payload)
                        )
                        result["status"] = "passed"

    except (TimeoutError, httpx.TimeoutException):
        result["reason"] = "timeout"
    except httpx.RequestError:
        result["reason"] = "connection_error"
    except (ValueError, TypeError, RecursionError):
        result["reason"] = "invalid_inventory"
    except Exception:
        # Never expose response bodies, credentials, or exception details.
        result["reason"] = "probe_error"

    result["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
    return result


async def collect_functional_status():
    async with httpx.AsyncClient(
        timeout=PROBE_TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
        headers={"Accept": "application/json", "Cache-Control": "no-cache"},
    ) as client:
        checks = await asyncio.gather(
            *(probe_inventory(client, service, url)
              for service, url in TARGETS.items()),
            probe_opa(client),
        )

    return {
        "schema_version": 1,
        "source": "internal_http_probes",
        "served_at": datetime.now(timezone.utc).isoformat(),
        "stale_after_seconds": STALE_AFTER_SECONDS,
        "checks": checks,
    }
