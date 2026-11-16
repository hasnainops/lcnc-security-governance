"""Idempotent classification with evidence provenance and bounded inference leases."""

import os
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator

from .classification_inputs import InputsPending, build_classification_inputs, digest
from .database import get_connection


ML_ANALYTICS_URL = os.getenv("ML_ANALYTICS_URL", "http://ml-analytics:8002")
CLASSES = {"public", "internal", "confidential", "restricted"}


class ModelIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    classification_model_version: str = Field(min_length=1, max_length=100)
    classification_model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification_review_threshold: float = Field(ge=0, le=1, allow_inf_nan=False)


class ModelResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_type: Literal["data-sensitivity-classification"]
    suggested_classification: Literal["public", "internal", "confidential", "restricted"]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    review_required: StrictBool
    review_threshold: float = Field(ge=0, le=1, allow_inf_nan=False)
    model_version: str = Field(min_length=1, max_length=100)
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    class_probabilities: dict[str, float]
    authority: Literal["advisory"]

    @model_validator(mode="after")
    def consistent_probabilities(self):
        probabilities = self.class_probabilities
        if set(probabilities) != CLASSES or any(not 0 <= value <= 1 for value in probabilities.values()):
            raise ValueError("Invalid class probabilities")
        if abs(sum(probabilities.values()) - 1) > 0.001:
            raise ValueError("Class probabilities must sum to one")
        if abs(max(probabilities.values()) - self.confidence) > 0.0002:
            raise ValueError("Confidence does not match class probabilities")
        if probabilities[self.suggested_classification] < max(probabilities.values()):
            raise ValueError("Suggestion is inconsistent with model probabilities")
        return self


def _source(connection, application_id, *, lock=True):
    query = "SELECT *, clock_timestamp() AS classification_now FROM applications WHERE id = %s"
    if lock:
        query += " FOR UPDATE"
    application = connection.execute(query + ";", (application_id,)).fetchone()
    if application is None:
        raise HTTPException(404, "Application not found")
    context = None
    if application.get("owner_context_id"):
        context = connection.execute(
            "SELECT * FROM application_owner_contexts WHERE id = %s AND application_id = %s;",
            (application["owner_context_id"], application_id),
        ).fetchone()
    observation = connection.execute(
        """SELECT id, application_id, observed_at, payload FROM discovery_observations
           WHERE application_id = %s AND source = 'appsmith'
           ORDER BY observed_at DESC, received_at DESC LIMIT 1;""", (application_id,),
    ).fetchone()
    return application, context, observation


def _inputs(source):
    application, context, observation = source
    return build_classification_inputs(application, context, observation, application["classification_now"])


def _state(application, action="unchanged", reasons=None):
    return {
        "application_id": application["id"],
        "action": action,
        "ml_classification_status": application["ml_classification_status"],
        "suggested_classification": application.get("ml_suggested_classification"),
        "confidence": application.get("ml_classification_confidence"),
        "review_required": application.get("ml_classification_review_required"),
        "model_version": application.get("ml_classification_model_version"),
        "classified_at": application.get("ml_classified_at"),
        "authoritative_classification": application["data_classification"],
        "pending_reasons": reasons if reasons is not None else application.get("ml_classification_pending_reasons", []),
        "provenance": application.get("ml_classification_provenance"),
        "authority": "advisory",
    }


def _pending(connection, application, reasons):
    updated = connection.execute(
        """UPDATE applications SET governance_status = 'stale', governance_outcome = NULL,
               governance_decided_at = NULL, ml_classification_status = 'pending',
           ml_suggested_classification = NULL, ml_classification_confidence = NULL,
           ml_classification_review_required = NULL, ml_classification_model_version = NULL,
           ml_classified_at = NULL, ml_classification_input_sha256 = NULL,
           ml_classification_provenance = NULL, ml_classification_pending_reasons = %s,
           ml_classification_lease_id = NULL, ml_classification_lease_until = NULL,
           updated_at = NOW() WHERE id = %s
           AND (ml_classification_status IS DISTINCT FROM 'pending'
                OR ml_classification_pending_reasons IS DISTINCT FROM %s
                OR ml_classification_lease_id IS NOT NULL)
           RETURNING *;""", (Jsonb(reasons), application["id"], Jsonb(reasons)),
    ).fetchone()
    return _state(updated or application, "pending", reasons)


def _key(inputs, identity):
    return digest({"source": inputs.semantic_hash, "model": identity.model_dump()})


def _failed_attempt(application_id, lease_id, reason):
    with get_connection() as connection:
        source = _source(connection, application_id)
        application = source[0]
        if application.get("ml_classification_lease_id") != lease_id:
            return _state(application, "superseded")
        return _pending(connection, application, [reason])


