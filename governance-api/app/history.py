from uuid import UUID

from fastapi import HTTPException, status

from .database import get_connection


def get_application_history(application_id: UUID):
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

        risk_history = connection.execute(
            """
            SELECT
                id,
                score,
                level,
                model_version,
                factors,
                assessed_at
            FROM risk_assessments
            WHERE application_id = %s
            ORDER BY assessed_at DESC;
            """,
            (application_id,),
        ).fetchall()

        policy_history = connection.execute(
            """
            SELECT
                id,
                action,
                allowed,
                reasons,
                policy_version,
                evaluated_at
            FROM policy_decisions
            WHERE application_id = %s
            ORDER BY evaluated_at DESC;
            """,
            (application_id,),
        ).fetchall()

        governance_history = connection.execute(
            """
            SELECT
                id,
                outcome,
                status,
                required_role,
                reasons,
                created_at
            FROM governance_decisions
            WHERE application_id = %s
            ORDER BY created_at DESC;
            """,
            (application_id,),
        ).fetchall()

    return {
        "application": application,
        "risk_assessments": risk_history,
        "policy_decisions": policy_history,
        "governance_decisions": governance_history,
    }
