import os

from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field


app = FastAPI(
    title="LCNC Governance Automation",
    version="0.1.0",
)


DATABASE_URL = os.environ["DATABASE_URL"]

ESCALATION_INTERVAL_SECONDS = int(
    os.getenv(
        "ESCALATION_INTERVAL_SECONDS",
        "30",
    )
)


class HumanDecision(BaseModel):
    decision: Literal[
        "approve",
        "reject",
        "request_changes",
    ]

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


def route_settings(
    outcome: str,
    required_role: str | None,
):
    if outcome == "AUTO_APPROVE":
        return {
            "route_type": "human_confirmation",
            "required_role": (
                "Business Application Owner"
            ),
            "due_hours": 24,
        }

    if outcome == "BUSINESS_REVIEW":
        return {
            "route_type": "business_review",
            "required_role": (
                required_role
                or "Business Application Owner"
            ),
            "due_hours": 24,
        }

    if outcome == "SECURITY_REVIEW":
        return {
            "route_type": "security_review",
            "required_role": (
                required_role
                or "Security/GRC Reviewer"
            ),
            "due_hours": 8,
        }

    if outcome == "BLOCK":
        return {
            "route_type": (
                "security_remediation_review"
            ),
            "required_role": (
                "Security/GRC Reviewer"
            ),
            "due_hours": 4,
        }

    raise HTTPException(
        status_code=400,
        detail=(
            f"Unsupported governance outcome: "
            f"{outcome}"
        ),
    )


def insert_event(
    connection,
    approval_request_id,
    event_type,
    actor=None,
    details=None,
):
    connection.execute(
        """
        INSERT INTO approval_events (
            id,
            approval_request_id,
            event_type,
            actor,
            details
        )
        VALUES (%s, %s, %s, %s, %s);
        """,
        (
            uuid4(),
            approval_request_id,
            event_type,
            actor,
            Jsonb(details or {}),
        ),
    )


def escalate_overdue():
    now = datetime.now(timezone.utc)

    with get_connection() as connection:
        overdue = connection.execute(
            """
            SELECT *
            FROM approval_requests
            WHERE status = 'pending'
              AND due_at <= %s
              AND escalation_level = 0
            ORDER BY due_at ASC;
            """,
            (now,),
        ).fetchall()

        for request in overdue:
            if request["route_type"] in (
                "security_review",
                "security_remediation_review",
            ):
                escalated_role = (
                    "Senior Security/GRC Reviewer"
                )
            else:
                escalated_role = (
                    "Business Unit Approver"
                )

            connection.execute(
                """
                UPDATE approval_requests
                SET
                    status = 'escalated',
                    required_role = %s,
                    escalation_level = 1,
                    escalated_at = %s,
                    updated_at = %s
                WHERE id = %s;
                """,
                (
                    escalated_role,
                    now,
                    now,
                    request["id"],
                ),
            )

            insert_event(
                connection,
                request["id"],
                "approval_escalated",
                actor="governance-automation",
                details={
                    "previous_role": (
                        request["required_role"]
                    ),
                    "escalated_role": (
                        escalated_role
                    ),
                    "reason": (
                        "Approval SLA expired."
                    ),
                },
            )

        connection.commit()

    return len(overdue)


_stop_event = Event()


def escalation_worker():
    while not _stop_event.wait(
        ESCALATION_INTERVAL_SECONDS
    ):
        try:
            escalate_overdue()
        except Exception:
            pass


@app.on_event("startup")
def start_escalation_worker():
    thread = Thread(
        target=escalation_worker,
        daemon=True,
    )
    thread.start()


@app.on_event("shutdown")
def stop_escalation_worker():
    _stop_event.set()


@app.get("/", response_class=HTMLResponse)
def dashboard():
    with get_connection() as connection:
        counts = connection.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE status = 'pending'
                ) AS pending,
                COUNT(*) FILTER (
                    WHERE status = 'escalated'
                ) AS escalated,
                COUNT(*) FILTER (
                    WHERE status IN (
                        'approved',
                        'rejected',
                        'changes_requested'
                    )
                ) AS decided
            FROM approval_requests;
            """
        ).fetchone()

        latest = connection.execute(
            """
            SELECT
                ar.*,
                a.name AS application_name
            FROM approval_requests ar
            JOIN applications a
              ON a.id = ar.application_id
            ORDER BY ar.created_at DESC
            LIMIT 1;
            """
        ).fetchone()

    app_name = (
        latest["application_name"]
        if latest
        else "None"
    )

    status = (
        latest["status"]
        if latest
        else "None"
    )

    role = (
        latest["required_role"]
        if latest
        else "None"
    )

    outcome = (
        latest["governance_outcome"]
        if latest
        else "None"
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>LCNC Governance Automation</title>
        <meta http-equiv="refresh" content="10">

        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 40px;
                max-width: 900px;
            }}

            .card {{
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 18px;
                margin-bottom: 16px;
            }}

            a {{
                margin-right: 18px;
            }}
        </style>
    </head>

    <body>
        <h1>LCNC Governance Automation</h1>

        <div class="card">
            <strong>Status:</strong> Healthy<br>
            <strong>Pending approvals:</strong>
            {counts["pending"]}<br>
            <strong>Escalated:</strong>
            {counts["escalated"]}<br>
            <strong>Decided:</strong>
            {counts["decided"]}
        </div>

        <div class="card">
            <h3>Latest Approval</h3>
            <strong>Application:</strong>
            {app_name}<br>
            <strong>Governance outcome:</strong>
            {outcome}<br>
            <strong>Status:</strong>
            {status}<br>
            <strong>Required role:</strong>
            {role}
        </div>

        <div class="card">
            <a href="/approvals">Approvals</a>
            <a href="/escalations">Escalations</a>
            <a href="/docs">API Documentation</a>
            <a href="/health">Health</a>
        </div>
    </body>
    </html>
    """


