import os
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from psycopg.types.json import Jsonb

from .database import get_connection


RISK_ENGINE_URL = os.getenv(
    "RISK_ENGINE_URL",
    "http://risk-engine:8001",
)


def assess_and_persist(application_id: UUID):
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

    payload = {
        "registration_status": application["registration_status"],
        "owner_name": application["owner_name"],
        "business_purpose": application["business_purpose"],
        "data_classification": application["data_classification"],
        "internet_exposed": application["internet_exposed"],
        "external_integration": application["external_integration"],
        "integration_approved": application["integration_approved"],
        "credential_type": application["credential_type"],
    }

    try:
        response = httpx.post(
            f"{RISK_ENGINE_URL}/assess",
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Risk engine unavailable: {exc}",
        ) from exc

    assessment = response.json()
    assessment_id = uuid4()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO risk_assessments (
                id,
                application_id,
                score,
                level,
                model_version,
                factors
            )
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (
                assessment_id,
                application_id,
                assessment["score"],
                assessment["level"],
                assessment["model_version"],
                Jsonb(assessment["factors"]),
            ),
        )

        updated_application = connection.execute(
            """
            UPDATE applications
            SET
                risk_status = 'assessed',
                risk_score = %s,
                risk_level = %s,
                risk_model_version = %s,
                risk_assessed_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *;
            """,
            (
                assessment["score"],
                assessment["level"],
                assessment["model_version"],
                application_id,
            ),
        ).fetchone()

    return {
        "assessment_id": assessment_id,
        "application_id": application_id,
        "application_name": updated_application["name"],
        "score": assessment["score"],
        "level": assessment["level"],
        "factors": assessment["factors"],
        "model_version": assessment["model_version"],
        "risk_status": updated_application["risk_status"],
        "assessed_at": updated_application["risk_assessed_at"],
    }
