"""Preflight for Appsmith's canonical manual publish endpoint.

This checks stored, observed configuration. It is NOT an atomic approval of the
live draft: changes between discovery and publish and other publish paths remain
outside this checkpoint. Appsmith still authenticates the forwarded request.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from psycopg.types.json import Jsonb

from .automatic_governance import INPUT_FIELDS
from .database import get_connection
from .policy import evaluate_and_persist
from .workflow import determine_outcome


router = APIRouter()
VERSION = "appsmith-publish-preflight-v1"
PUBLISH = re.compile(r"/api/v1/applications/publish/([0-9a-f]{24})")
MAX_AGE = timedelta(minutes=3)


def publish_target(method, uri, branch=""):
    """Reject ambiguous API paths before Caddy can forward them.

    The proxy sends these headers from the original request, overwriting client
    values. Missing headers fail closed. Query values are not policy inputs.
    """
    if not method or not uri or len(uri) > 16384 or not uri.startswith("/"):
        raise ValueError("invalid_request_target")
    path, _, query = uri.partition("?")
    # Appsmith's API paths use literal resource identifiers. Blocking unusual
    # encodings/segments avoids relying on differing proxy/Spring normalization.
    if ("%" in path or "\\" in path or ";" in path or "//" in path
            or any(p in (".", "..") for p in path.split("/"))
            or any(ord(c) < 32 for c in uri)):
        raise ValueError("noncanonical_request_target")
    # The pinned Appsmith implementation auto-publishes the default page on
    # create and publishes the copied pages on clone. Neither operation has
    # a target application ID that can pass this app-scoped preflight.
    # Reject them before forwarding; a separate native creation design is
    # required before these routes can be enabled behind this proxy.
    if method == "POST" and (path.lower() in (
            "/api/v1/applications", "/api/v1/applications/")
            or path.lower().startswith("/api/v1/applications/clone")):
        raise ValueError("unreviewed_auto_publish_route")
    if not path.lower().startswith("/api/v1/applications/publish"):
        return None
    match = PUBLISH.fullmatch(path)
    if not match or method != "POST" or query or branch:
        raise ValueError("unsupported_publish_request")
    return match[1]


def fresh(source, now):
    timestamp = (source or {}).get("observed_at")
    return isinstance(timestamp, datetime) and timestamp.tzinfo is not None and (
        now - MAX_AGE <= timestamp <= now
    )


def source_content(source):
    # Compare ALL stored observation fields, including widget evidence, rather
    # than treating matching connector counts as the same observation.
    payload = dict((source or {}).get("payload") or {})
    payload.pop("observed_at", None)
    for key, identity in (("page_ids", None), ("pending_reasons", None),
                          ("connectors", "connector_id"),
                          ("observed_actions", "action_id")):
        if key in payload:
            payload[key] = sorted(payload[key], key=(lambda x: x[identity]) if identity else None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def approval_matches(
    application, decision, policy,
    expected_outcome="AUTO_APPROVE",
    expected_status="completed",
):
    if not decision or not decision.get("input_sha256"):
        return False
    if (application.get("governance_status") != expected_status
            or application.get("governance_outcome") != expected_outcome
            or application.get("governance_decided_at") != decision.get("created_at")
            or decision.get("outcome") != expected_outcome
            or decision.get("status") != expected_status
            or (decision.get("source_evidence") or {}).get("authority") != "deterministic_governance"):
        return False
    if application.get("risk_level") != "low":
        return False
    outcome = determine_outcome({"level": application["risk_level"]}, policy, application)
    if (outcome.get("outcome") != expected_outcome
            or outcome.get("status") != expected_status):
        return False
    evidence = decision["source_evidence"]
    release_digest = evidence.get("release_sha256")
    if (evidence.get("manifest_version") != "appsmith-release-manifest-v1"
            or not isinstance(release_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", release_digest) is None):
        return False
    digest = hashlib.sha256(json.dumps({
        "version": "automatic-governance-v2",
        "manifest_version": evidence["manifest_version"],
        "release_sha256": release_digest,
        "application_id": str(application["id"]),
        "application": {k: application.get(k) for k in INPUT_FIELDS},
        "policy": policy, "outcome": outcome,
    }, sort_keys=True, default=str).encode()).hexdigest()
    return digest == decision["input_sha256"]


def reviewed_approval_matches(application, decision, policy, review):
    """Accept only an authorized classification-review resolution.

    The decision remains SECURITY_REVIEW in the audit record.
    Hard governance policy and release binding are never overridden.
    """
    if not review or not decision or policy.get("allowed") is not True:
        return False

    if not (
        application.get("ml_classification_review_required") is True
        and application.get("ml_anomaly_status") == "assessed"
        and application.get("ml_anomalous") is False
        and application.get("ml_classification_status") == "assessed"
        and review.get("status") == "approved"
        and review.get("human_decision") == "approve"
        and review.get("route_type") == "security_review"
        and (
            review.get("required_role") == "Security/GRC Reviewer"
            or (
                review.get("required_role") == "Senior Security/GRC Reviewer"
                and review.get("verified_reviewer_policy")
                    == "lcnc-senior-security-reviewer"
            )
        )
        and review.get("governance_outcome") == "SECURITY_REVIEW"
        and str(review.get("application_id")) == str(application.get("id"))
        and str(review.get("governance_decision_id")) == str(decision.get("id"))
        and isinstance(review.get("decided_by"), str)
        and bool(review["decided_by"].strip())
        and isinstance(review.get("decision_reason"), str)
        and bool(review["decision_reason"].strip())
        and review.get("decided_at") is not None
    ):
        return False

    return approval_matches(
        application, decision, policy,
        expected_outcome="SECURITY_REVIEW",
        expected_status="pending_review",
    )


def evaluate_publish_policy(facts):
    url = os.getenv("OPA_URL", "http://opa:8181").rstrip("/")
    response = httpx.post(url + "/v1/data/lcnc/appsmith_publish/decision",
                          json={"input": facts}, timeout=5.0, follow_redirects=False)
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise ValueError("missing_publish_policy")
    allowed, reasons = result.get("allow"), result.get("reasons")
    if (type(allowed) is not bool or result.get("action") != ("allow" if allowed else "deny")
            or result.get("version") != VERSION
            or not isinstance(reasons, list) or any(not isinstance(r, str) for r in reasons)
            or (allowed and reasons) or (not allowed and not reasons)):
        raise ValueError("invalid_publish_policy_response")
    return result


def check_publish(external_id):
    with get_connection() as connection:
        apps = connection.execute("""SELECT * FROM applications
            WHERE external_id=%s AND LOWER(platform)='appsmith' FOR UPDATE""",
                                  (external_id,)).fetchall()
        if len(apps) != 1:
            return {"allowed": False, "reasons": ["unique_discovered_application_required"]}
        app = apps[0]
        source = connection.execute("""SELECT id, observed_at, payload FROM discovery_observations
            WHERE application_id=%s AND source='appsmith'
            ORDER BY observed_at DESC, received_at DESC LIMIT 1""", (app["id"],)).fetchone()
        decision = connection.execute("""SELECT * FROM governance_decisions
            WHERE application_id=%s ORDER BY created_at DESC, id DESC LIMIT 1""",
                                      (app["id"],)).fetchone()
        origin_id = ((decision or {}).get("source_evidence") or {}).get("observation_id")
        origin = connection.execute("""SELECT id, observed_at, payload FROM discovery_observations
            WHERE id=%s AND application_id=%s AND source='appsmith'""",
                                    (origin_id, app["id"])).fetchone() if origin_id else None
        training = connection.execute("""SELECT id FROM training_assignments
            WHERE application_id=%s AND required=TRUE AND status NOT IN ('completed', 'not_required') LIMIT 1""",
                                      (app["id"],)).fetchone()
        # Consult the existing governance policy too; a publish rule cannot
        # override a hard governance block. Do not replace historical decisions.
        policy = evaluate_and_persist(app["id"], connection=connection, persist=False)
        features = app.get("discovery_feature_evidence") or {}
        evidence_ready = bool(
            fresh(source, datetime.now(timezone.utc)) and origin
            and source["payload"].get("external_id") == external_id
            and source["payload"].get("collection_complete") is True
            and not source["payload"].get("pending_reasons")
            and source_content(source) == source_content(origin)
            and features.get("fresh") is True
            and str(features.get("source_observation_id")) == str(source["id"])
            and features.get("approval_policy_available") is True
            and features.get("internal_boundary_valid") is True
            and not features.get("pending_reasons")
        )
        reviewed = False
        if decision and decision.get("outcome") == "SECURITY_REVIEW":
            review = connection.execute("""SELECT * FROM approval_requests
                WHERE application_id=%s AND governance_decision_id=%s""", (app["id"], decision["id"])).fetchone()
            reviewed = reviewed_approval_matches(app, decision, policy, review)

        approved = approval_matches(app, decision, policy) or reviewed
        if approved:
            binding = decision["source_evidence"]
            approved = all(
                (row or {}).get("payload", {}).get(key) == binding[key]
                for row in (origin, source)
                for key in ("manifest_version", "release_sha256")
            )
        facts = {
            "application": {key: app.get(key) for key in (
                "registration_status", "data_classification", "risk_status", "risk_level",
                "ml_anomaly_status", "ml_anomalous", "ml_classification_status",
                "ml_classification_review_required", "security_scan_status", "security_scan_passed")},
            "evidence_ready": evidence_ready,
            "governance_approval_current": approved,
            "security_review_resolved": reviewed and approved,
            "governance_policy_allowed": policy["allowed"],
            "training_complete": training is None,
        }
        result = evaluate_publish_policy(facts)
        reasons = list(result["reasons"])
        # These evidence requirements remain mandatory even if a Rego rule is
        # accidentally weakened. Recheck age after external policy calls.
        for ok, reason in (
            (evidence_ready and fresh(source, datetime.now(timezone.utc)), "current_observed_evidence_required"),
            (approved, "current_automatic_approval_required"),
            (policy["allowed"] is True, "governance_policy_denied"),
            (training is None, "required_training_incomplete"),
        ):
            if not ok and reason not in reasons:
                reasons.append(reason)
        allowed = result["allow"] and not reasons
        receipt_id = uuid4()
        # This is an evaluation receipt, never a claim of successful deployment
        # or of native user authentication. Existing CTRL-06 stays not_assessed.
        connection.execute("""INSERT INTO access_decisions
            (id,application_id,subject_id,role,requested_action,allowed,decision,reasons,
             registration_status,data_classification,policy_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (receipt_id, app["id"], "appsmith-proxy", "service", "publish_preflight",
             allowed, "allow" if allowed else "deny", Jsonb(reasons),
             app.get("registration_status") or "unknown", app.get("data_classification") or "unknown", VERSION))
        report = {"allowed": allowed, "reasons": reasons, "decision_id": str(receipt_id),
                  "application_id": str(app["id"]),
                  "observation_id": str(source["id"]) if source else None,
                  "governance_decision_id": str(decision["id"]) if decision else None}
        if allowed:
            report["release_sha256"] = decision["source_evidence"]["release_sha256"]
    # Commit must succeed before the proxy can forward the request.
    return report


