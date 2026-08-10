import os
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from psycopg.types.json import Jsonb

from .database import get_connection


OPA_URL = os.getenv(
    "OPA_URL",
    "http://opa:8181",
)

POLICY_VERSION = "application-v1"


def evaluate_and_persist(application_id: UUID):
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

    policy_input = {
        "name": application["name"],
        "registration_status": application["registration_status"],
        "data_classification": application["data_classification"],
        "internet_exposed": application["internet_exposed"],
        "external_integration": application["external_integration"],
        "integration_approved": application["integration_approved"],
        "credential_type": application["credential_type"],
        "risk_score": application["risk_score"],
        "risk_level": application["risk_level"],
    }

    try:
        response = httpx.post(
            f"{OPA_URL}/v1/data/lcnc/governance/decision",
            json={"input": policy_input},
            timeout=10.0,
        )
        response.raise_for_status()

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OPA unavailable: {exc}",
        ) from exc

    result = response.json().get("result")

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OPA returned no governance decision",
        )

    action = result.get("action")
    allowed = result.get("allow")
    reasons = result.get("reasons", [])

    if action not in {"allow", "deny"} or not isinstance(allowed, bool):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OPA returned an invalid governance decision",
        )

    decision_id = uuid4()

    with get_connection() as connection:
        decision = connection.execute(
            """
            INSERT INTO policy_decisions (
                id,
                application_id,
                action,
                allowed,
                reasons,
                policy_version
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *;
            """,
            (
                decision_id,
                application_id,
                action,
                allowed,
                Jsonb(reasons),
                POLICY_VERSION,
            ),
        ).fetchone()

    return {
        "decision_id": decision["id"],
        "application_id": application_id,
        "application_name": application["name"],
        "action": decision["action"],
        "allowed": decision["allowed"],
        "reasons": decision["reasons"],
        "policy_version": decision["policy_version"],
        "evaluated_at": decision["evaluated_at"],
    }
