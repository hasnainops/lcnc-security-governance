from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .citizen_guidance import (
    TRAINING_CATALOG,
    build_guidance,
)
from .database import get_connection


class TrainingCompletionRequest(BaseModel):
    subject_id: str = Field(
        min_length=1,
        max_length=255,
    )

    module_id: str = Field(
        min_length=1,
        max_length=100,
    )


def get_training_status(
    application_id: UUID,
    subject_id: str,
):
    guidance = build_guidance(
        application_id
    )

    with get_connection() as connection:
        completed = connection.execute(
            """
            SELECT
                module_id,
                completed_at
            FROM training_completions
            WHERE application_id = %s
              AND subject_id = %s
            ORDER BY completed_at DESC;
            """,
            (
                application_id,
                subject_id,
            ),
        ).fetchall()

    completed_ids = {
        row["module_id"]
        for row in completed
    }

    recommended_ids = {
        item["module_id"]
        for item in guidance[
            "recommended_training"
        ]
    }

    completed_recommended = (
        completed_ids
        & recommended_ids
    )

    if recommended_ids:
        completion_rate = round(
            (
                len(completed_recommended)
                / len(recommended_ids)
            )
            * 100
        )
    else:
        completion_rate = 100

    security_score = guidance[
        "security_score"
    ]

    if (
        security_score >= 90
        and completion_rate == 100
    ):
        achievement = "secure_builder"

    elif completion_rate > 0:
        achievement = "security_progress"

    else:
        achievement = "training_pending"

    return {
        "application_id": application_id,
        "application_name": (
            guidance["application_name"]
        ),
        "subject_id": subject_id,
        "security_score": security_score,
        "badge": guidance["badge"],
        "recommended_training_count": (
            len(recommended_ids)
        ),
        "completed_recommended_count": (
            len(completed_recommended)
        ),
        "completion_rate": completion_rate,
        "achievement": achievement,
        "completed_modules": completed,
    }


def complete_training(
    application_id: UUID,
    payload: TrainingCompletionRequest,
):
    valid_module_ids = {
        item["module_id"]
        for item in TRAINING_CATALOG.values()
    }

    if payload.module_id not in valid_module_ids:
        raise HTTPException(
            status_code=422,
            detail=(
                "Unknown citizen-developer "
                "training module."
            ),
        )

    with get_connection() as connection:
        application = connection.execute(
            """
            SELECT id
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

        completion = connection.execute(
            """
            INSERT INTO training_completions (
                id,
                application_id,
                subject_id,
                module_id
            )
            VALUES (%s, %s, %s, %s)

            ON CONFLICT (
                application_id,
                subject_id,
                module_id
            )
            DO UPDATE SET
                completed_at = NOW()

            RETURNING
                id,
                module_id,
                completed_at;
            """,
            (
                uuid4(),
                application_id,
                payload.subject_id,
                payload.module_id,
            ),
        ).fetchone()

    status = get_training_status(
        application_id,
        payload.subject_id,
    )

    return {
        "completion": completion,
        "training_status": status,
    }
