from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from .citizen_guidance import (
    TRAINING_CATALOG,
    build_guidance,
)
from .database import get_connection


TRAINING_DUE_DAYS = 7


class TrainingCompletionRequest(BaseModel):
    subject_id: str = Field(
        min_length=1,
        max_length=255,
    )

    module_id: str = Field(
        min_length=1,
        max_length=100,
    )


def insert_training_event(
    connection,
    assignment_id,
    event_type,
    actor=None,
    details=None,
):
    connection.execute(
        """
        INSERT INTO training_events (
            id,
            training_assignment_id,
            event_type,
            actor,
            details
        )
        VALUES (%s, %s, %s, %s, %s);
        """,
        (
            uuid4(),
            assignment_id,
            event_type,
            actor,
            Jsonb(details or {}),
        ),
    )


def refresh_overdue_assignments(
    application_id: UUID | None = None,
):
    now = datetime.now(timezone.utc)

    with get_connection() as connection:
        if application_id is None:
            overdue = connection.execute(
                """
                UPDATE training_assignments
                SET
                    status = 'overdue',
                    updated_at = %s
                WHERE required = TRUE
                  AND status = 'assigned'
                  AND due_at <= %s
                RETURNING *;
                """,
                (
                    now,
                    now,
                ),
            ).fetchall()
        else:
            overdue = connection.execute(
                """
                UPDATE training_assignments
                SET
                    status = 'overdue',
                    updated_at = %s
                WHERE application_id = %s
                  AND required = TRUE
                  AND status = 'assigned'
                  AND due_at <= %s
                RETURNING *;
                """,
                (
                    now,
                    application_id,
                    now,
                ),
            ).fetchall()

        for assignment in overdue:
            insert_training_event(
                connection,
                assignment["id"],
                "training_overdue",
                actor="governance-automation",
                details={
                    "module_id": (
                        assignment["module_id"]
                    ),
                    "subject_id": (
                        assignment["subject_id"]
                    ),
                    "due_at": (
                        assignment[
                            "due_at"
                        ].isoformat()
                    ),
                },
            )

        connection.commit()

    return len(overdue)


