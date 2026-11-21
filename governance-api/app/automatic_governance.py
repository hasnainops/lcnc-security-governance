"""Scheduled governance with atomic decisions and retryable downstream delivery."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .database import get_connection
from .assessment import assess_and_persist
from .policy import evaluate_and_persist
from .workflow import determine_outcome, SECURITY_GRC_REVIEWER_ROLE
from .approval_automation import route_governance_approval
from .training import assign_required_training

# Values that affect decisions; poll timestamps and inferred assessment IDs are
# deliberately excluded. Changed model identity and owner attestations are inputs.
INPUT_FIELDS = (
    'name', 'registration_status', 'owner_name', 'owner_context_id',
    'business_purpose', 'data_fields', 'data_classification', 'internet_exposed',
    'external_integration', 'integration_approved', 'credential_type',
    'connector_count', 'external_integration_count', 'unapproved_integration_count',
    'external_domain_count', 'changes_last_24h',
    'ml_anomaly_status', 'ml_anomalous', 'ml_model_version',
    'ml_classification_status', 'ml_classification_input_sha256',
    'ml_suggested_classification', 'ml_classification_confidence',
    'ml_classification_review_required', 'ml_classification_model_version',
    'security_scan_status', 'security_scan_passed', 'security_finding_count',
    'security_highest_severity', 'security_scanner_version',
    'risk_score', 'risk_level', 'risk_model_version',
)


def review_reasons(app, source):
    reasons = []
    if source['payload'].get('collection_complete') is not True:
        reasons.append('Discovery evidence is incomplete.')
    if app.get('ml_classification_status') != 'assessed':
        reasons.append('Current classification assessment is unavailable.')
    if app.get('data_classification') in (None, 'unknown'):
        reasons.append('Authoritative data classification requires review.')
    if app.get('ml_anomaly_status') != 'assessed':
        reasons.append('Current AI configuration/anomaly assessment is unavailable.')
    if app.get('security_scan_status') != 'scanned' or app.get('security_scan_passed') is not True:
        reasons.append('Security scanning is incomplete or has unresolved findings.')
    return reasons



def build_decision_binding(app, source, policy, outcome):
    """Bind governance decisions to verified native release evidence."""

    payload = source.get("payload") or {}

    evidence = {
        "observation_id": str(source["id"]),
        "observed_at": source["observed_at"].isoformat(),
        "owner_context_id": (
            str(app["owner_context_id"])
            if app.get("owner_context_id") else None
        ),
        "classification_input_sha256": (
            app.get("ml_classification_input_sha256")
        ),
        "authority": "deterministic_governance",
    }

    binding = {
        "version": "automatic-governance-v1",
        "application": {
            k: app.get(k) for k in INPUT_FIELDS
        },
        "policy": policy,
        "outcome": outcome,
    }

    native_id = app.get("external_id")
    manifest = payload.get("manifest_version")
    release_digest = payload.get("release_sha256")

    release_verified = (
        isinstance(native_id, str)
        and bool(native_id)
        and payload.get("external_id") == native_id
        and payload.get("collection_complete") is True
        and not payload.get("pending_reasons")
        and manifest == "appsmith-release-manifest-v1"
        and isinstance(release_digest, str)
        and len(release_digest) == 64
        and all(c in "0123456789abcdef" for c in release_digest)
    )

    if release_verified:

        evidence.update({
            "manifest_version": manifest,
            "release_sha256": release_digest,
        })

        binding.update({
            "version": "automatic-governance-v2",
            "manifest_version": manifest,
            "release_sha256": release_digest,
            "application_id": str(app["id"]),
        })

    # Legacy discovery can still support inventory governance.
    # Only v2 decisions can satisfy native publication binding.

    digest = hashlib.sha256(
        json.dumps(
            binding, sort_keys=True, default=str
        ).encode()
    ).hexdigest()

    return digest, evidence


def evaluate_governance_if_needed(application_id):
    with get_connection() as connection:
        # Shared row lock serializes replicas and owner/source updates. Risk and
        # policy persistence use this same transaction; no nested connection locks.
        app = connection.execute('SELECT * FROM applications WHERE id=%s FOR UPDATE',
                                 (application_id,)).fetchone()
        if app is None:
            raise HTTPException(404, 'Application not found')
        if app['platform'].lower() != 'appsmith':
            return {'action': 'skipped', 'reason': 'automatic_handoff_scoped_to_appsmith'}
        source = connection.execute('''SELECT id, observed_at, payload FROM discovery_observations
            WHERE application_id=%s AND source='appsmith'
            ORDER BY observed_at DESC, received_at DESC LIMIT 1''', (application_id,)).fetchone()
        now = datetime.now(timezone.utc)
        if source is None or not now-timedelta(minutes=3) <= source['observed_at'] <= now:
            connection.execute("""UPDATE applications SET governance_status='stale',
                governance_outcome=NULL, governance_decided_at=NULL WHERE id=%s""", (application_id,))
            return {'action': 'pending', 'reason': 'fresh_observation_required'}

        risk = connection.execute('''SELECT * FROM risk_assessments WHERE application_id=%s
            ORDER BY assessed_at DESC LIMIT 1''', (application_id,)).fetchone()
        if app.get('risk_status') != 'assessed' or risk is None:
            assess_and_persist(application_id, connection=connection)
            app = connection.execute('SELECT * FROM applications WHERE id=%s', (application_id,)).fetchone()
            risk = connection.execute('''SELECT * FROM risk_assessments WHERE application_id=%s
                ORDER BY assessed_at DESC LIMIT 1''', (application_id,)).fetchone()
        # OPA is consulted each cycle, including policy-only changes. An outage
        # raises and rolls back, and cannot generate an approval.
        policy = evaluate_and_persist(application_id, connection=connection, persist=False)
        outcome = determine_outcome({'level': risk['level']}, policy, app)
        incomplete = review_reasons(app, source)
        if policy['allowed'] and incomplete:
            outcome = {'outcome': 'SECURITY_REVIEW', 'status': 'pending_review',
                       'required_role': SECURITY_GRC_REVIEWER_ROLE,
                       'reasons': list(dict.fromkeys(incomplete + (
                           outcome['reasons'] if outcome['outcome'] == 'SECURITY_REVIEW' else [])))}
        if datetime.now(timezone.utc)-source['observed_at'] > timedelta(minutes=3):
            raise HTTPException(409, 'Discovery evidence expired during evaluation')
        digest, source_evidence = build_decision_binding(
            app, source, policy, outcome
        )
        previous = connection.execute('''SELECT * FROM governance_decisions WHERE application_id=%s
            ORDER BY created_at DESC, id DESC LIMIT 1''', (application_id,)).fetchone()
        if previous and previous.get('input_sha256') == digest:
            decision_id = previous['id']
            action = 'reused'
            decided_at = previous['created_at']
        else:
            policy_id, decision_id = uuid4(), uuid4()
            connection.execute('''INSERT INTO policy_decisions
                (id,application_id,action,allowed,reasons,policy_version)
                VALUES (%s,%s,%s,%s,%s,%s)''', (policy_id, application_id,
                policy['action'], policy['allowed'], Jsonb(policy['reasons']), policy['policy_version']))
            row = connection.execute('''INSERT INTO governance_decisions
                (id,application_id,risk_assessment_id,policy_decision_id,outcome,status,
                 required_role,reasons,input_sha256,source_evidence)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING created_at''',
                (decision_id, application_id, risk['id'], policy_id, outcome['outcome'],
                 outcome['status'], outcome['required_role'], Jsonb(outcome['reasons']), digest,
                 Jsonb(source_evidence))).fetchone()
            decided_at, action = row['created_at'], 'evaluated'
        connection.execute('''UPDATE applications SET governance_status=%s,
            governance_outcome=%s, governance_decided_at=%s WHERE id=%s''',
            (outcome['status'], outcome['outcome'], decided_at, application_id))

    # Commit first: the approval service uses another connection. Retry even when
    # decision is reused, so downstream outages do not strand a decision.
    try:
        training = assign_required_training(application_id)
    except Exception:
        training = {'status': 'assignment_error'}
    if training.get('status') == 'assignment_error':
        # Do not expose an approvable request when required training could not
        # be established. The next cycle reuses the decision and retries.
        with get_connection() as connection:
            connection.execute("""UPDATE applications SET governance_status='stale'
                WHERE id=%s AND governance_decided_at=%s""", (application_id, decided_at))
        routing = {'status': 'pending', 'reason': 'training_assignment_failed'}
    else:
        routing = route_governance_approval(application_id)
    return {'action': action, 'decision_id': str(decision_id), 'governance': outcome,
            'approval_automation': routing, 'training_automation': training}
