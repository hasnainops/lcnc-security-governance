import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app import appsmith_publish as gate


def reviewed_case():
    app_id = uuid4()
    decision_id = uuid4()
    decided_at = datetime.now(timezone.utc)

    application = {
        "id": app_id,
        "risk_level": "low",
        "governance_status": "pending_review",
        "governance_outcome": "SECURITY_REVIEW",
        "governance_decided_at": decided_at,
        "ml_classification_review_required": True,
        "ml_classification_status": "assessed",
        "ml_anomaly_status": "assessed",
        "ml_anomalous": False,
    }

    policy = {"allowed": True, "reasons": []}
    outcome = gate.determine_outcome(
        {"level": "low"}, policy, application
    )

    evidence = {
        "authority": "deterministic_governance",
        "manifest_version": "appsmith-release-manifest-v1",
        "release_sha256": "a" * 64,
    }

    binding = {
        "version": "automatic-governance-v2",
        "manifest_version": evidence["manifest_version"],
        "release_sha256": evidence["release_sha256"],
        "application_id": str(app_id),
        "application": {
            key: application.get(key)
            for key in gate.INPUT_FIELDS
        },
        "policy": policy,
        "outcome": outcome,
    }

    decision = {
        "id": decision_id,
        "outcome": "SECURITY_REVIEW",
        "status": "pending_review",
        "created_at": decided_at,
        "source_evidence": evidence,
        "input_sha256": hashlib.sha256(
            json.dumps(
                binding, sort_keys=True, default=str
            ).encode()
        ).hexdigest(),
    }

    review = {
        "application_id": app_id,
        "governance_decision_id": decision_id,
        "route_type": "security_review",
        "required_role": "Security/GRC Reviewer",
        "governance_outcome": "SECURITY_REVIEW",
        "status": "approved",
        "human_decision": "approve",
        "decided_by": "verified-test-reviewer",
        "decision_reason": "Classification advisory reviewed",
        "decided_at": decided_at,
    }

    return application, decision, policy, review


def test_valid_reviewed_release_matches_exact_decision():
    app, decision, policy, review = reviewed_case()

    assert gate.reviewed_approval_matches(
        app, decision, policy, review
    ) is True


@pytest.mark.parametrize("field,value", [
    ("status", "pending"),
    ("human_decision", "reject"),
    ("required_role", "Business Application Owner"),
    ("governance_decision_id", "wrong-decision"),
    ("application_id", "wrong-application"),
    ("decided_by", " "),
    ("decision_reason", " "),
    ("decided_at", None),
])
def test_invalid_review_is_rejected(field, value):
    app, decision, policy, review = reviewed_case()
    review[field] = value

    assert gate.reviewed_approval_matches(
        app, decision, policy, review
    ) is False


def test_edited_release_invalidates_review():
    app, decision, policy, review = reviewed_case()

    decision["source_evidence"]["release_sha256"] = "b" * 64

    assert gate.reviewed_approval_matches(
        app, decision, policy, review
    ) is False


def test_hard_policy_block_cannot_be_overridden():
    app, decision, policy, review = reviewed_case()
    policy["allowed"] = False

    assert gate.reviewed_approval_matches(
        app, decision, policy, review
    ) is False


def test_missing_human_approval_is_rejected():
    app, decision, policy, _ = reviewed_case()

    assert gate.reviewed_approval_matches(
        app, decision, policy, None
    ) is False


def test_nonclassification_review_is_rejected():
    app, decision, policy, review = reviewed_case()
    app["ml_classification_review_required"] = False

    assert gate.reviewed_approval_matches(
        app, decision, policy, review
    ) is False


@pytest.mark.parametrize("authority,expected", [
    ("lcnc-senior-security-reviewer", True),
    ("lcnc-security-reviewer", False),
    (None, False),
    ("untrusted-policy", False),
])
def test_senior_review_requires_verified_authority(authority, expected):
    app, decision, policy, review = reviewed_case()
    review["required_role"] = "Senior Security/GRC Reviewer"
    review["verified_reviewer_policy"] = authority

    assert gate.reviewed_approval_matches(
        app, decision, policy, review
    ) is expected


