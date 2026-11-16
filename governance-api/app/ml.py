import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from psycopg.types.json import Jsonb

from .database import get_connection


ML_ANALYTICS_URL = os.getenv(
    "ML_ANALYTICS_URL",
    "http://ml-analytics:8002",
)


OBSERVED_FEATURES = [
    "external_integration_count",
    "unapproved_integration_count",
    "connector_count",
    "external_domain_count",
    "changes_last_24h",
]


def analyze_ml_if_needed(application_id: UUID):
    """Run existing ML scorer only when assessment is not current."""

    with get_connection() as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(41012, hashtext(%s));",
            (str(application_id),),
        )

        row = connection.execute(
            """
            SELECT ml_anomaly_status
            FROM applications
            WHERE id = %s;
            """,
            (application_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(404, "Application not found")

        if row["ml_anomaly_status"] == "assessed":
            return {"action": "skipped"}

        try:
            result = analyze_and_persist(application_id)
        except HTTPException as exc:
            if exc.status_code == 409 and exc.detail == "Discovery features changed or expired during inference":
                return {"action": "pending", "reason": "fresh_unchanged_features_required"}
            raise

        return {
            "action": "assessed",
            "assessment_id": str(result["assessment_id"]),
        }


def analyze_and_persist(
    application_id: UUID,
    *,
    diagnostic_features=None,
    diagnostic_provenance=None,
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    if diagnostic_features is None:
        if diagnostic_provenance is not None:
            raise HTTPException(422, "Unexpected provenance")

        feature_values = {
            name: application[name]
            for name in OBSERVED_FEATURES
        }
    else:
        valid = (
            isinstance(diagnostic_features, dict)
            and set(diagnostic_features) == set(OBSERVED_FEATURES)
            and all(
                type(diagnostic_features[name]) is int
                and diagnostic_features[name] >= 0
                for name in OBSERVED_FEATURES
            )
            and isinstance(diagnostic_provenance, dict)
            and diagnostic_provenance.get(
                "assessment_tier"
            ) == "cold_start_witnessed"
            and diagnostic_provenance.get(
                "certified_24h"
            ) is False
            and type(diagnostic_provenance.get(
                "witnessed_changes"
            )) is int
            and diagnostic_provenance[
                "witnessed_changes"
            ] >= 1
            and diagnostic_features[
                "changes_last_24h"
            ] == diagnostic_provenance[
                "witnessed_changes"
            ]
            and isinstance(
                diagnostic_provenance.get(
                    "observation_fingerprint"
                ), str
            )
            and isinstance(
                diagnostic_provenance.get(
                    "source_observation_id"
                ), str
            )
        )

        if not valid:
            raise HTTPException(
                422, "Invalid cold-start evidence"
            )

        feature_values = diagnostic_features

    missing_features = [
        feature
        for feature in OBSERVED_FEATURES
        if feature_values[feature] is None
    ]

    if missing_features:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "ML analysis requires complete observed "
                    "application metadata."
                ),
                "missing_features": missing_features,
            },
        )

    credential_type = (
        application["credential_type"] or ""
    ).strip().lower()

    payload = {
        "owner_known": int(
            bool(
                application["owner_name"]
                or application["owner_email"]
            )
        ),
        "business_purpose_known": int(
            bool(application["business_purpose"])
        ),
        "internet_exposed": int(
            bool(application["internet_exposed"])
        ),
        "external_integration_count": (
            application["external_integration_count"]
        ),
        "unapproved_integration_count": (
            application["unapproved_integration_count"]
        ),
        "uses_api_key": int(
            credential_type
            in {
                "api_key",
                "api-key",
                "apikey",
            }
        ),
        "connector_count": (
            application["connector_count"]
        ),
        "external_domain_count": (
            application["external_domain_count"]
        ),
        "changes_last_24h": (
            application["changes_last_24h"]
        ),
    }

    if diagnostic_features is not None:
        payload.update(diagnostic_features)

    try:
        response = httpx.post(
            f"{ML_ANALYTICS_URL}/analyze",
            json=payload,
            timeout=10.0,
        )

        response.raise_for_status()

    except (
        httpx.ConnectError,
        httpx.TimeoutException,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "ML Analytics unavailable. "
                "No ML assessment was persisted."
            ),
        ) from exc

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "ML Analytics returned an "
                "upstream HTTP error."
            ),
        ) from exc

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="ML Analytics request failed.",
        ) from exc

    analysis = response.json()

    context_signals = analysis["context_signals"]

    if not isinstance(context_signals, list):
        raise HTTPException(
            502, "Invalid ML context signals"
        )

    ml_status = "assessed"

    feature_evidence = application.get("discovery_feature_evidence")
    if diagnostic_features is None and isinstance(feature_evidence, dict):
        context_signals = [*context_signals, {"discovery_feature_evidence": feature_evidence}]

    if diagnostic_features is not None:
        ml_status = "diagnostic"
        context_signals = [
            *context_signals,
            {
                "lo1_diagnostic_provenance":
                    diagnostic_provenance,
                "feature_provenance": {
                    **{
                        name: "verified_appsmith_observation"
                        for name in OBSERVED_FEATURES[:-1]
                    },
                    "changes_last_24h":
                        "cold_start_witnessed_only",
                },
            },
        ]

    assessment_id = uuid4()

    with get_connection() as connection:
        if diagnostic_features is None and isinstance(feature_evidence, dict):
            # The temporal scorer must not overwrite newer connector/policy
            # evidence while its HTTP inference was in flight.
            current = connection.execute(
                "SELECT * FROM applications WHERE id=%s FOR UPDATE", (application_id,)
            ).fetchone()
            latest_evidence = (current or {}).get("discovery_feature_evidence") or {}
            relevant = [*OBSERVED_FEATURES, "owner_name", "owner_email",
                        "business_purpose", "internet_exposed", "credential_type"]
            try:
                observed_at = datetime.fromisoformat(latest_evidence.get("observed_at", ""))
                now = datetime.now(timezone.utc)
                fresh = now - timedelta(minutes=3) <= observed_at <= now
            except (ValueError, TypeError):
                fresh = False
            if (not current or not fresh
                or any(current.get(key) != application.get(key) for key in relevant)
                or latest_evidence.get("semantic_sha256") != feature_evidence.get("semantic_sha256")):
                raise HTTPException(409, "Discovery features changed or expired during inference")
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
                assessment_id,
                application_id,
                analysis["analysis_type"],
                analysis["anomalous"],
                analysis["raw_decision_score"],
                analysis["model_version"],
                Jsonb(payload),
                Jsonb(context_signals),
            ),
        )

        updated_application = connection.execute(
            """
            UPDATE applications
            SET
                ml_anomaly_status = %s,
                ml_anomalous = %s,
                shadow_it_candidate = CASE
                    WHEN LOWER(platform) = 'appsmith'
                    THEN (
                        %s = 'assessed'
                        AND %s IS TRUE
                        AND registration_status = 'unregistered'
                    )
                    ELSE shadow_it_candidate
                END,
                ml_decision_score = %s,
                ml_model_version = %s,
                ml_assessed_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *;
            """,
            (
                ml_status,
                analysis["anomalous"],
                ml_status,
                analysis["anomalous"],
                analysis["raw_decision_score"],
                analysis["model_version"],
                application_id,
            ),
        ).fetchone()

    return {
        "assessment_id": assessment_id,
        "application_id": application_id,
        "application_name": (
            updated_application["name"]
        ),
        "analysis_type": (
            analysis["analysis_type"]
        ),
        "anomalous": analysis["anomalous"],
        "decision_score": (
            analysis["raw_decision_score"]
        ),
        "model_version": (
            analysis["model_version"]
        ),
        "features": payload,
        "context_signals": context_signals,
        "shadow_it_candidate": (
            updated_application["shadow_it_candidate"]
        ),
        "ml_anomaly_status": (
            updated_application[
                "ml_anomaly_status"
            ]
        ),
        "assessed_at": (
            updated_application["ml_assessed_at"]
        ),
    }
