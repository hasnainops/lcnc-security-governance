import os
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from .database import get_connection


INTEGRATION_GATEWAY_URL = os.getenv(
    "INTEGRATION_GATEWAY_URL",
    "http://integration-gateway:8005",
)


class TransferEvaluationRequest(BaseModel):
    destination_url: str

    destination_trust: Literal[
        "internal",
        "approved_external",
        "unapproved_external",
    ]

    content: str = ""

    field_names: list[str] = Field(
        default_factory=list
    )


def evaluate_and_persist(
    application_id: UUID,
    payload: TransferEvaluationRequest,
):
    with get_connection() as connection:
        application = connection.execute(
            """
            SELECT *
            FROM applications
            WHERE id = %s;
            """,
            (application_id,),
        ).fetchone()

    if application is None:
        raise HTTPException(
            status_code=404,
            detail="Application not found",
        )

    parsed = urlparse(
        payload.destination_url
    )

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "destination_url must be a valid "
                "HTTP or HTTPS URL"
            ),
        )

    gateway_payload = {
        "application_id": str(application_id),
        "application_name": application["name"],
        "destination_url": payload.destination_url,
        "destination_trust": (
            payload.destination_trust
        ),
        "declared_classification": (
            application["data_classification"]
        ),
        "content": payload.content,
        "field_names": payload.field_names,
    }

    try:
        response = httpx.post(
            (
                f"{INTEGRATION_GATEWAY_URL}"
                "/evaluate-transfer"
            ),
            json=gateway_payload,
            timeout=15.0,
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
                "reason": (
                    "integration_gateway_unavailable"
                ),
                "message": (
                    "Transfer blocked because the "
                    "integration control is unavailable."
                ),
            },
        ) from exc

    except httpx.HTTPStatusError as exc:
        detail = (
            exc.response.json()
            if exc.response.content
            else {
                "decision": "block",
                "reason": "gateway_error",
            }
        )

        raise HTTPException(
            status_code=502,
            detail=detail,
        ) from exc

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "decision": "block",
                "reason": "gateway_request_failed",
            },
        ) from exc

    result = response.json()
    event_id = uuid4()

    with get_connection() as connection:
        persisted = connection.execute(
            """
            INSERT INTO integration_transfer_events (
                id,
                application_id,
                destination_scheme,
                destination_host,
                destination_trust,
                declared_classification,
                effective_sensitivity,
                decision,
                allowed,
                reasons,
                dlp_sensitive_data_detected,
                dlp_finding_count,
                dlp_highest_sensitivity,
                dlp_detected_types,
                gateway_version,
                dlp_engine_version
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            RETURNING evaluated_at;
            """,
            (
                event_id,
                application_id,
                parsed.scheme,
                parsed.hostname,
                payload.destination_trust,
                application["data_classification"],
                result["effective_sensitivity"],
                result["decision"],
                result["allowed"],
                Jsonb(result["reasons"]),
                result["dlp"][
                    "sensitive_data_detected"
                ],
                result["dlp"]["finding_count"],
                result["dlp"][
                    "highest_sensitivity"
                ],
                Jsonb(
                    result["dlp"][
                        "detected_types"
                    ]
                ),
                result["gateway_version"],
                result["dlp"]["engine_version"],
            ),
        ).fetchone()

    return {
        "event_id": event_id,
        "application_id": application_id,
        "application_name": application["name"],
        "destination": {
            "scheme": parsed.scheme,
            "host": parsed.hostname,
            "trust": payload.destination_trust,
        },
        "declared_classification": (
            application["data_classification"]
        ),
        "effective_sensitivity": (
            result["effective_sensitivity"]
        ),
        "decision": result["decision"],
        "allowed": result["allowed"],
        "reasons": result["reasons"],
        "dlp": result["dlp"],
        "evaluated_at": persisted["evaluated_at"],
    }