def _reuse_assessment(connection, application, inputs, identity, input_hash):
    """Revalidate an immutable result only after fresh source/model checks.

    Pending states still clear the current suggestion. Recovery does not turn
    another observation of identical content into another model inference.
    Called under the application row lock, with no active inference lease.
    """
    previous = connection.execute(
        """SELECT * FROM classification_assessments
           WHERE application_id = %s AND input_sha256 = %s
           ORDER BY classified_at DESC, id DESC LIMIT 1;""",
        (application["id"], input_hash),
    ).fetchone()
    if previous is None:
        return None
    evidence = previous.get("source_evidence") or {}
    if not isinstance(evidence, dict) or previous.get("inputs") != inputs.payload:
        return None
    try:
        result = ModelResult.model_validate({
            "analysis_type": "data-sensitivity-classification",
            **{key: previous.get(key) for key in (
                "suggested_classification", "confidence", "review_required",
                "review_threshold", "model_version", "class_probabilities", "authority",
            )},
            "model_sha256": evidence.get("model_sha256"),
        })
    except (ValidationError, TypeError, ValueError):
        return None
    if (result.model_version != identity.classification_model_version
            or result.model_sha256 != identity.classification_model_sha256
            or result.review_threshold != identity.classification_review_threshold
            or previous.get("classified_at") is None
            or previous["classified_at"] > application["classification_now"]):
        return None
    review_reasons = list(inputs.review_reasons)
    if result.confidence < result.review_threshold:
        review_reasons.append("model_confidence_below_review_threshold")
    if result.suggested_classification in {"confidential", "restricted"}:
        review_reasons.append("high_sensitivity_requires_human_review")
    review_required = result.review_required or bool(review_reasons)
    provenance = {
        **inputs.provenance,
        "model_sha256": result.model_sha256,
        "review_threshold": result.review_threshold,
        "review_reasons": review_reasons,
        "reused_assessment_id": str(previous["id"]),
        "inference_observation_id": evidence.get("observation_id"),
        "revalidated_at": application["classification_now"].isoformat(),
    }
    updated = connection.execute(
        """UPDATE applications SET governance_status = 'stale', governance_outcome = NULL,
               governance_decided_at = NULL, ml_classification_status = 'assessed',
           ml_suggested_classification = %s, ml_classification_confidence = %s,
           ml_classification_review_required = %s, ml_classification_model_version = %s,
           ml_classified_at = %s, ml_classification_input_sha256 = %s,
           ml_classification_provenance = %s, ml_classification_pending_reasons = '[]'::jsonb,
           ml_classification_lease_id = NULL, ml_classification_lease_until = NULL,
           updated_at = NOW() WHERE id = %s RETURNING *;""",
        (result.suggested_classification, result.confidence, review_required,
         result.model_version, previous["classified_at"], input_hash, Jsonb(provenance),
         application["id"]),
    ).fetchone()
    return {**_state(updated, "revalidated"), "assessment_id": previous["id"]}


