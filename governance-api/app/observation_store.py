"""Persist sanitized observation history; no assessment or transfer execution."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .database import get_connection
from .discovery_observation import AppsmithObservation


def canonical_observation(observation: AppsmithObservation):
    document = observation.model_dump(mode="json")
    document["observed_at"] = observation.observed_at.astimezone(
        timezone.utc
    ).isoformat()
    document["connectors"].sort(key=lambda item: item["connector_id"])
    document["observed_actions"].sort(
        key=lambda item: item["action_id"]
    )
    document["pending_reasons"].sort()
    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return document, digest


def persist_discovery_observation(
    application_id: UUID,
    observation: AppsmithObservation,
):
    latest_allowed = datetime.now(timezone.utc) + timedelta(minutes=5)
    if observation.observed_at > latest_allowed:
        raise HTTPException(
            422, "Observation time is too far in the future"
        )

    document, digest = canonical_observation(observation)
    observed_at = observation.observed_at.astimezone(timezone.utc)

    with get_connection() as connection:
        application = connection.execute(
            """
            SELECT external_id, platform
            FROM applications
            WHERE id = %s
            FOR UPDATE;
            """,
            (application_id,),
        ).fetchone()

        if application is None:
            raise HTTPException(404, "Application not found")
        if (
            application["external_id"] != observation.external_id
            or application["platform"] != observation.source
        ):
            raise HTTPException(
                409, "Observation application identity mismatch"
            )

        row = connection.execute(
            """
            INSERT INTO discovery_observations (
                id, application_id, source, observed_at,
                payload, payload_sha256
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (application_id, source, observed_at) DO NOTHING
            RETURNING id, application_id, source, observed_at,
                      received_at, payload_sha256;
            """,
            (
                uuid4(),
                application_id,
                observation.source,
                observed_at,
                Jsonb(document),
                digest,
            ),
        ).fetchone()
        created = row is not None

        if not created:
            row = connection.execute(
                """
                SELECT id, application_id, source, observed_at,
                       received_at, payload_sha256
                FROM discovery_observations
                WHERE application_id = %s AND source = %s
                  AND observed_at = %s;
                """,
                (application_id, observation.source, observed_at),
            ).fetchone()

            if row is None:
                raise RuntimeError("Observation conflict lookup failed")
            if row["payload_sha256"] != digest:
                raise HTTPException(
                    409,
                    "Observation timestamp already contains different evidence",
                )

        # Invalidate risk only for newly accepted, comparable,
        # chronological Appsmith structural observations.
        risk_invalidated = False

        if (
            created
            and observation.collection_complete
            and "page_ids" in observation.model_fields_set
        ):
            latest = connection.execute(
                """
                SELECT id
                FROM discovery_observations
                WHERE application_id = %s
                  AND source = %s
                ORDER BY observed_at DESC, received_at DESC
                LIMIT 1;
                """,
                (application_id, observation.source),
            ).fetchone()

            if latest is not None and latest["id"] == row["id"]:
                previous = connection.execute(
                    """
                    SELECT payload
                    FROM discovery_observations
                    WHERE application_id = %s
                      AND source = %s
                      AND observed_at < %s
                    ORDER BY observed_at DESC
                    LIMIT 1;
                    """,
                    (
                        application_id,
                        observation.source,
                        observed_at,
                    ),
                ).fetchone()

                if previous is not None:
                    previous_payload = previous["payload"]

                    comparable = (
                        previous_payload.get(
                            "collection_complete"
                        ) is True
                        and "page_ids" in previous_payload
                    )

                    if comparable:
                        from .feature_assembly import (
                            observation_fingerprint,
                        )

                        previous_observation = (
                            AppsmithObservation.model_validate(
                                previous_payload
                            )
                        )

                        changed = (
                            observation_fingerprint(
                                previous_observation
                            )
                            != observation_fingerprint(
                                observation
                            )
                        )

                        if changed:
                            updated = connection.execute(
                                """
                                UPDATE applications
                                SET
                                    risk_status = 'stale',
                                    risk_score = NULL,
                                    risk_level = NULL,
                                    risk_model_version = NULL,
                                    risk_assessed_at = NULL,
                                    updated_at = NOW()
                                WHERE id = %s
                                  AND risk_status = 'assessed'
                                RETURNING id;
                                """,
                                (application_id,),
                            ).fetchone()

                            risk_invalidated = (
                                updated is not None
                            )


        connector_metadata_updated = False

        # Persist verified Appsmith connector evidence in the same
        # transaction as the accepted discovery observation.
        if created and observation.collection_complete:
            latest_evidence = connection.execute(
                """
                SELECT id
                FROM discovery_observations
                WHERE application_id = %s
                  AND source = %s
                ORDER BY observed_at DESC, received_at DESC
                LIMIT 1;
                """,
                (application_id, observation.source),
            ).fetchone()

            if (
                latest_evidence is not None
                and latest_evidence["id"] == row["id"]
            ):
                from .feature_assembly import derive_connector_provenance

                provenance = {
                    "source": "appsmith_verified",
                    **derive_connector_provenance(observation),
                    "verified_connectors": sorted(
                        [
                            {
                                "connector_id": connector.connector_id,
                                "destination_state": connector.destination_state,
                                "destination_host": (
                                    connector.destination.host
                                    if connector.destination is not None
                                    else None
                                ),
                            }
                            for connector in observation.connectors
                        ],
                        key=lambda item: item["connector_id"],
                    ),
                }

                current = connection.execute(
                    """
                    SELECT connector_metadata
                    FROM applications
                    WHERE id = %s;
                    """,
                    (application_id,),
                ).fetchone()

                if current is None:
                    raise RuntimeError("Application disappeared during ingestion")

                existing_raw = current["connector_metadata"]
                existing = None

                if existing_raw:
                    try:
                        existing = json.loads(existing_raw)
                    except (ValueError, TypeError):
                        pass

                # Do not silently overwrite non-Appsmith or
                # manually supplied connector metadata.
                replaceable = (
                    not existing_raw
                    or (
                        isinstance(existing, dict)
                        and existing.get("source") == "appsmith_verified"
                    )
                )

                if replaceable:
                    previous_semantic = (
                        {
                            key: value
                            for key, value in existing.items()
                            if key != "source_observation_id"
                        }
                        if isinstance(existing, dict)
                        else None
                    )

                    # Polling timestamps and observation IDs must not
                    # cause repeated classification invalidation.
                    if previous_semantic != provenance:
                        provenance["source_observation_id"] = str(row["id"])

                        connection.execute(
                            """
                            UPDATE applications
                            SET
                                connector_metadata = %s,
                                ml_classification_status = CASE
                                    WHEN ml_classification_status = 'assessed'
                                    THEN 'stale'
                                    ELSE ml_classification_status
                                END,
                                ml_suggested_classification = CASE
                                    WHEN ml_classification_status = 'assessed'
                                    THEN NULL
                                    ELSE ml_suggested_classification
                                END,
                                ml_classification_confidence = CASE
                                    WHEN ml_classification_status = 'assessed'
                                    THEN NULL
                                    ELSE ml_classification_confidence
                                END,
                                ml_classification_review_required = CASE
                                    WHEN ml_classification_status = 'assessed'
                                    THEN NULL
                                    ELSE ml_classification_review_required
                                END,
                                ml_classification_model_version = CASE
                                    WHEN ml_classification_status = 'assessed'
                                    THEN NULL
                                    ELSE ml_classification_model_version
                                END,
                                ml_classified_at = CASE
                                    WHEN ml_classification_status = 'assessed'
                                    THEN NULL
                                    ELSE ml_classified_at
                                END,
                                updated_at = NOW()
                            WHERE id = %s;
                            """,
                            (
                                json.dumps(provenance, sort_keys=True),
                                application_id,
                            ),
                        )

                        connector_metadata_updated = True

        data_field_evidence_updated = False

        # Synchronize observed widget-field evidence independently
        # of overall connector collection completeness.
        if (
            created
            and observation.data_field_evidence is not None
        ):
            latest_field_observation = connection.execute(
                """
                SELECT id
                FROM discovery_observations
                WHERE application_id = %s
                  AND source = %s
                ORDER BY observed_at DESC, received_at DESC
                LIMIT 1;
                """,
                (application_id, observation.source),
            ).fetchone()

            if (
                latest_field_observation is not None
                and latest_field_observation["id"] == row["id"]
            ):
                evidence = (
                    observation.data_field_evidence.model_dump(
                        mode="json"
                    )
                )

                provenance = {
                    "source": "appsmith_widget_dsl_observed",
                    **evidence,
                }

                current = connection.execute(
                    """
                    SELECT data_field_evidence
                    FROM applications
                    WHERE id = %s;
                    """,
                    (application_id,),
                ).fetchone()

                if current is None:
                    raise RuntimeError(
                        "Application disappeared during field ingestion"
                    )

                existing = current["data_field_evidence"]

                # Preserve externally managed evidence.
                replaceable = (
                    existing is None
                    or (
                        isinstance(existing, dict)
                        and existing.get("source")
                        == "appsmith_widget_dsl_observed"
                    )
                )

                if replaceable:
                    previous_semantic = (
                        {
                            key: value
                            for key, value in existing.items()
                            if key != "source_observation_id"
                        }
                        if isinstance(existing, dict)
                        else None
                    )

                    # Ignore observation IDs when deciding whether
                    # unchanged polling should update the inventory.
                    if previous_semantic != provenance:
                        provenance["source_observation_id"] = str(
                            row["id"]
                        )

                        connection.execute(
                            """
                            UPDATE applications
                            SET
                                data_field_evidence = %s,
                                updated_at = NOW()
                            WHERE id = %s;
                            """,
                            (
                                Jsonb(provenance),
                                application_id,
                            ),
                        )

                        data_field_evidence_updated = True

    return {
        **row,
        "created": created,
        "risk_invalidated": risk_invalidated,
        "connector_metadata_updated": connector_metadata_updated,
        "data_field_evidence_updated": data_field_evidence_updated,
    }