@app.get("/health")
def health():
    with get_connection() as connection:
        connection.execute("SELECT 1").fetchone()

    return {
        "status": "healthy",
        "service": "governance-automation",
        "version": "governance-automation-v1",
        "human_in_the_loop": True,
        "automatic_escalation": True,
    }


@app.get("/approvals")
def approvals(
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
                ar.*,
                a.name AS application_name
            FROM approval_requests ar
            JOIN applications a
              ON a.id = ar.application_id
            ORDER BY ar.created_at DESC
            LIMIT %s;
            """,
            (limit,),
        ).fetchall()

    return {
        "count": len(records),
        "approvals": records,
    }


@app.get("/escalations")
def escalations():
    with get_connection() as connection:
        records = connection.execute(
            """
            SELECT
                ar.*,
                a.name AS application_name
            FROM approval_requests ar
            JOIN applications a
              ON a.id = ar.application_id
            WHERE ar.escalation_level > 0
               OR ar.status = 'escalated'
            ORDER BY ar.updated_at DESC;
            """
        ).fetchall()

    return {
        "count": len(records),
        "escalations": records,
    }


@app.post(
    "/applications/{application_id}/route",
    status_code=201,
)
def route_application(
    application_id: UUID,
):
    now = datetime.now(timezone.utc)

    with get_connection() as connection:
        decision = connection.execute(
            """
            SELECT
                gd.*,
                ra.level AS risk_level,
                a.name AS application_name
            FROM governance_decisions gd
            JOIN applications a
              ON a.id = gd.application_id
            LEFT JOIN risk_assessments ra
              ON ra.id = gd.risk_assessment_id
            WHERE gd.application_id = %s
            ORDER BY gd.created_at DESC
            LIMIT 1;
            """,
            (application_id,),
        ).fetchone()

        if not decision:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No governance decision exists "
                    "for this application."
                ),
            )

        existing = connection.execute(
            """
            SELECT *
            FROM approval_requests
            WHERE governance_decision_id = %s;
            """,
            (decision["id"],),
        ).fetchone()

        if existing:
            return existing

        routing = route_settings(
            decision["outcome"],
            decision["required_role"],
        )

        approval_id = uuid4()

        due_at = now + timedelta(
            hours=routing["due_hours"]
        )

        approval = connection.execute(
            """
            INSERT INTO approval_requests (
                id,
                application_id,
                governance_decision_id,
                route_type,
                status,
                required_role,
                risk_level,
                governance_outcome,
                due_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            RETURNING *;
            """,
            (
                approval_id,
                application_id,
                decision["id"],
                routing["route_type"],
                "pending",
                routing["required_role"],
                decision["risk_level"],
                decision["outcome"],
                due_at,
            ),
        ).fetchone()

        insert_event(
            connection,
            approval_id,
            "approval_routed",
            actor="governance-automation",
            details={
                "application_name": (
                    decision["application_name"]
                ),
                "governance_outcome": (
                    decision["outcome"]
                ),
                "risk_level": (
                    decision["risk_level"]
                ),
                "required_role": (
                    routing["required_role"]
                ),
                "due_at": due_at.isoformat(),
            },
        )

        connection.commit()

    return approval


@app.post(
    "/approvals/{approval_id}/decision"
)
def record_decision(
    approval_id: UUID,
    payload: HumanDecision,
):
    now = datetime.now(timezone.utc)

    with get_connection() as connection:
        approval = connection.execute(
            """
            SELECT *
            FROM approval_requests
            WHERE id = %s;
            """,
            (approval_id,),
        ).fetchone()

        if not approval:
            raise HTTPException(
                status_code=404,
                detail="Approval request not found.",
            )

        if approval["status"] in (
            "approved",
            "rejected",
            "changes_requested",
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Approval request is already "
                    "decided."
                ),
            )

        if (
            approval["governance_outcome"]
            == "BLOCK"
            and payload.decision == "approve"
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "A hard policy BLOCK cannot "
                    "be overridden by human approval. "
                    "Remediate the application and "
                    "re-run governance."
                ),
            )

        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "request_changes": (
                "changes_requested"
            ),
        }

        updated = connection.execute(
            """
            UPDATE approval_requests
            SET
                status = %s,
                human_decision = %s,
                decided_by = %s,
                decision_reason = %s,
                decided_at = %s,
                updated_at = %s
            WHERE id = %s
            RETURNING *;
            """,
            (
                status_map[payload.decision],
                payload.decision,
                payload.actor,
                payload.reason,
                now,
                now,
                approval_id,
            ),
        ).fetchone()

        insert_event(
            connection,
            approval_id,
            "human_decision_recorded",
            actor=payload.actor,
            details={
                "decision": payload.decision,
                "reason": payload.reason,
            },
        )

        connection.commit()

    return updated


@app.post("/escalations/run")
def run_escalations():
    count = escalate_overdue()

    return {
        "status": "completed",
        "escalated_requests": count,
    }
