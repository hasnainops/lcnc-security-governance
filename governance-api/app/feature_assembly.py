"""Deterministic LO1 feature assembly from verified evidence."""

import hashlib
import json

from .discovery_observation import AppsmithObservation


FEATURE_NAMES = (
    "external_integration_count",
    "unapproved_integration_count",
    "connector_count",
    "external_domain_count",
    "changes_last_24h",
)

TRUST_STATES = {
    "approved_external",
    "unapproved_external",
    "internal",
}



def derive_connector_provenance(observation: AppsmithObservation):
    """Describe collected Appsmith integration evidence.

    This does not establish that an HTTP origin is a logical
    connector, nor does it grant integration approval.
    """

    connector_count = len(observation.connectors)
    action_count = len(observation.observed_actions)

    if observation.collection_complete:
        if connector_count == 0 and action_count == 0:
            evidence_status = "verified_absent"
        elif connector_count > 0:
            evidence_status = "verified_present"
        else:
            evidence_status = "verified_partial"

    elif (
        "connector_identity_unresolved"
        in observation.pending_reasons
    ):
        evidence_status = "verified_partial"

    else:
        evidence_status = "uncollected"

    return {
        "status": evidence_status,
        "scope": "observed_appsmith_integrations",
        "verified_connector_count": connector_count,
        "observed_action_count": action_count,
        "collection_complete": observation.collection_complete,
        "pending_reasons": sorted(
            observation.pending_reasons
        ),
    }


def observation_fingerprint(observation: AppsmithObservation):
    """Fingerprint semantic connector/action evidence, not polling time."""

    document = observation.model_dump(mode="json")

    content = {
        "source": document["source"],
        "external_id": document["external_id"],
        "page_ids": sorted(document["page_ids"]),
        "collection_complete": document["collection_complete"],
        "pending_reasons": sorted(document["pending_reasons"]),
        "connectors": sorted(
            document["connectors"],
            key=lambda item: item["connector_id"],
        ),
        "observed_actions": sorted(
            document["observed_actions"],
            key=lambda item: item["action_id"],
        ),
    }

    encoded = json.dumps(
        content, sort_keys=True, separators=(",", ":")
    )

    return hashlib.sha256(encoded.encode()).hexdigest()



def verified_changes_from_history(observations, end_at):
    """Count observed structural transitions over a verified 24h window.

    Requires an observation at the window boundary and continuous
    collection. An unverified window returns None, not zero.
    """
    from datetime import timedelta

    window_start = end_at - timedelta(hours=24)
    max_gap = timedelta(minutes=3)

    if not observations:
        return None

    ordered = sorted(
        observations,
        key=lambda item: item.observed_at,
    )

    timestamps = [item.observed_at for item in ordered]

    if len(timestamps) != len(set(timestamps)):
        return None

    baseline_index = None

    for index, observation in enumerate(ordered):
        if observation.observed_at <= window_start:
            baseline_index = index
        else:
            break

    if baseline_index is None:
        return None

    window = [
        item
        for item in ordered[baseline_index:]
        if item.observed_at <= end_at
    ]

    if not window:
        return None

    if window_start - window[0].observed_at > max_gap:
        return None

    if end_at - window[-1].observed_at > max_gap:
        return None

    for item in window:
        if not item.collection_complete:
            return None

        # Old observations without page IDs cannot establish
        # comparable evidence under the expanded fingerprint.
        if "page_ids" not in item.model_fields_set:
            return None

    for previous, current in zip(window, window[1:]):
        if current.observed_at - previous.observed_at > max_gap:
            return None

    changes = 0

    for previous, current in zip(window, window[1:]):
        if current.observed_at <= window_start:
            continue

        if (
            observation_fingerprint(previous)
            != observation_fingerprint(current)
        ):
            changes += 1

    return changes



def cold_start_witnessed_evidence(observations):
    """Qualify witnessed structural changes, never certify 24h coverage."""

    from datetime import timedelta

    if not observations:
        return None

    ordered = sorted(
        observations,
        key=lambda item: item.observed_at,
    )

    if len({
        item.observed_at for item in ordered
    }) != len(ordered):
        return None

    latest = ordered[-1]
    identity = (latest.source, latest.external_id)

    def compatible(item):
        return (
            item.collection_complete is True
            and "page_ids" in item.model_fields_set
            and (item.source, item.external_id) == identity
        )

    if not compatible(latest):
        return None

    # Use only the latest uninterrupted segment.
    # Never infer changes across a sleeping/offline period.
    segment = [latest]

    for previous in reversed(ordered[:-1]):
        if (
            latest.observed_at - previous.observed_at
            > timedelta(hours=24)
        ):
            break

        if not compatible(previous):
            break

        gap = segment[0].observed_at - previous.observed_at

        if gap > timedelta(minutes=3):
            break

        segment.insert(0, previous)

    if len(segment) < 2:
        return None

    changes = sum(
        observation_fingerprint(before)
        != observation_fingerprint(after)
        for before, after in zip(
            segment,
            segment[1:],
        )
    )

    if changes == 0:
        return None

    return {
        "assessment_tier": "cold_start_witnessed",
        "witnessed_changes": changes,
        "observation_window_seconds": (
            segment[-1].observed_at
            - segment[0].observed_at
        ).total_seconds(),
        "first_observed_at": (
            segment[0].observed_at.isoformat()
        ),
        "last_observed_at": (
            segment[-1].observed_at.isoformat()
        ),
        "observation_fingerprint": (
            observation_fingerprint(segment[-1])
        ),
        "certified_24h": False,
    }


def assemble_features(
    observation: AppsmithObservation,
    *,
    destination_trust=None,
    verified_changes_24h=None,
):
    """Assemble features from evidence already verified server-side.

    destination_trust must come from Governance policy evaluation,
    not from the Discovery client.

    verified_changes_24h requires independently verified historical
    coverage and must not represent polling-cycle counts.
    """

    values = {name: None for name in FEATURE_NAMES}

    # An empty connector list is not proof of zero integrations
    # when action evidence exists without connector identities.
    if (
        observation.collection_complete
        and (observation.connectors or not observation.observed_actions)
    ):
        connectors = observation.connectors
        values["connector_count"] = len(connectors)

        # An exhaustive empty connector collection proves zero.
        if not connectors:
            values["external_integration_count"] = 0
            values["unapproved_integration_count"] = 0
            values["external_domain_count"] = 0

        elif destination_trust is not None:
            identities = {c.connector_id for c in connectors}

            if (
                set(destination_trust) == identities
                and all(
                    c.destination_state == "observed"
                    for c in connectors
                )
                and all(
                    state in TRUST_STATES
                    for state in destination_trust.values()
                )
            ):
                external = [
                    c for c in connectors
                    if destination_trust[c.connector_id]
                    in {"approved_external", "unapproved_external"}
                ]

                values["external_integration_count"] = len(external)
                values["unapproved_integration_count"] = sum(
                    destination_trust[c.connector_id]
                    == "unapproved_external"
                    for c in external
                )
                values["external_domain_count"] = len({
                    c.destination.host for c in external
                })

    if verified_changes_24h is not None:
        if (
            type(verified_changes_24h) is not int
            or verified_changes_24h < 0
        ):
            raise ValueError("Invalid verified change count")

        values["changes_last_24h"] = verified_changes_24h

    missing = [
        name for name, value in values.items()
        if value is None
    ]

    return {
        "features": values,
        "ready_for_ml": not missing,
        "missing_features": missing,
        "observation_fingerprint": observation_fingerprint(
            observation
        ),
    }