def classify_if_needed(application_id):
    # First establish eligibility without depending on ML availability.
    with get_connection() as connection:
        source = _source(connection, application_id)
        try:
            _inputs(source)
        except InputsPending as exc:
            return _pending(connection, source[0], exc.reasons)

    # Network requests never hold a database row lock or transaction open.
    try:
        health = httpx.get(f"{ML_ANALYTICS_URL}/health", timeout=5, follow_redirects=False)
        health.raise_for_status()
        identity = ModelIdentity.model_validate(health.json())
    except (httpx.HTTPError, ValueError, TypeError):
        with get_connection() as connection:
            source = _source(connection, application_id)
            try:
                _inputs(source)
            except InputsPending as exc:
                return _pending(connection, source[0], exc.reasons)
            # An active attempt owns its completion; a concurrent health failure
            # must not erase its lease or persist a competing outcome.
            application = source[0]
            until = application.get("ml_classification_lease_until")
            if until and until > application["classification_now"]:
                return _state(application, "in_progress")
            return _pending(connection, application, ["ml_identity_unavailable"])

    with get_connection() as connection:
        source = _source(connection, application_id)
        application = source[0]
        try:
            inputs = _inputs(source)
        except InputsPending as exc:
            return _pending(connection, application, exc.reasons)
        input_hash = _key(inputs, identity)
        if application["ml_classification_status"] == "assessed" and application.get("ml_classification_input_sha256") == input_hash:
            return _state(application)
        until = application.get("ml_classification_lease_until")
        if until and until > application["classification_now"]:
            return _state(application, "in_progress")
        reused = _reuse_assessment(connection, application, inputs, identity, input_hash)
        if reused is not None:
            return reused
        lease_id = uuid4()
        connection.execute(
            """UPDATE applications SET governance_status = 'stale', governance_outcome = NULL,
               governance_decided_at = NULL, ml_classification_status = 'assessing',
               ml_suggested_classification = NULL, ml_classification_confidence = NULL,
               ml_classification_review_required = NULL, ml_classification_model_version = NULL,
               ml_classified_at = NULL, ml_classification_input_sha256 = NULL,
               ml_classification_provenance = NULL, ml_classification_pending_reasons = '[]'::jsonb,
               ml_classification_lease_id = %s,
               ml_classification_lease_until = clock_timestamp() + INTERVAL '90 seconds',
               updated_at = NOW() WHERE id = %s;""", (lease_id, application_id),
        )

    try:
        response = httpx.post(f"{ML_ANALYTICS_URL}/classify", json=inputs.payload, timeout=10, follow_redirects=False)
        response.raise_for_status()
        result = ModelResult.model_validate(response.json())
        if (result.model_version != identity.classification_model_version
                or result.model_sha256 != identity.classification_model_sha256
                or result.review_threshold != identity.classification_review_threshold):
            return _failed_attempt(application_id, lease_id, "ml_model_changed_during_inference")
    except (httpx.ConnectError, httpx.TimeoutException):
        return _failed_attempt(application_id, lease_id, "ml_unavailable")
    except (httpx.HTTPError, ValueError, TypeError):
        return _failed_attempt(application_id, lease_id, "ml_response_invalid")

    with get_connection() as connection:
        source = _source(connection, application_id)
        application = source[0]
        if application.get("ml_classification_lease_id") != lease_id:
            return _state(application, "superseded")
        try:
            current_inputs = _inputs(source)
        except InputsPending as exc:
            return _pending(connection, application, exc.reasons)
        if _key(current_inputs, identity) != input_hash:
            return _pending(connection, application, ["source_changed_during_inference"])
        if application["ml_classification_lease_until"] <= application["classification_now"]:
            return _pending(connection, application, ["inference_lease_expired"])
        review_reasons = list(inputs.review_reasons)
        if result.confidence < result.review_threshold:
            review_reasons.append("model_confidence_below_review_threshold")
        if result.suggested_classification in {"confidential", "restricted"}:
            review_reasons.append("high_sensitivity_requires_human_review")
        review_required = result.review_required or bool(review_reasons)
        provenance = {**current_inputs.provenance, "model_sha256": result.model_sha256,
                      "review_threshold": result.review_threshold, "review_reasons": review_reasons}
        assessment_id = uuid4()
        connection.execute(
            """INSERT INTO classification_assessments
               (id, application_id, suggested_classification, confidence, review_required,
                review_threshold, model_version, class_probabilities, inputs, authority,
                input_sha256, source_evidence)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);""",
            (assessment_id, application_id, result.suggested_classification, result.confidence,
             review_required, result.review_threshold, result.model_version,
             Jsonb(result.class_probabilities), Jsonb(inputs.payload), "advisory", input_hash, Jsonb(provenance)),
        )
        updated = connection.execute(
            """UPDATE applications SET governance_status = 'stale', governance_outcome = NULL,
               governance_decided_at = NULL, ml_classification_status = 'assessed',
               ml_suggested_classification = %s, ml_classification_confidence = %s,
               ml_classification_review_required = %s, ml_classification_model_version = %s,
               ml_classified_at = NOW(), ml_classification_input_sha256 = %s,
               ml_classification_provenance = %s, ml_classification_pending_reasons = '[]'::jsonb,
               ml_classification_lease_id = NULL, ml_classification_lease_until = NULL,
               updated_at = NOW() WHERE id = %s RETURNING *;""",
            (result.suggested_classification, result.confidence, review_required,
             result.model_version, input_hash, Jsonb(provenance), application_id),
        ).fetchone()
    return {**_state(updated, "assessed"), "assessment_id": assessment_id}


def classification_state(application_id):
    """Read-only, freshness-aware view; retained history is not current evidence."""
    with get_connection() as connection:
        source = _source(connection, application_id)
        state = _state(source[0], "status")
        try:
            inputs = _inputs(source)
        except InputsPending as exc:
            state.update(ml_classification_status="pending", suggested_classification=None,
                         confidence=None, review_required=None, pending_reasons=exc.reasons,
                         classified_at=None, model_version=None, provenance=None)
            return state
        application = source[0]
        if application["ml_classification_status"] == "assessed":
            try:
                identity = ModelIdentity(
                    classification_model_version=application.get("ml_classification_model_version"),
                    classification_model_sha256=(application.get("ml_classification_provenance") or {}).get("model_sha256"),
                    classification_review_threshold=(application.get("ml_classification_provenance") or {}).get("review_threshold"),
                )
                current = application.get("ml_classification_input_sha256") == _key(inputs, identity)
            except ValidationError:
                current = False
            if not current:
                state.update(ml_classification_status="stale", suggested_classification=None,
                             confidence=None, review_required=None,
                             pending_reasons=["classification_evidence_changed"],
                             classified_at=None, model_version=None, provenance=None)
        until = application.get("ml_classification_lease_until")
        if application["ml_classification_status"] == "assessing" and (not until or until <= application["classification_now"]):
            state.update(ml_classification_status="pending", pending_reasons=["inference_lease_expired"])
        return state