def publish_error(result, status_code, headers, code, message):
    """Keep non-2xx denial semantics and Appsmith's ResponseDTO error contract.

    Appsmith revision d847cf495020767bfe53f4ead37a24513a51d7d4 reads
    responseMeta.error.code in handleBadRequestError even for HTTP 403/503.
    Existing top-level receipt fields remain available to evidence collectors.
    Never return HTTP 200 for an error: Caddy would permit forwarding.
    """
    return JSONResponse({
        **result, "allowed": False, "scope": VERSION,
        "responseMeta": {
            "status": status_code, "success": False,
            "error": {"code": code, "message": message},
        },
        "data": None,
        "errorDisplay": f"{code}: {message}",
    }, status_code=status_code, headers=headers)


@router.get("/internal/appsmith/publish-preflight")
def publish_preflight(request: Request):
    headers = {"Cache-Control": "no-store", "X-LCNC-Publish-Guard": VERSION}
    try:
        external_id = publish_target(request.headers.get("x-lcnc-original-method"),
                                     request.headers.get("x-lcnc-original-uri"),
                                     request.headers.get("x-lcnc-appsmith-branch", ""))
    except ValueError as exc:
        return publish_error(
            {"reasons": [str(exc)]}, 403, headers, "LCNC-PUBLISH-REQUEST-REJECTED",
            "Request blocked by the publish guard. This request format is not supported.",
        )
    if external_id is None:
        return Response(status_code=204, headers=headers)
    try:
        result = check_publish(external_id)
    except Exception:
        # Do not expose DB details, tokens, cookies, or upstream response bodies.
        return publish_error(
            {"reasons": ["publish_preflight_unavailable"]}, 503, headers,
            "LCNC-PUBLISH-UNAVAILABLE",
            "Deployment blocked because the governance check is unavailable. "
            "Try again later or contact your administrator.",
        )
    if result.get("decision_id"):
        headers["X-LCNC-Publish-Decision"] = result["decision_id"]
    if result["allowed"] is True:
        digest = result.get("release_sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            return publish_error(
                {"reasons": ["approved_release_digest_unavailable"]}, 503, headers,
                "LCNC-PUBLISH-UNAVAILABLE", "Deployment blocked because the approved release digest is unavailable.",
            )
        headers["X-LCNC-Approved-Release-SHA256"] = digest
        return Response(status_code=204, headers=headers)
    return publish_error(
        result, 403, headers, "LCNC-PUBLISH-DENIED",
        "Deployment blocked by governance. Review and resolve the application's "
        "outstanding governance requirements before deploying.",
    )
