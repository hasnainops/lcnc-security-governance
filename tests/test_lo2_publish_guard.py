import copy
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import appsmith_publish as gate


EXTERNAL = "6afabf4265d61d1e1b332ac1"
URI = "/api/v1/applications/publish/" + EXTERNAL


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(gate.router)
    return TestClient(app)


def request(client, uri=URI, method="POST", **extra):
    return client.get("/internal/appsmith/publish-preflight", headers={
        "X-LCNC-Original-Method": method, "X-LCNC-Original-Uri": uri, **extra,
    })


def test_normal_requests_do_not_query_db(client, monkeypatch):
    monkeypatch.setattr(gate, "check_publish", lambda _: pytest.fail("Unexpected DB check"))
    assert request(client, "/api/v1/applications", "GET").status_code == 204
    assert request(client, "/static/app.js", "GET").status_code == 204


@pytest.mark.parametrize("uri", [
    "/api/v1/applications", "/api/v1/applications/",
    "/api/v1/applications/clone/" + EXTERNAL,
    "/api/v1/applications/clone/" + EXTERNAL + "?workspaceId=test",
])
def test_auto_publish_routes_fail_before_appsmith(client, monkeypatch, uri):
    monkeypatch.setattr(gate, "check_publish", lambda _: pytest.fail("Unexpected DB check"))
    response = request(client, uri)
    assert response.status_code == 403
    assert response.json()["reasons"] == ["unreviewed_auto_publish_route"]


def test_application_list_read_still_passes(client):
    assert request(client, "/api/v1/applications", "GET").status_code == 204


@pytest.mark.parametrize("uri", [
    URI + "/", URI + "?branch=main", URI.replace("publish", "%70ublish"),
    URI.replace("publish", "%2570ublish"), URI.replace("publish", "x/../publish"),
    URI.replace("/api/", "//api/"), URI.replace("/publish/", "/publish;/"),
    URI.replace("/publish/", "/PUBLISH/"), URI.replace("publish", "publish//"),
    URI.replace("/publish/", "/publish\\"), "/api/v1/applications/publish/not-an-id",
])
def test_noncanonical_publish_never_reaches_policy(client, monkeypatch, uri):
    monkeypatch.setattr(gate, "check_publish", lambda _: pytest.fail("Unexpected DB check"))
    assert request(client, uri).status_code == 403


def test_missing_headers_branch_and_wrong_method_fail_closed(client):
    assert client.get("/internal/appsmith/publish-preflight").status_code == 403
    assert request(client, method="GET").status_code == 403
    assert request(client, **{"X-LCNC-Appsmith-Branch": "main"}).status_code == 403


def test_explicit_allow_and_deny_and_failure(client, monkeypatch):
    monkeypatch.setattr(gate, "check_publish", lambda _: {"allowed": True, "decision_id": "test", "release_sha256": "a" * 64})
    assert request(client).status_code == 204
    monkeypatch.setattr(gate, "check_publish", lambda _: {"allowed": False, "reasons": ["review_required"]})
    response = request(client)
    assert response.status_code == 403
    assert response.json()["reasons"] == ["review_required"]
    def fail(_):
        raise RuntimeError("secret raw upstream response")
    monkeypatch.setattr(gate, "check_publish", fail)
    response = request(client)
    assert response.status_code == 503
    assert "secret" not in response.text


@pytest.mark.parametrize("case,status,code", [
    ("policy_denial", 403, "LCNC-PUBLISH-DENIED"),
    ("unknown_application", 403, "LCNC-PUBLISH-DENIED"),
    ("invalid_request", 403, "LCNC-PUBLISH-REQUEST-REJECTED"),
    ("unavailable", 503, "LCNC-PUBLISH-UNAVAILABLE"),
])
def test_errors_satisfy_appsmith_client_contract(client, monkeypatch, case, status, code):
    receipt = {"allowed": False, "reasons": ["review_required"],
               "decision_id": "receipt-123", "application_id": "application-123"}
    if case == "unknown_application":
        receipt = {"allowed": False, "reasons": ["unique_discovered_application_required"]}
    def check(_):
        if case == "unavailable":
            raise RuntimeError("private DB connection details")
        return receipt
    monkeypatch.setattr(gate, "check_publish", check)
    response = request(client, method="GET" if case == "invalid_request" else "POST")
    body = response.json()
    assert response.status_code == status  # Never turn denial into forward_auth success.
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-lcnc-publish-guard"] == gate.VERSION
    assert body["allowed"] is False and body["scope"] == gate.VERSION
    # The deployed Appsmith interceptor reads this chain before checking status.
    assert body["responseMeta"]["error"]["code"] == code
    assert body["responseMeta"]["status"] == status
    assert body["responseMeta"]["success"] is False
    message = body["responseMeta"]["error"]["message"]
    assert isinstance(message, str) and "blocked" in message
    assert body["data"] is None
    assert body["errorDisplay"] == f"{code}: {message}"
    assert "private DB" not in response.text
    if case == "policy_denial":
        assert all(body[key] == value for key, value in receipt.items())
        assert response.headers["x-lcnc-publish-decision"] == "receipt-123"
    else:
        assert "x-lcnc-publish-decision" not in response.headers


