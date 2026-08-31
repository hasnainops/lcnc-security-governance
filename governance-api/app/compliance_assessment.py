from uuid import UUID, uuid4

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
