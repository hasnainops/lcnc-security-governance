from uuid import UUID, uuid4

from fastapi import HTTPException

from psycopg.types.json import Jsonb

from .database import get_connection
from .dynamic_compliance import (
    evaluate_dynamic_compliance,
)


def assess_and_persist(
    application_id: UUID,
):
    result = evaluate_dynamic_compliance(
        application_id
    )

    assessment_id = uuid4()

    with get_connection() as connection:
        persisted = connection.execute(
            """
            INSERT INTO dynamic_compliance_assessments (
                id,
                application_id,
                assessment_version,
                overall_status,
                summary,
                controls
            )
            VALUES (
                %s, %s, %s, %s, %s, %s
            )
            RETURNING assessed_at;
            """,
            (
                assessment_id,
                application_id,
                result["assessment_version"],
                result["overall_status"],
                Jsonb(result["summary"]),
                Jsonb(result["controls"]),
            ),
        ).fetchone()

    return {
        "assessment_id": assessment_id,
        **result,
        "assessed_at": (
            persisted["assessed_at"]
        ),
    }


def assess_if_needed(application_id: UUID):
    """Persist a compliance assessment only when results change.

    Existing manual assessment behavior remains unchanged.
    """

    with get_connection() as connection:
        application = connection.execute(
            """
            SELECT id
            FROM applications
            WHERE id = %s
            FOR UPDATE;
            """,
            (application_id,),
        ).fetchone()

        if application is None:
            raise HTTPException(
                status_code=404,
                detail="Application not found",
            )

        # Reuse the transaction holding the application row lock.
        # Nested review validation must not acquire that lock through
        # another database connection.
        result = evaluate_dynamic_compliance(
            application_id,
            connection=connection,
        )

        latest = connection.execute(
            """
            SELECT
                id,
                assessment_version,
                overall_status,
                summary,
                controls,
                assessed_at
            FROM dynamic_compliance_assessments
            WHERE application_id = %s
            ORDER BY assessed_at DESC, id DESC
            LIMIT 1;
            """,
            (application_id,),
        ).fetchone()

        # Compare meaningful assessment output.
        # Polling timestamps do not cause new assessments.
        if latest is not None:
            unchanged = (
                latest["assessment_version"]
                == result["assessment_version"]
                and latest["overall_status"]
                == result["overall_status"]
                and latest["summary"]
                == result["summary"]
                and latest["controls"]
                == result["controls"]
            )

            if unchanged:
                return {
                    "action": "unchanged",
                    "assessment_id": latest["id"],
                    **result,
                    "assessed_at": latest["assessed_at"],
                }

        assessment_id = uuid4()

        persisted = connection.execute(
            """
            INSERT INTO dynamic_compliance_assessments (
                id,
                application_id,
                assessment_version,
                overall_status,
                summary,
                controls
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING assessed_at;
            """,
            (
                assessment_id,
                application_id,
                result["assessment_version"],
                result["overall_status"],
                Jsonb(result["summary"]),
                Jsonb(result["controls"]),
            ),
        ).fetchone()

    return {
        "action": "created",
        "assessment_id": assessment_id,
        **result,
        "assessed_at": persisted["assessed_at"],
    }
