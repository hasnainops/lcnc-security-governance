"""Persist independently known features from the latest fresh observation.

NULL represents insufficient evidence. Partial collection invalidates previous
values instead of retaining them as current or substituting fabricated zeros.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .database import get_connection
from .feature_assembly import FEATURE_NAMES


def persist_current_features(application_id, observation_id, values, *, evidence=None,
                             connection=None):
    if set(values) != set(FEATURE_NAMES) or any(
        value is not None and (type(value) is not int or value < 0)
        for value in values.values()
    ):
        raise ValueError("Invalid independently verified features")

    if connection is None:
        with get_connection() as opened:
            return persist_current_features(application_id, observation_id, values,
                                            evidence=evidence, connection=opened)

    # Observation ingestion takes this same application row lock. A delayed
    # ingestion request cannot overwrite facts from a newer observation.
    current = connection.execute(
        "SELECT * FROM applications WHERE id = %s FOR UPDATE;",
        (application_id,),
    ).fetchone()
    if current is None:
        raise HTTPException(404, "Application not found")
    latest = connection.execute(
        """SELECT id, observed_at FROM discovery_observations
           WHERE application_id = %s AND source = 'appsmith'
           ORDER BY observed_at DESC, received_at DESC LIMIT 1;""",
        (application_id,),
    ).fetchone()
    result = {"action": "superseded", "changed": False,
              "source_observation_id": str(observation_id)}
    if latest is None or str(latest["id"]) != str(observation_id):
        return result

    now = datetime.now(timezone.utc)
    stale = not now - timedelta(minutes=3) <= latest["observed_at"] <= now
    persisted = {name: None if stale else values[name] for name in FEATURE_NAMES}
    values_changed = any(current[name] != persisted[name] for name in FEATURE_NAMES)
    old_evidence = current.get("discovery_feature_evidence") or {}
    evidence_changed = evidence is not None and (
        old_evidence.get("semantic_sha256") != evidence.get("semantic_sha256")
    )
    changed = values_changed or evidence_changed
    if changed:
        connection.execute(
            """UPDATE applications SET
               external_integration_count = %s,
               unapproved_integration_count = %s,
               connector_count = %s, external_domain_count = %s,
               changes_last_24h = %s,
               ml_anomaly_status = 'stale', ml_anomalous = NULL,
               ml_decision_score = NULL, ml_model_version = NULL,
               ml_assessed_at = NULL,
               shadow_it_candidate = CASE WHEN LOWER(platform) = 'appsmith'
                   THEN FALSE ELSE shadow_it_candidate END,
               risk_status = 'stale', risk_score = NULL, risk_level = NULL,
               risk_model_version = NULL, risk_assessed_at = NULL,
               governance_status = 'stale', governance_outcome = NULL,
               governance_decided_at = NULL, updated_at = NOW()
               WHERE id = %s;""",
            (*(persisted[name] for name in FEATURE_NAMES), application_id),
        )
    if evidence is not None:
        persisted_evidence = {**evidence, "fresh": not stale,
                              "missing_features": [name for name in FEATURE_NAMES
                                                   if persisted[name] is None]}
        connection.execute("UPDATE applications SET discovery_feature_evidence=%s WHERE id=%s",
                           (Jsonb(persisted_evidence), application_id))
    result.update(action="stale_observation" if stale else "persisted",
                  changed=changed,
                  feature_values_changed=values_changed, evidence_changed=evidence_changed,
                  missing_features=[name for name in FEATURE_NAMES if persisted[name] is None])
    return result
