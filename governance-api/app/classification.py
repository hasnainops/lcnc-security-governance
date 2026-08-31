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


def classify_and_persist(application_id: UUID):
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

    required_fields = {
        "business_purpose": application["business_purpose"],
        "data_fields": application["data_fields"],
        "connector_metadata": application["connector_metadata"],
    }

    missing_fields = [
        field
        for field, value in required_fields.items()
        if value is None or not str(value).strip()
    ]

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "ML classification requires complete "
                    "application content metadata."
                ),
                "missing_fields": missing_fields,
            },
        )

    payload = {
        "application_name": application["name"],
        "business_purpose": application["business_purpose"],
        "data_fields": application["data_fields"],
        "connector_metadata": application["connector_metadata"],
    }

    try:
        response = httpx.post(
            f"{ML_ANALYTICS_URL}/classify",
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
                "No classification assessment was persisted."
            ),
        ) from exc

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "ML Analytics returned an upstream HTTP error."
            ),
        ) from exc

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="ML classification request failed.",
        ) from exc

    result = response.json()
    assessment_id = uuid4()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO classification_assessments (
                id,
                application_id,
                suggested_classification,
                confidence,
                review_required,
                review_threshold,
                model_version,
                class_probabilities,
                inputs,
                authority
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            );
            """,
            (
                assessment_id,
                application_id,
                result["suggested_classification"],
                result["confidence"],
                result["review_required"],
                result["review_threshold"],
                result["model_version"],
                Jsonb(result["class_probabilities"]),
                Jsonb(payload),
                result["authority"],
            ),
        )

        updated_application = connection.execute(
            """
            UPDATE applications
            SET
                ml_classification_status = 'assessed',
                ml_suggested_classification = %s,
                ml_classification_confidence = %s,
                ml_classification_review_required = %s,
                ml_classification_model_version = %s,
                ml_classified_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *;
            """,
            (
                result["suggested_classification"],
                result["confidence"],
                result["review_required"],
                result["model_version"],
                application_id,
            ),
        ).fetchone()

    return {
        "assessment_id": assessment_id,
        "application_id": application_id,
        "application_name": updated_application["name"],
        "suggested_classification": (
            result["suggested_classification"]
        ),
        "confidence": result["confidence"],
        "review_required": result["review_required"],
        "review_threshold": result["review_threshold"],
        "model_version": result["model_version"],
        "class_probabilities": result["class_probabilities"],
        "authority": result["authority"],
        "authoritative_classification": (
            updated_application["data_classification"]
        ),
        "ml_classification_status": (
            updated_application["ml_classification_status"]
        ),
        "classified_at": updated_application["ml_classified_at"],
    }