@pytest.mark.parametrize("result", [None, [], True, {},
    {"allow": "true", "action": "allow", "reasons": [], "version": gate.VERSION},
    {"allow": True, "action": "deny", "reasons": [], "version": gate.VERSION},
    {"allow": True, "action": "allow", "reasons": ["deny"], "version": gate.VERSION},
    {"allow": False, "action": "deny", "reasons": [], "version": gate.VERSION},
    {"allow": True, "action": "allow", "reasons": [], "version": "old"},
])
def test_malformed_opa_result_rejected(monkeypatch, result):
    monkeypatch.setattr(gate.httpx, "post", lambda *a, **k: httpx.Response(
        200, json={"result": result}, request=httpx.Request("POST", "http://opa")))
    with pytest.raises(ValueError):
        gate.evaluate_publish_policy({})


@pytest.fixture
def state(monkeypatch):
    now = datetime.now(timezone.utc)
    app_id, source_id, decision_id = uuid4(), uuid4(), uuid4()
    source = {"id": source_id, "observed_at": now, "payload": {
        "external_id": EXTERNAL, "collection_complete": True,
        "observed_at": now.isoformat(), "connectors": [], "observed_actions": [],
        "page_ids": ["page1"], "pending_reasons": [], "data_field_evidence": {"widgets_inspected": 0},
    }}
    policy = {"allowed": True, "action": "allow", "reasons": [], "policy_version": "application-v2"}
    app = {"id": app_id, "registration_status": "registered", "data_classification": "internal",
           "risk_status": "assessed", "risk_level": "low", "risk_score": 10,
           "ml_anomaly_status": "assessed", "ml_anomalous": False,
           "ml_classification_status": "assessed", "ml_classification_review_required": False,
           "security_scan_status": "scanned", "security_scan_passed": True,
           "governance_status": "completed", "governance_outcome": "AUTO_APPROVE",
           "governance_decided_at": now, "discovery_feature_evidence": {
               "fresh": True, "source_observation_id": str(source_id), "approval_policy_available": True,
               "internal_boundary_valid": True, "pending_reasons": [],
           }}
    decision = {"id": decision_id, "outcome": "AUTO_APPROVE", "status": "completed", "created_at": now,
                "source_evidence": {"authority": "deterministic_governance", "observation_id": str(source_id)}}
    # Simulate a decision issued for a particular release by the trusted writer.
    release_digest = hashlib.sha256(b"fixture release A").hexdigest()
    source["payload"].update(
        manifest_version="appsmith-release-manifest-v1", release_sha256=release_digest,
    )
    decision["source_evidence"].update(
        manifest_version="appsmith-release-manifest-v1", release_sha256=release_digest,
    )
    decision["input_sha256"] = hashlib.sha256(json.dumps({
        "version": "automatic-governance-v2",
        "manifest_version": "appsmith-release-manifest-v1",
        "release_sha256": release_digest,
        "application_id": str(app["id"]),
        "application": {k: app.get(k) for k in gate.INPUT_FIELDS},
        "policy": policy, "outcome": gate.determine_outcome({"level": "low"}, policy, app),
    }, sort_keys=True, default=str).encode()).hexdigest()
    state = SimpleNamespace(app=app, source=source, origin=copy.deepcopy(source), decision=decision,
                            policy=policy, training=None, review=None, writes=[], committed=False, fail_commit=False,
                            fail_write=False, count=1)
    class Connection:
        def execute(self, sql, params):
            if "FROM applications" in sql:
                self.rows = [state.app] * state.count
            elif "FROM governance_decisions" in sql:
                self.row = state.decision
            elif "FROM discovery_observations" in sql:
                self.row = state.origin if "WHERE id=" in sql else state.source
            elif "FROM training_assignments" in sql:
                self.row = state.training
            elif "FROM approval_requests" in sql:
                self.row = state.review
            elif "INSERT INTO access_decisions" in sql:
                if state.fail_write:
                    raise RuntimeError("DB write failed")
                state.writes.append(params)
            else:
                raise AssertionError(sql)
            return self
        def fetchone(self):
            return self.row
        def fetchall(self):
            return self.rows
    @contextmanager
    def connect():
        yield Connection()
        if state.fail_commit:
            raise RuntimeError("DB commit failed")
        state.committed = True
    monkeypatch.setattr(gate, "get_connection", connect)
    monkeypatch.setattr(gate, "evaluate_and_persist", lambda *a, **k: state.policy)
    # Deliberately return allow: mandatory evidence checks must still block.
    monkeypatch.setattr(gate, "evaluate_publish_policy", lambda facts: {"allow": True, "reasons": []})
    return state


