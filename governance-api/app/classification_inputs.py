"""Build model inputs from owner attestations and sanitized live observations."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError

from .discovery_observation import AppsmithObservation
from .feature_assembly import observation_fingerprint
from .owner_context import OwnerContextRequest


OBSERVATION_MAX_AGE_SECONDS = 180
INPUT_CONTRACT_VERSION = "classification-evidence-v1"


class InputsPending(Exception):
    def __init__(self, *reasons):
        self.reasons = list(reasons)
        super().__init__(", ".join(reasons))


@dataclass(frozen=True)
class ClassificationInputs:
    payload: dict
    semantic_hash: str
    provenance: dict
    review_reasons: list[str]


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_classification_inputs(application, context, observation_row, now=None):
    now = now or datetime.now(timezone.utc)
    if application.get("platform") != "appsmith":
        raise InputsPending("platform_outside_appsmith_scope")
    if context is None:
        raise InputsPending("owner_attestation_required")
    if context["application_id"] != application["id"] or context["id"] != application.get("owner_context_id"):
        raise InputsPending("owner_context_identity_mismatch")
    if observation_row is None:
        raise InputsPending("appsmith_observation_required")
    try:
        declared = OwnerContextRequest.model_validate(context["payload"])
        observation = AppsmithObservation.model_validate(observation_row["payload"])
    except (ValidationError, TypeError, KeyError):
        raise InputsPending("invalid_source_evidence") from None
    if observation.external_id != application["external_id"] or observation_row["application_id"] != application["id"]:
        raise InputsPending("observation_identity_mismatch")
    if observation_row["observed_at"] != observation.observed_at:
        raise InputsPending("observation_timestamp_mismatch")
    age = (now - observation.observed_at).total_seconds()
    if age < -30:
        raise InputsPending("observation_timestamp_in_future")
    if age > OBSERVATION_MAX_AGE_SECONDS:
        raise InputsPending("appsmith_observation_stale")

    fields = sorted(declared.data_fields, key=lambda field: field.name.casefold())
    field_text = "; ".join(
        f"{field.name}: {field.description}" for field in fields
    )
    review_reasons = []
    field_evidence = observation.data_field_evidence
    observed_fields = sorted(field_evidence.field_identifiers) if field_evidence else []
    # Provenance labels belong in source_evidence, not the trained model's text.
    # Adding labels such as "Owner-declared" changed a challenge prediction.
    declared_names = {field.name.casefold() for field in fields}
    extra_observed = [name for name in observed_fields if name.casefold() not in declared_names]
    if extra_observed:
        field_text = "; ".join(filter(None, [field_text, ", ".join(extra_observed)]))
    if not field_text:
        field_text = "No data fields declared; no widget fields observed."
    if field_evidence is None or field_evidence.coverage == "uncollected":
        review_reasons.append("widget_field_evidence_unavailable")
    elif field_evidence.dynamic_bindings_detected:
        review_reasons.append("dynamic_field_bindings_require_owner_review")
    if declared.field_scope == "no_data_fields" and observed_fields:
        review_reasons.append("owner_declaration_conflicts_with_observed_fields")
    if fields and any(name.casefold() not in {field.name.casefold() for field in fields} for name in observed_fields):
        review_reasons.append("observed_fields_outside_declared_schema")
    if not observation.collection_complete:
        review_reasons.append("connector_collection_partial")

    destinations = sorted({
        f"{item.destination.scheme}://{item.destination.host}"
        + (f":{item.destination.port}" if item.destination.port else "")
        for item in [*observation.connectors, *observation.observed_actions]
        if item.destination is not None
    })
    unresolved = any(
        item.destination_state != "observed"
        for item in [*observation.connectors, *observation.observed_actions]
    )
    if unresolved:
        review_reasons.append("integration_destinations_unresolved")
    if destinations:
        connector_text = "; ".join(destinations)
    elif observation.collection_complete and not observation.connectors and not observation.observed_actions:
        connector_text = "Complete Appsmith collection observed no configured connectors or actions."
    else:
        connector_text = "Appsmith integration evidence is incomplete; destinations are unresolved."
    if not observation.connectors and observation.observed_actions:
        review_reasons.append("action_destinations_without_connector_identity")
    payload = {
        "application_name": application["name"],
        "business_purpose": declared.business_purpose,
        "data_fields": field_text,
        "connector_metadata": connector_text,
    }
    semantic = {
        "contract": INPUT_CONTRACT_VERSION,
        "application_id": str(application["id"]),
        "external_id": application["external_id"],
        "owner_context_id": str(context["id"]),
        "payload": payload,
        "observation_fingerprint": observation_fingerprint(observation),
        "field_evidence": field_evidence.model_dump(mode="json") if field_evidence else None,
        "review_reasons": review_reasons,
    }
    provenance = {
        "contract_version": INPUT_CONTRACT_VERSION,
        "owner_context_id": str(context["id"]),
        "owner_subject_id": context["subject_id"],
        "owner_declared_at": context["declared_at"].isoformat(),
        "owner_identity_source": "operator_issued_application_credential",
        "declared_fields": [field.model_dump() for field in fields],
        "observed_widget_fields": observed_fields,
        "observed_destinations": destinations,
        "observation_id": str(observation_row["id"]),
        "observed_at": observation.observed_at.isoformat(),
        "collector_version": observation.collector_version,
        "field_scope": declared.field_scope,
        "observed_field_coverage": field_evidence.coverage if field_evidence else "uncollected",
        "collection_complete": observation.collection_complete,
        "review_reasons": review_reasons,
        "authority": "advisory",
    }
    return ClassificationInputs(payload, digest(semantic), provenance, review_reasons)
