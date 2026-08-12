import os
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from psycopg.types.json import Jsonb

from .database import get_connection


ML_ANALYTICS_URL = os.getenv(
    "ML_ANALYTICS_URL",
    "http://ml-analytics:8002",
)


OBSERVED_FEATURES = [
    "external_integration_count",
    "unapproved_integration_count",
    "connector_count",
    "external_domain_count",
    "changes_last_24h",
]


def analyze_and_persist(application_id: UUID):
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    missing_features = [
        feature
        for feature in OBSERVED_FEATURES
        if application[feature] is None
    ]

    if missing_features:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "ML analysis requires complete observed "
                    "application metadata."
                ),
                "missing_features": missing_features,
            },
        )

    credential_type = (
        application["credential_type"] or ""
    ).strip().lower()

    payload = {
        "owner_known": int(
            bool(
                application["owner_name"]
                or application["owner_email"]
            )
        ),
        "business_purpose_known": int(
            bool(application["business_purpose"])
        ),
        "internet_exposed": int(
            bool(application["internet_exposed"])
        ),
        "external_integration_count": (
            application["external_integration_count"]
        ),
        "unapproved_integration_count": (
            application["unapproved_integration_count"]
        ),
        "uses_api_key": int(
            credential_type
            in {
                "api_key",
                "api-key",
                "apikey",
            }
        ),
        "connector_count": (
            application["connector_count"]
        ),
        "external_domain_count": (
            application["external_domain_count"]
        ),
        "changes_last_24h": (
            application["changes_last_24h"]
        ),
    }

    try:
        response = httpx.post(
            f"{ML_ANALYTICS_URL}/analyze",
            json=payload,
            timeout=10.0,
        )

        response.raise_for_status()

    except (
        httpx.ConnectError,
        httpx.TimeoutException,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "ML Analytics unavailable. "
                "No ML assessment was persisted."
            ),
        ) from exc

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "ML Analytics returned an "
                "upstream HTTP error."
            ),
        ) from exc

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="ML Analytics request failed.",
        ) from exc

    analysis = response.json()
    assessment_id = uuid4()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ml_assessments (
                id,
                application_id,
                analysis_type,
                anomalous,
                decision_score,
                model_version,
                features,
                context_signals
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s
            );
            """,
            (
                assessment_id,
                application_id,
                analysis["analysis_type"],
                analysis["anomalous"],
                analysis["raw_decision_score"],
                analysis["model_version"],
                Jsonb(payload),
                Jsonb(
                    analysis["context_signals"]
                ),
            ),
        )

        updated_application = connection.execute(
            """
            UPDATE applications
            SET
                ml_anomaly_status = 'assessed',
                ml_anomalous = %s,
                ml_decision_score = %s,
                ml_model_version = %s,
                ml_assessed_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *;
            """,
            (
                analysis["anomalous"],
                analysis["raw_decision_score"],
                analysis["model_version"],
                application_id,
            ),
        ).fetchone()

    return {
        "assessment_id": assessment_id,
        "application_id": application_id,
        "application_name": (
            updated_application["name"]
        ),
        "analysis_type": (
            analysis["analysis_type"]
        ),
        "anomalous": analysis["anomalous"],
        "decision_score": (
            analysis["raw_decision_score"]
        ),
        "model_version": (
            analysis["model_version"]
        ),
        "features": payload,
        "context_signals": (
            analysis["context_signals"]
        ),
        "ml_anomaly_status": (
            updated_application[
                "ml_anomaly_status"
            ]
        ),
        "assessed_at": (
            updated_application["ml_assessed_at"]
        ),
    }