def test_clean_approved_state_commits_evaluation_receipt(state):
    result = gate.check_publish(EXTERNAL)
    assert result["allowed"] is True
    assert state.committed
    assert len(state.writes) == 1
    assert state.writes[0][4:7] == ("publish_preflight", True, "allow")


@pytest.mark.parametrize("change", ["stale", "future", "partial", "changed_source", "changed_risk",
    "changed_policy", "missing_approval", "manual_approval", "review_pending", "training",
    "stale_features", "mismatched_observation", "no_source", "no_origin"])
def test_preconditions_cannot_be_overridden_by_opa_allow(state, change):
    if change == "stale": state.source["observed_at"] -= timedelta(minutes=4)
    if change == "future": state.source["observed_at"] += timedelta(minutes=4)
    if change == "partial": state.source["payload"]["collection_complete"] = False
    if change == "changed_source": state.source["payload"]["data_field_evidence"]["widgets_inspected"] = 1
    if change == "changed_risk": state.app["risk_score"] = 80
    if change == "changed_policy": state.policy["allowed"] = False
    if change == "missing_approval": state.decision = None
    if change == "manual_approval": state.decision["input_sha256"] = None
    if change == "review_pending": state.app["governance_status"] = "pending_review"
    if change == "training": state.training = {"id": uuid4()}
    if change == "stale_features": state.app["discovery_feature_evidence"]["fresh"] = False
    if change == "mismatched_observation": state.app["discovery_feature_evidence"]["source_observation_id"] = str(uuid4())
    if change == "no_source": state.source = None
    if change == "no_origin": state.origin = None
    assert gate.check_publish(EXTERNAL)["allowed"] is False
    assert state.writes[0][5] is False


@pytest.mark.parametrize("count", [0, 2])
def test_unknown_or_ambiguous_application_rejected(state, count):
    state.count = count
    assert gate.check_publish(EXTERNAL)["allowed"] is False
    assert not state.writes


@pytest.mark.parametrize("failure", ["fail_commit", "fail_write"])
def test_no_permission_before_audit_commits(client, state, failure):
    setattr(state, failure, True)
    assert request(client).status_code == 503


def test_age_rechecked_after_policy_call(state, monkeypatch):
    def delay_policy(facts):
        state.source["observed_at"] -= timedelta(minutes=4)
        return {"allow": True, "reasons": []}
    monkeypatch.setattr(gate, "evaluate_publish_policy", delay_policy)
    assert gate.check_publish(EXTERNAL)["allowed"] is False


def test_poll_time_alone_does_not_change_source_content(state):
    state.source["payload"]["observed_at"] = datetime.now(timezone.utc).isoformat()
    assert gate.source_content(state.source) == gate.source_content(state.origin)


def test_publish_denies_approval_without_release_binding(state):
    # Recreate the evidence stored by an approval issued before release binding.
    evidence = state.decision["source_evidence"]
    state.decision["source_evidence"] = {
        "authority": evidence["authority"],
        "observation_id": evidence["observation_id"],
    }
    result = gate.check_publish(EXTERNAL)
    assert result["allowed"] is False, (
        "Publish preflight accepted an approval with no approved release digest"
    )


def test_changed_release_digest_invalidates_approval(state):
    state.decision["source_evidence"]["release_sha256"] = hashlib.sha256(
        b"fixture release B"
    ).hexdigest()
    assert gate.check_publish(EXTERNAL)["allowed"] is False


@pytest.mark.parametrize("observed_digest", [None, hashlib.sha256(b"fixture release B").hexdigest()])
def test_approval_must_match_observed_release(state, observed_digest):
    for row in (state.origin, state.source):
        if observed_digest is None:
            del row["payload"]["release_sha256"]
        else:
            row["payload"]["release_sha256"] = observed_digest
    assert gate.check_publish(EXTERNAL)["allowed"] is False


