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

    dlp_result = response.json()

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
