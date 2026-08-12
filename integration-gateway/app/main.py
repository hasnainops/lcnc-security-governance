import os

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .policy import evaluate_transfer


DLP_ENGINE_URL = os.getenv(
    "DLP_ENGINE_URL",
    "http://dlp-engine:8004",
)


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


@app.post("/evaluate-transfer")
def evaluate(payload: TransferRequest):
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