def test_publish_response_carries_only_the_approved_digest(client, state):
    header = "X-LCNC-Approved-Release-SHA256"
    expected = state.decision["source_evidence"]["release_sha256"]
    response = request(client, **{header: "f" * 64})
    assert response.status_code == 204
    assert state.committed
    assert response.headers[header] == expected

    state.training = {"id": "incomplete"}
    denied = request(client, **{header: "f" * 64})
    assert denied.status_code == 403
    assert header not in denied.headers


def test_publish_response_requires_digest_on_allow(client, monkeypatch):
    monkeypatch.setattr(gate, "check_publish", lambda _: {"allowed": True, "decision_id": "test"})
    response = request(client)
    assert response.status_code == 503
    assert "X-LCNC-Approved-Release-SHA256" not in response.headers



# LO2.1: Full Security/GRC-reviewed release preflight regression.

def prepare_reviewed_release(state):
    app = state.app
    decision = state.decision

    app["ml_classification_review_required"] = True
    app["governance_status"] = "pending_review"
    app["governance_outcome"] = "SECURITY_REVIEW"

    decision["outcome"] = "SECURITY_REVIEW"
    decision["status"] = "pending_review"

    evidence = decision["source_evidence"]

    outcome = gate.determine_outcome(
        {"level": app["risk_level"]}, state.policy, app
    )

    assert outcome["outcome"] == "SECURITY_REVIEW"
    assert outcome["status"] == "pending_review"

    decision["input_sha256"] = hashlib.sha256(
        json.dumps({
            "version": "automatic-governance-v2",
            "manifest_version": evidence["manifest_version"],
            "release_sha256": evidence["release_sha256"],
            "application_id": str(app["id"]),
            "application": {
                k: app.get(k) for k in gate.INPUT_FIELDS
            },
            "policy": state.policy,
            "outcome": outcome,
        }, sort_keys=True, default=str).encode()
    ).hexdigest()

    state.review = {
        "application_id": app["id"],
        "governance_decision_id": decision["id"],
        "route_type": "security_review",
        "required_role": "Security/GRC Reviewer",
        "governance_outcome": "SECURITY_REVIEW",
        "status": "approved",
        "human_decision": "approve",
        "decided_by": "verified-test-reviewer",
        "decision_reason": "Reviewed the classification advisory",
        "decided_at": datetime.now(timezone.utc),
    }

    return state


def test_reviewed_release_passes_complete_preflight(state, monkeypatch):
    prepare_reviewed_release(state)

    observed_facts = {}

    def evaluate(facts):
        observed_facts.update(facts)
        return {"allow": True, "reasons": []}

    monkeypatch.setattr(gate, "evaluate_publish_policy", evaluate)

    result = gate.check_publish(EXTERNAL)

    assert result["allowed"] is True
    assert result["reasons"] == []
    assert result["release_sha256"] == (
        state.decision["source_evidence"]["release_sha256"]
    )
    assert observed_facts["security_review_resolved"] is True
    assert observed_facts["governance_approval_current"] is True
    assert state.committed is True
    assert len(state.writes) == 1


@pytest.mark.parametrize("failure", [
    "missing_review",
    "pending_review",
    "rejected_review",
    "wrong_decision",
    "wrong_reviewer_role",
    "edited_release",
    "incomplete_training",
    "hard_policy_block",
    "anomalous_application",
])
def test_reviewed_release_denied_on_failed_precondition(state, failure):
    prepare_reviewed_release(state)

    if failure == "missing_review":
        state.review = None

    elif failure == "pending_review":
        state.review["status"] = "pending"

    elif failure == "rejected_review":
        state.review["human_decision"] = "reject"

    elif failure == "wrong_decision":
        state.review["governance_decision_id"] = uuid4()

    elif failure == "wrong_reviewer_role":
        state.review["required_role"] = "Business Application Owner"

    elif failure == "edited_release":
        # Both observations now report B; approval remains bound to A.
        for observation in (state.origin, state.source):
            observation["payload"]["release_sha256"] = "b" * 64

    elif failure == "incomplete_training":
        state.training = {"id": uuid4()}

    elif failure == "hard_policy_block":
        state.policy["allowed"] = False

    elif failure == "anomalous_application":
        state.app["ml_anomalous"] = True

    result = gate.check_publish(EXTERNAL)

    assert result["allowed"] is False, failure
    assert result["reasons"], failure
    assert "release_sha256" not in result, failure
    assert state.committed is True
    assert len(state.writes) == 1
    assert state.writes[0][5] is False
