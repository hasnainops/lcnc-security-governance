import os
import time
from collections import defaultdict, deque
from threading import Lock

import httpx
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    generate_latest,
)

from .policy import evaluate_transfer


DLP_ENGINE_URL = os.getenv(
    "DLP_ENGINE_URL",
    "http://dlp-engine:8004",
)



RATE_LIMIT_PER_MINUTE = int(
    os.getenv(
        "GATEWAY_RATE_LIMIT_PER_MINUTE",
        "60",
    )
)

TRANSFER_REQUESTS = Counter(
    "lcnc_gateway_transfer_requests_total",
    "Total transfer evaluation requests.",
)

TRANSFER_DECISIONS = Counter(
    "lcnc_gateway_transfer_decisions_total",
    "Transfer decisions produced by the gateway.",
    ["decision"],
)

DLP_FAILURES = Counter(
    "lcnc_gateway_dlp_failures_total",
    "DLP inspection failures.",
    ["reason"],
)

RATE_LIMITED = Counter(
    "lcnc_gateway_rate_limited_total",
    "Requests blocked by the gateway rate limit.",
)

_rate_windows = defaultdict(deque)
_rate_lock = Lock()


def rate_limit_exceeded(application_id: str):
    now = time.monotonic()
    cutoff = now - 60.0

    with _rate_lock:
        window = _rate_windows[application_id]

        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= RATE_LIMIT_PER_MINUTE:
            return True

        window.append(now)

    return False


app = FastAPI(
    title="LCNC Integration Gateway",
    version="0.1.0",
)


class TransferRequest(BaseModel):
    application_id: str
    application_name: str

    destination_url: str

    destination_trust: str = Field(
        pattern=(
            "^(internal|approved_external|"
            "unapproved_external)$"
        )
    )

    declared_classification: str = Field(
        pattern=(
            "^(public|internal|confidential|"
            "restricted|unknown)$"
        )
    )

    content: str = ""

    field_names: list[str] = Field(
        default_factory=list
    )


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "integration-gateway",
        "version": "gateway-v1",
    }



@app.get("/metrics")
def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def _validate_dlp_result(document):
    """Reject incomplete or inconsistent DLP inspection evidence."""

    if not isinstance(document, dict):
        raise ValueError("DLP response must be an object")

    engine_version = document.get("engine_version")
    sensitive = document.get("sensitive_data_detected")
    finding_count = document.get("finding_count")
    highest = document.get("highest_sensitivity")
    detected_types = document.get("detected_types")
    findings = document.get("findings")

    if (
        not isinstance(engine_version, str)
        or not engine_version.strip()
    ):
        raise ValueError("Invalid DLP engine version")

    if type(sensitive) is not bool:
        raise ValueError("Invalid DLP detection flag")

    if (
        type(finding_count) is not int
        or finding_count < 0
    ):
        raise ValueError("Invalid DLP finding count")

    if not isinstance(detected_types, list):
        raise ValueError("Invalid DLP detected types")

    if not all(
        isinstance(item, str) and item.strip()
        for item in detected_types
    ):
        raise ValueError("Invalid DLP detected type")

    if len(set(detected_types)) != len(detected_types):
        raise ValueError("Duplicate DLP detected types")

    if not isinstance(findings, list):
        raise ValueError("Missing DLP findings")

    if len(findings) != finding_count:
        raise ValueError("DLP finding count mismatch")

    sensitivity_rank = {
        "confidential": 2,
        "restricted": 3,
    }

    actual_types = set()
    actual_highest = None

    for item in findings:
        if not isinstance(item, dict):
            raise ValueError("Invalid DLP finding")

        for field in ("rule_id", "data_type", "evidence"):
            value = item.get(field)

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError("Invalid DLP finding field")

        if (
            type(item.get("count")) is not int
            or item["count"] < 1
        ):
            raise ValueError("Invalid DLP occurrence count")

        sensitivity = item.get("sensitivity")

        if sensitivity not in sensitivity_rank:
            raise ValueError("Invalid DLP finding sensitivity")

        actual_types.add(item["data_type"])

        if (
            actual_highest is None
            or sensitivity_rank[sensitivity]
            > sensitivity_rank[actual_highest]
        ):
            actual_highest = sensitivity

    if sensitive != bool(findings):
        raise ValueError("Inconsistent DLP detection flag")

    if set(detected_types) != actual_types:
        raise ValueError("Inconsistent DLP detected types")

    if highest != actual_highest:
        raise ValueError("Inconsistent DLP highest sensitivity")

    return document


@app.post("/evaluate-transfer")
def evaluate(payload: TransferRequest):
    TRANSFER_REQUESTS.inc()

    if rate_limit_exceeded(
        payload.application_id
    ):
        RATE_LIMITED.inc()

        raise HTTPException(
            status_code=429,
            detail={
                "decision": "block",
                "reason": "rate_limit_exceeded",
                "message": (
                    "Transfer evaluation rate "
                    "limit exceeded."
                ),
            },
        )
    try:
        response = httpx.post(
            f"{DLP_ENGINE_URL}/inspect",
            json={
                "content": payload.content,
                "field_names": payload.field_names,
            },
            timeout=10.0,
        )

        response.raise_for_status()

    except (
        httpx.ConnectError,
        httpx.TimeoutException,
    ) as exc:
        DLP_FAILURES.labels(
            reason="unavailable"
        ).inc()

        raise HTTPException(
            status_code=503,
            detail={
                "decision": "block",
                "reason": "dlp_unavailable",
                "message": (
                    "Transfer blocked because "
                    "DLP inspection is unavailable."
                ),
            },
        ) from exc

    except httpx.HTTPError as exc:
        DLP_FAILURES.labels(
            reason="inspection_failed"
        ).inc()

        raise HTTPException(
            status_code=502,
            detail={
                "decision": "block",
                "reason": "dlp_inspection_failed",
            },
        ) from exc

    try:
        dlp_result = _validate_dlp_result(
            response.json()
        )
    except (TypeError, ValueError) as exc:
        DLP_FAILURES.labels(
            reason="invalid_response"
        ).inc()

        raise HTTPException(
            status_code=502,
            detail={
                "decision": "block",
                "reason": "dlp_invalid_response",
            },
        ) from exc

    policy = evaluate_transfer(
        destination_url=payload.destination_url,
        destination_trust=payload.destination_trust,
        declared_classification=(
            payload.declared_classification
        ),
        dlp_result=dlp_result,
    )

    TRANSFER_DECISIONS.labels(
        decision=policy["decision"]
    ).inc()

    return {
        "gateway_version": "gateway-v1",
        "application_id": payload.application_id,
        "application_name": (
            payload.application_name
        ),
        "destination_trust": (
            payload.destination_trust
        ),
        "decision": policy["decision"],
        "allowed": policy["allowed"],
        "effective_sensitivity": (
            policy["effective_sensitivity"]
        ),
        "reasons": policy["reasons"],
        "dlp": {
            "engine_version": (
                dlp_result["engine_version"]
            ),
            "sensitive_data_detected": (
                dlp_result[
                    "sensitive_data_detected"
                ]
            ),
            "finding_count": (
                dlp_result["finding_count"]
            ),
            "highest_sensitivity": (
                dlp_result[
                    "highest_sensitivity"
                ]
            ),
            "detected_types": (
                dlp_result["detected_types"]
            ),
        },
    }