def test_senior_review_cannot_override_hard_policy():
    app, decision, policy, review = reviewed_case()
    review["required_role"] = "Senior Security/GRC Reviewer"
    review["verified_reviewer_policy"] = "lcnc-senior-security-reviewer"
    policy["allowed"] = False

    assert not gate.reviewed_approval_matches(
        app, decision, policy, review
    )


def test_edited_release_invalidates_senior_review():
    app, decision, policy, review = reviewed_case()
    review["required_role"] = "Senior Security/GRC Reviewer"
    review["verified_reviewer_policy"] = "lcnc-senior-security-reviewer"
    decision["source_evidence"]["release_sha256"] = "b" * 64

    assert not gate.reviewed_approval_matches(
        app, decision, policy, review
    )


from app import automatic_governance as writer


def writer_binding_case():
    app, decision, policy, review = reviewed_case()

    app["external_id"] = "6affb740b82ed4d1f79df9fb"

    source = {
        "id": uuid4(),
        "observed_at": datetime.now(timezone.utc),
        "payload": {
            "external_id": app["external_id"],
            "collection_complete": True,
            "pending_reasons": [],
            "manifest_version": "appsmith-release-manifest-v1",
            "release_sha256": "a" * 64,
        },
    }

    outcome = gate.determine_outcome(
        {"level": "low"}, policy, app
    )

    return app, decision, policy, review, source, outcome


def test_automatic_writer_matches_publish_verifier():
    app, decision, policy, review, source, outcome = (
        writer_binding_case()
    )

    digest, evidence = writer.build_decision_binding(
        app, source, policy, outcome
    )

    decision["input_sha256"] = digest
    decision["source_evidence"] = evidence

    assert evidence["release_sha256"] == "a" * 64

    assert gate.reviewed_approval_matches(
        app, decision, policy, review
    )


def test_automatic_writer_changes_digest_for_modified_release():
    app, decision, policy, review, source, outcome = (
        writer_binding_case()
    )

    digest_a, evidence_a = writer.build_decision_binding(
        app, source, policy, outcome
    )

    source["payload"]["release_sha256"] = "b" * 64

    digest_b, evidence_b = writer.build_decision_binding(
        app, source, policy, outcome
    )

    assert digest_a != digest_b
    assert evidence_a["release_sha256"] == "a" * 64
    assert evidence_b["release_sha256"] == "b" * 64


def test_unchanged_release_keeps_same_governance_digest():
    app, decision, policy, review, source, outcome = (
        writer_binding_case()
    )

    digest_a, _ = writer.build_decision_binding(
        app, source, policy, outcome
    )

    source["id"] = uuid4()
    source["observed_at"] = datetime.now(timezone.utc)

    digest_b, _ = writer.build_decision_binding(
        app, source, policy, outcome
    )

    assert digest_a == digest_b


@pytest.mark.parametrize("field,value", [
    ("release_sha256", None),
    ("release_sha256", "invalid"),
    ("release_sha256", "A" * 64),
    ("manifest_version", "unknown-version"),
    ("external_id", "different-application"),
    ("collection_complete", False),
    ("pending_reasons", ["unresolved_evidence"]),
])
def test_unverified_release_cannot_create_publish_binding(field, value):
    app, decision, policy, review, source, outcome = (
        writer_binding_case()
    )

    source["payload"][field] = value

    digest, evidence = writer.build_decision_binding(
        app, source, policy, outcome
    )

    assert "release_sha256" not in evidence
    assert "manifest_version" not in evidence

    decision["input_sha256"] = digest
    decision["source_evidence"] = evidence

    assert not gate.reviewed_approval_matches(
        app, decision, policy, review
    )


def test_release_binding_cannot_be_reused_for_another_application():
    app, decision, policy, review, source, outcome = (
        writer_binding_case()
    )

    digest_a, _ = writer.build_decision_binding(
        app, source, policy, outcome
    )

    app["id"] = uuid4()

    digest_b, _ = writer.build_decision_binding(
        app, source, policy, outcome
    )

    assert digest_a != digest_b
