"""Canonical enterprise discovery to governance handoff."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from fastapi import HTTPException, status
from psycopg.types.json import Jsonb

from .database import get_connection


ML_FEATURES = [
    "owner_known",
    "business_purpose_known",
    "internet_exposed",
    "external_integration_count",
    "unapproved_integration_count",
    "uses_api_key",
    "connector_count",
    "external_domain_count",
    "changes_last_24h",
]


class EnterpriseDiscoveryHandoff(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=100)

    authorization_status: str = "unknown"

    owner_known: bool | None = None
    business_purpose_known: bool | None = None
    internet_exposed: bool | None = None
    uses_api_key: bool | None = None

    external_integration_count: int | None = Field(
        default=None,
        ge=0,
    )
    unapproved_integration_count: int | None = Field(
        default=None,
        ge=0,
    )
    connector_count: int | None = Field(
        default=None,
        ge=0,
    )
    external_domain_count: int | None = Field(
        default=None,
        ge=0,
    )
    changes_last_24h: int | None = Field(
        default=None,
        ge=0,
    )

    evidence: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None

    ml_result: dict


def persist_enterprise_discovery_handoff(payload):
    """Persist discovery telemetry and an already-computed ML result.

    ML inference happens upstream in the canonical ML Analytics
    service. This function persists that existing result without
    performing another inference.
    """

    ml_result = payload["ml_result"]

    features = {
        feature: payload.get(feature)
        for feature in ML_FEATURES
    }

    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM applications
            WHERE external_id = %s;
            """,
            (payload["external_id"],),
        ).fetchone()

        if (
            existing is not None
            and existing["platform"] != payload["platform"]
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Canonical application identity conflict: "
                    f"external_id {payload['external_id']} "
                    f"already belongs to platform "
                    f"{existing['platform']}."
                ),
            )

        if existing is None:
            application_id = uuid4()

            application = connection.execute(
                """
                INSERT INTO applications (
                    id,
                    external_id,
                    name,
                    platform,
                    registration_status,
                    lifecycle_status,
                    data_classification,
                    internet_exposed,
                    external_integration,
                    integration_approved,
                    credential_type,
                    external_integration_count,
                    unapproved_integration_count,
                    connector_count,
                    external_domain_count,
                    changes_last_24h
                )
                VALUES (
                    %s, %s, %s, %s,
                    'unregistered',
                    'active',
                    'unknown',
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                RETURNING *;
                """,
                (
                    application_id,
                    payload["external_id"],
                    payload["name"],
                    payload["platform"],
                    bool(
                        payload.get(
                            "internet_exposed"
                        )
                    ),
                    (
                        payload.get(
                            "external_integration_count",
                            0,
                        )
                        > 0
                    ),
                    (
                        False
                        if payload.get(
                            "unapproved_integration_count",
                            0,
                        )
                        > 0
                        else None
                    ),
                    (
                        "api_key"
                        if payload.get("uses_api_key")
                        else None
                    ),
                    payload.get(
                        "external_integration_count"
                    ),
                    payload.get(
                        "unapproved_integration_count"
                    ),
                    payload.get("connector_count"),
                    payload.get(
                        "external_domain_count"
                    ),
                    payload.get(
                        "changes_last_24h"
                    ),
                ),
            ).fetchone()

            action = "created"

        else:
            application = connection.execute(
                """
                UPDATE applications
                SET
                    name = %s,
                    internet_exposed = %s,
                    external_integration = %s,
                    external_integration_count = %s,
                    unapproved_integration_count = %s,
                    connector_count = %s,
                    external_domain_count = %s,
                    changes_last_24h = %s,
                    last_seen_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (
                    payload["name"],
                    bool(
                        payload.get(
                            "internet_exposed"
                        )
                    ),
                    (
                        payload.get(
                            "external_integration_count",
                            0,
                        )
                        > 0
                    ),
                    payload.get(
                        "external_integration_count"
                    ),
                    payload.get(
                        "unapproved_integration_count"
                    ),
                    payload.get("connector_count"),
                    payload.get(
                        "external_domain_count"
                    ),
                    payload.get(
                        "changes_last_24h"
                    ),
                    existing["id"],
                ),
            ).fetchone()

            action = "updated"

        connection.execute(
            """
            INSERT INTO ml_assessments (
                id,
                application_id,
                analysis_type,
                anomalous,
                decision_score,
                model_version,
                features,
                context_signals
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s
            );
            """,
            (
                uuid4(),
                application["id"],
                ml_result["analysis_type"],
                ml_result["anomalous"],
                ml_result["raw_decision_score"],
                ml_result["model_version"],
                Jsonb(features),
                Jsonb(
                    ml_result.get(
                        "context_signals",
                        [],
                    )
                ),
            ),
        )

        updated_application = connection.execute(
            """
            UPDATE applications
            SET
                ml_anomaly_status = 'assessed',
                ml_anomalous = %s,
                ml_decision_score = %s,
                ml_model_version = %s,
                ml_assessed_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *;
            """,
            (
                ml_result["anomalous"],
                ml_result["raw_decision_score"],
                ml_result["model_version"],
                application["id"],
            ),
        ).fetchone()

    return {
        "application_id": updated_application["id"],
        "action": action,
        "ml": {
            "anomalous": ml_result["anomalous"],
            "decision_score": (
                ml_result["raw_decision_score"]
            ),
            "model_version": ml_result["model_version"],
        },
    }
