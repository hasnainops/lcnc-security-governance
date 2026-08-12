import os
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from pydantic import BaseModel
from psycopg.types.json import Jsonb

from .database import get_connection


OPA_URL = os.getenv(
    "OPA_URL",
    "http://opa:8181",
)

ACCESS_POLICY_VERSION = "access-v1"


class AccessRequest(BaseModel):
    subject_id: str

    role: Literal[
        "viewer",
        "developer",
        "security_admin",
    ]

    action: Literal[
        "read",
        "modify",
        "export",
        "review",
        "approve",
    ]


def authorize_and_persist(
    application_id: UUID,
    request: AccessRequest,
):
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
            status_code=404,
            detail="Application not found",
        )

    policy_input = {
        "subject_id": request.subject_id,
        "role": request.role,
        "action": request.action,
        "registration_status": (
            application["registration_status"]
        ),
        "data_classification": (
            application["data_classification"]
        ),
    }

    try:
        response = httpx.post(
            f"{OPA_URL}/v1/data/lcnc/access/decision",
            json={
                "input": policy_input
            },
            timeout=10.0,
        )

        response.raise_for_status()

    except (
        httpx.ConnectError,
        httpx.TimeoutException,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "allowed": False,
                "decision": "deny",
                "reason": "opa_unavailable",
                "message": (
                    "Authorization failed closed "
                    "because OPA is unavailable."
                ),
            },
        ) from exc

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "allowed": False,
                "decision": "deny",
                "reason": "opa_upstream_error",
            },
        ) from exc

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "allowed": False,
                "decision": "deny",
                "reason": "opa_request_failed",
            },
        ) from exc

    result = response.json().get("result")

    if result is None:
        raise HTTPException(
            status_code=502,
            detail={
                "allowed": False,
                "decision": "deny",
                "reason": "opa_no_decision",
            },
        )

    allowed = result.get("allow")
    decision = result.get("action")
    reasons = result.get("reasons", [])

    if (
        not isinstance(allowed, bool)
        or decision not in {"allow", "deny"}
    ):
        raise HTTPException(
            status_code=502,
            detail={
                "allowed": False,
                "decision": "deny",
                "reason": "opa_invalid_decision",
            },
        )

    decision_id = uuid4()

    with get_connection() as connection:
        persisted = connection.execute(
            """
            INSERT INTO access_decisions (
                id,
                application_id,
                subject_id,
                role,
                requested_action,
                allowed,
                decision,
                reasons,
                registration_status,
                data_classification,
                policy_version
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s
            )
            RETURNING evaluated_at;
            """,
            (
                decision_id,
                application_id,
                request.subject_id,
                request.role,
                request.action,
                allowed,
                decision,
                Jsonb(reasons),
                application[
                    "registration_status"
                ],
                application[
                    "data_classification"
                ],
                ACCESS_POLICY_VERSION,
            ),
        ).fetchone()

    return {
        "decision_id": decision_id,
        "application_id": application_id,
        "application_name": application["name"],
        "subject_id": request.subject_id,
        "role": request.role,
        "requested_action": request.action,
        "allowed": allowed,
        "decision": decision,
        "reasons": reasons,
        "registration_status": (
            application["registration_status"]
        ),
        "data_classification": (
            application["data_classification"]
        ),
        "policy_version": ACCESS_POLICY_VERSION,
        "evaluated_at": persisted["evaluated_at"],
    }
