"""Automatic LO1 risk assessment without duplicate polling assessments."""

from uuid import UUID

from fastapi import HTTPException

from .assessment import assess_and_persist
from .database import get_connection


def assess_risk_if_needed(application_id: UUID):
    """Assess unassessed or stale applications using the existing engine."""

    with get_connection() as connection:
        # Serialize automatic assessment attempts across API replicas.
        # The transaction-scoped lock is released on commit or rollback.
        connection.execute(
            "SELECT pg_advisory_xact_lock(41011, hashtext(%s));",
            (str(application_id),),
        )

        application = connection.execute(
            """
            SELECT risk_status
            FROM applications
            WHERE id = %s;
            """,
            (application_id,),
        ).fetchone()

        if application is None:
            raise HTTPException(404, "Application not found")

        current_status = application["risk_status"]

        if current_status not in {"not_assessed", "stale"}:
            return {
                "action": "skipped",
                "risk_status": current_status,
            }

        result = assess_and_persist(application_id)

        return {
            "action": "assessed",
            "assessment_id": result["assessment_id"],
            "risk_status": result["risk_status"],
            "score": result["score"],
            "level": result["level"],
        }