def assign_required_training(
    application_id: UUID,
):
    guidance = build_guidance(
        application_id
    )

    recommendations = guidance[
        "recommended_training"
    ]

    now = datetime.now(timezone.utc)

    default_due_at = now + timedelta(
        days=TRAINING_DUE_DAYS
    )

    with get_connection() as connection:
        application = connection.execute(
            """
            SELECT
                id,
                name,
                owner_name,
                owner_email
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

        subject_id = application[
            "owner_email"
        ]

        existing_rows = connection.execute(
            """
            SELECT *
            FROM training_assignments
            WHERE application_id = %s;
            """,
            (application_id,),
        ).fetchall()

        existing = {
            row["module_id"]: row
            for row in existing_rows
        }

        recommended_ids = {
            item["module_id"]
            for item in recommendations
        }

        for module_id, row in existing.items():
            if (
                module_id not in recommended_ids
                and row["status"]
                in {
                    "assigned",
                    "unassigned",
                    "overdue",
                }
            ):
                connection.execute(
                    """
                    UPDATE training_assignments
                    SET
                        status = 'not_required',
                        updated_at = %s
                    WHERE id = %s;
                    """,
                    (
                        now,
                        row["id"],
                    ),
                )

                insert_training_event(
                    connection,
                    row["id"],
                    "training_not_required",
                    actor="governance-automation",
                    details={
                        "module_id": module_id,
                        "reason": (
                            "Triggering control "
                            "no longer requires "
                            "training."
                        ),
                    },
                )

        for item in recommendations:
            module_id = item[
                "module_id"
            ]

            current = existing.get(
                module_id
            )

            desired_status = (
                "assigned"
                if subject_id
                else "unassigned"
            )

            if current is None:
                assignment_id = uuid4()

                assignment = (
                    connection.execute(
                        """
                        INSERT INTO training_assignments (
                            id,
                            application_id,
                            subject_id,
                            module_id,
                            trigger_control,
                            trigger_status,
                            trigger_reason,
                            status,
                            required,
                            assigned_at,
                            due_at,
                            updated_at
                        )
                        VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            TRUE, %s, %s, %s
                        )
                        RETURNING *;
                        """,
                        (
                            assignment_id,
                            application_id,
                            subject_id,
                            module_id,
                            item[
                                "trigger_control"
                            ],
                            item[
                                "control_status"
                            ],
                            item["reason"],
                            desired_status,
                            now,
                            default_due_at,
                            now,
                        ),
                    ).fetchone()
                )

                insert_training_event(
                    connection,
                    assignment_id,
                    (
                        "training_assigned"
                        if subject_id
                        else "training_owner_missing"
                    ),
                    actor="governance-automation",
                    details={
                        "module_id": module_id,
                        "trigger_control": (
                            item[
                                "trigger_control"
                            ]
                        ),
                        "subject_id": subject_id,
                        "due_at": (
                            default_due_at.isoformat()
                        ),
                    },
                )

                existing[
                    module_id
                ] = assignment

                continue

            if current["status"] == "completed":
                connection.execute(
                    """
                    UPDATE training_assignments
                    SET
                        trigger_control = %s,
                        trigger_status = %s,
                        trigger_reason = %s,
                        updated_at = %s
                    WHERE id = %s;
                    """,
                    (
                        item[
                            "trigger_control"
                        ],
                        item[
                            "control_status"
                        ],
                        item["reason"],
                        now,
                        current["id"],
                    ),
                )

                continue

            if current["status"] == "not_required":
                connection.execute(
                    """
                    UPDATE training_assignments
                    SET
                        subject_id = %s,
                        trigger_control = %s,
                        trigger_status = %s,
                        trigger_reason = %s,
                        status = %s,
                        assigned_at = %s,
                        due_at = %s,
                        completed_at = NULL,
                        updated_at = %s
                    WHERE id = %s;
                    """,
                    (
                        subject_id,
                        item[
                            "trigger_control"
                        ],
                        item[
                            "control_status"
                        ],
                        item["reason"],
                        desired_status,
                        now,
                        default_due_at,
                        now,
                        current["id"],
                    ),
                )

                insert_training_event(
                    connection,
                    current["id"],
                    "training_reassigned",
                    actor="governance-automation",
                    details={
                        "module_id": module_id,
                        "subject_id": subject_id,
                        "due_at": (
                            default_due_at.isoformat()
                        ),
                    },
                )

                continue

            effective_status = (
                "unassigned"
                if not subject_id
                else (
                    "overdue"
                    if current[
                        "due_at"
                    ] <= now
                    else "assigned"
                )
            )

            connection.execute(
                """
                UPDATE training_assignments
                SET
                    subject_id = %s,
                    trigger_control = %s,
                    trigger_status = %s,
                    trigger_reason = %s,
                    status = %s,
                    updated_at = %s
                WHERE id = %s;
                """,
                (
                    subject_id,
                    item[
                        "trigger_control"
                    ],
                    item[
                        "control_status"
                    ],
                    item["reason"],
                    effective_status,
                    now,
                    current["id"],
                ),
            )

        connection.commit()

    refresh_overdue_assignments(
        application_id
    )

    assignments = get_training_assignments(
        application_id
    )

    active_required = [
        item
        for item in assignments["assignments"]
        if (
            item["required"]
            and item["status"]
            in {
                "assigned",
                "unassigned",
                "overdue",
            }
        )
    ]

    return {
        "status": "evaluated",
        "application_id": application_id,
        "application_name": (
            guidance["application_name"]
        ),
        "subject_id": subject_id,
        "recommended_training_count": (
            len(recommendations)
        ),
        "required_incomplete_count": (
            len(active_required)
        ),
        "approval_ready": (
            len(active_required) == 0
        ),
        "assignments": (
            assignments["assignments"]
        ),
    }


def get_training_assignments(
    application_id: UUID,
):
    refresh_overdue_assignments(
        application_id
    )

    with get_connection() as connection:
        application = connection.execute(
            """
            SELECT id, name
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

        assignments = connection.execute(
            """
            SELECT *
            FROM training_assignments
            WHERE application_id = %s
            ORDER BY assigned_at DESC;
            """,
            (application_id,),
        ).fetchall()

    return {
        "application_id": application_id,
        "application_name": (
            application["name"]
        ),
        "count": len(assignments),
        "assignments": assignments,
    }


def get_training_status(
    application_id: UUID,
    subject_id: str,
):
    guidance = build_guidance(
        application_id
    )

    refresh_overdue_assignments(
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

        assignments = connection.execute(
            """
            SELECT *
            FROM training_assignments
            WHERE application_id = %s
              AND subject_id = %s
            ORDER BY assigned_at DESC;
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

    active_required = [
        row
        for row in assignments
        if (
            row["required"]
            and row["status"]
            in {
                "assigned",
                "overdue",
                "unassigned",
            }
        )
    ]

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
        "required_incomplete_count": (
            len(active_required)
        ),
        "approval_ready": (
            len(active_required) == 0
        ),
        "completed_modules": completed,
        "assignments": assignments,
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

    now = datetime.now(timezone.utc)

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

        assignment = connection.execute(
            """
            UPDATE training_assignments
            SET
                status = 'completed',
                completed_at = %s,
                updated_at = %s
            WHERE application_id = %s
              AND subject_id = %s
              AND module_id = %s
              AND status != 'completed'
            RETURNING *;
            """,
            (
                now,
                now,
                application_id,
                payload.subject_id,
                payload.module_id,
            ),
        ).fetchone()

        if assignment:
            insert_training_event(
                connection,
                assignment["id"],
                "training_completed",
                actor=payload.subject_id,
                details={
                    "module_id": (
                        payload.module_id
                    ),
                },
            )

        connection.commit()

    status = get_training_status(
        application_id,
        payload.subject_id,
    )

    return {
        "completion": completion,
        "assignment": assignment,
        "training_status": status,
    }
