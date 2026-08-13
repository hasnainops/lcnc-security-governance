import os

from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field


jit_router = APIRouter(
    prefix="/privileges",
    tags=["JIT Privileges"],
)

DATABASE_URL = os.environ["DATABASE_URL"]

JIT_EXPIRY_INTERVAL_SECONDS = int(
    os.getenv(
        "JIT_EXPIRY_INTERVAL_SECONDS",
        "30",
    )
)


class PrivilegeRequestCreate(BaseModel):
    application_id: UUID

    subject_id: str = Field(
        min_length=1,
        max_length=255,
    )

    base_role: Literal[
        "viewer",
        "developer",
        "security_admin",
    ]

    requested_action: Literal[
        "modify",
        "export",
        "approve",
    ]

    justification: str = Field(
        min_length=1,
        max_length=2000,
    )

    requested_duration_minutes: int = Field(
        ge=5,
        le=480,
    )


class PrivilegeDecision(BaseModel):
    decision: Literal[
        "approve",
        "reject",
    ]

    actor: str = Field(
        min_length=1,
        max_length=255,
    )

    reason: str = Field(
        min_length=1,
        max_length=2000,
    )


class PrivilegeRevocation(BaseModel):
    actor: str = Field(
        min_length=1,
        max_length=255,
    )

    reason: str = Field(
        min_length=1,
        max_length=2000,
    )


def get_connection():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    )


def insert_privilege_event(
    connection,
    event_type,
    *,
    privilege_request_id=None,
    privilege_grant_id=None,
    actor=None,
    details=None,
):
    connection.execute(
        """
        INSERT INTO privilege_events (
            id,
            privilege_request_id,
            privilege_grant_id,
            event_type,
            actor,
            details
        )
        VALUES (%s, %s, %s, %s, %s, %s);
        """,
        (
            uuid4(),
            privilege_request_id,
            privilege_grant_id,
            event_type,
            actor,
            Jsonb(details or {}),
        ),
    )


def expire_grants():
    now = datetime.now(timezone.utc)

    with get_connection() as connection:
        expired = connection.execute(
            """
            UPDATE privilege_grants
            SET
                status = 'expired',
                revoked_at = %s,
                revoked_by = 'governance-automation',
                revocation_reason = 'JIT privilege TTL expired.'
            WHERE status = 'active'
              AND expires_at <= %s
            RETURNING *;
            """,
            (
                now,
                now,
            ),
        ).fetchall()

        for grant in expired:
            insert_privilege_event(
                connection,
                "privilege_expired",
                privilege_request_id=(
                    grant["privilege_request_id"]
                ),
                privilege_grant_id=grant["id"],
                actor="governance-automation",
                details={
                    "subject_id": grant["subject_id"],
                    "granted_action": (
                        grant["granted_action"]
                    ),
                    "expires_at": (
                        grant["expires_at"].isoformat()
                    ),
                },
            )

        connection.commit()

    return len(expired)


_jit_stop_event = Event()


def jit_expiry_worker():
    while not _jit_stop_event.wait(
        JIT_EXPIRY_INTERVAL_SECONDS
    ):
        try:
            expire_grants()
        except Exception:
            pass


def start_jit_expiry_worker():
    _jit_stop_event.clear()

    thread = Thread(
        target=jit_expiry_worker,
        daemon=True,
    )

    thread.start()


def stop_jit_expiry_worker():
    _jit_stop_event.set()


@jit_router.post(
    "/requests",
    status_code=201,
)
def create_privilege_request(
    payload: PrivilegeRequestCreate,
):
    request_id = uuid4()

    with get_connection() as connection:
        application = connection.execute(
            """
            SELECT id, name
            FROM applications
            WHERE id = %s;
            """,
            (payload.application_id,),
        ).fetchone()

        if not application:
            raise HTTPException(
                status_code=404,
                detail="Application not found.",
            )

        record = connection.execute(
            """
            INSERT INTO privilege_requests (
                id,
                application_id,
                subject_id,
                base_role,
                requested_action,
                justification,
                status,
                required_role,
                requested_duration_minutes
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, 'pending',
                'Security/GRC Reviewer',
                %s
            )
            RETURNING *;
            """,
            (
                request_id,
                payload.application_id,
                payload.subject_id,
                payload.base_role,
                payload.requested_action,
                payload.justification,
                payload.requested_duration_minutes,
            ),
        ).fetchone()

        insert_privilege_event(
            connection,
            "privilege_requested",
            privilege_request_id=request_id,
            actor=payload.subject_id,
            details={
                "application_name": (
                    application["name"]
                ),
                "base_role": payload.base_role,
                "requested_action": (
                    payload.requested_action
                ),
                "requested_duration_minutes": (
                    payload.requested_duration_minutes
                ),
                "justification": (
                    payload.justification
                ),
            },
        )

        connection.commit()

    return record


@jit_router.get("/requests")
def list_privilege_requests(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
):
    with get_connection() as connection:
        records = connection.execute(
            """
            SELECT
                pr.*,
                a.name AS application_name
            FROM privilege_requests pr
            JOIN applications a
              ON a.id = pr.application_id
            ORDER BY pr.requested_at DESC
            LIMIT %s;
            """,
            (limit,),
        ).fetchall()

    return {
        "count": len(records),
        "requests": records,
    }


@jit_router.post(
    "/requests/{request_id}/decision"
)
def decide_privilege_request(
    request_id: UUID,
    payload: PrivilegeDecision,
):
    now = datetime.now(timezone.utc)

    with get_connection() as connection:
        request_record = connection.execute(
            """
            SELECT *
            FROM privilege_requests
            WHERE id = %s;
            """,
            (request_id,),
        ).fetchone()

        if not request_record:
            raise HTTPException(
                status_code=404,
                detail="Privilege request not found.",
            )

        if request_record["status"] != "pending":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Privilege request has already "
                    "been decided."
                ),
            )

        if payload.decision == "reject":
            updated = connection.execute(
                """
                UPDATE privilege_requests
                SET
                    status = 'rejected',
                    decided_by = %s,
                    decision_reason = %s,
                    decided_at = %s
                WHERE id = %s
                RETURNING *;
                """,
                (
                    payload.actor,
                    payload.reason,
                    now,
                    request_id,
                ),
            ).fetchone()

            insert_privilege_event(
                connection,
                "privilege_rejected",
                privilege_request_id=request_id,
                actor=payload.actor,
                details={
                    "reason": payload.reason,
                },
            )

            connection.commit()

            return {
                "request": updated,
                "grant": None,
            }

        expires_at = now + timedelta(
            minutes=request_record[
                "requested_duration_minutes"
            ]
        )

        updated = connection.execute(
            """
            UPDATE privilege_requests
            SET
                status = 'approved',
                decided_by = %s,
                decision_reason = %s,
                decided_at = %s
            WHERE id = %s
            RETURNING *;
            """,
            (
                payload.actor,
                payload.reason,
                now,
                request_id,
            ),
        ).fetchone()

        grant_id = uuid4()

        grant = connection.execute(
            """
            INSERT INTO privilege_grants (
                id,
                privilege_request_id,
                application_id,
                subject_id,
                granted_action,
                granted_by,
                status,
                granted_at,
                expires_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, 'active', %s, %s
            )
            RETURNING *;
            """,
            (
                grant_id,
                request_id,
                request_record["application_id"],
                request_record["subject_id"],
                request_record["requested_action"],
                payload.actor,
                now,
                expires_at,
            ),
        ).fetchone()

        insert_privilege_event(
            connection,
            "privilege_granted",
            privilege_request_id=request_id,
            privilege_grant_id=grant_id,
            actor=payload.actor,
            details={
                "subject_id": (
                    request_record["subject_id"]
                ),
                "granted_action": (
                    request_record[
                        "requested_action"
                    ]
                ),
                "expires_at": (
                    expires_at.isoformat()
                ),
                "reason": payload.reason,
            },
        )

        connection.commit()

    return {
        "request": updated,
        "grant": grant,
    }


@jit_router.get("/grants")
def list_privilege_grants(
    active_only: bool = False,
):
    expire_grants()

    with get_connection() as connection:
        if active_only:
            records = connection.execute(
                """
                SELECT
                    pg.*,
                    a.name AS application_name
                FROM privilege_grants pg
                JOIN applications a
                  ON a.id = pg.application_id
                WHERE pg.status = 'active'
                  AND pg.expires_at > NOW()
                ORDER BY pg.granted_at DESC;
                """
            ).fetchall()

        else:
            records = connection.execute(
                """
                SELECT
                    pg.*,
                    a.name AS application_name
                FROM privilege_grants pg
                JOIN applications a
                  ON a.id = pg.application_id
                ORDER BY pg.granted_at DESC;
                """
            ).fetchall()

    return {
        "count": len(records),
        "grants": records,
    }


@jit_router.get("/check")
def check_privilege(
    application_id: UUID,
    subject_id: str,
    action: str,
):
    with get_connection() as connection:
        grant = connection.execute(
            """
            SELECT *
            FROM privilege_grants
            WHERE application_id = %s
              AND subject_id = %s
              AND granted_action = %s
              AND status = 'active'
              AND expires_at > NOW()
            ORDER BY expires_at DESC
            LIMIT 1;
            """,
            (
                application_id,
                subject_id,
                action,
            ),
        ).fetchone()

    if not grant:
        return {
            "active": False,
            "grant": None,
        }

    return {
        "active": True,
        "grant": grant,
    }


@jit_router.post(
    "/grants/{grant_id}/revoke"
)
def revoke_privilege_grant(
    grant_id: UUID,
    payload: PrivilegeRevocation,
):
    now = datetime.now(timezone.utc)

    with get_connection() as connection:
        grant = connection.execute(
            """
            SELECT *
            FROM privilege_grants
            WHERE id = %s;
            """,
            (grant_id,),
        ).fetchone()

        if not grant:
            raise HTTPException(
                status_code=404,
                detail="Privilege grant not found.",
            )

        if grant["status"] != "active":
            raise HTTPException(
                status_code=409,
                detail="Privilege grant is not active.",
            )

        updated = connection.execute(
            """
            UPDATE privilege_grants
            SET
                status = 'revoked',
                revoked_at = %s,
                revoked_by = %s,
                revocation_reason = %s
            WHERE id = %s
            RETURNING *;
            """,
            (
                now,
                payload.actor,
                payload.reason,
                grant_id,
            ),
        ).fetchone()

        insert_privilege_event(
            connection,
            "privilege_revoked",
            privilege_request_id=(
                grant["privilege_request_id"]
            ),
            privilege_grant_id=grant_id,
            actor=payload.actor,
            details={
                "reason": payload.reason,
            },
        )

        connection.commit()

    return updated


@jit_router.post("/expire/run")
def run_expiry():
    count = expire_grants()

    return {
        "status": "completed",
        "expired_grants": count,
    }
