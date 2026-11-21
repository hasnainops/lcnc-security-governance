from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app import appsmith_publish, dynamic_compliance


NOW = datetime.now(timezone.utc)
APP_ID = uuid4()

APPLICATION = {
    "id": APP_ID,
    "registration_status": "registered",
    "data_classification": "internal",
}

RECEIPT = {
    "id": uuid4(),
    "application_id": APP_ID,
    "subject_id": "appsmith-proxy",
    "role": "service",
    "requested_action": "publish_preflight",
    "allowed": False,
    "decision": "deny",
    "policy_version": appsmith_publish.VERSION,
    "registration_status": "registered",
    "data_classification": "internal",
    "evaluated_at": NOW - timedelta(seconds=5),
    "proxy_denial_verified_at": NOW,
    "proxy_denial_http_status": 403,
}


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({}, True),
        ({"proxy_denial_verified_at": None}, False),
        ({"proxy_denial_http_status": None}, False),
        ({"proxy_denial_http_status": 200}, False),
        ({"application_id": uuid4()}, False),
        ({"allowed": True}, False),
        ({"decision": "allow"}, False),
        ({"requested_action": "read"}, False),
        ({"data_classification": "public"}, False),
        ({"policy_version": "unknown"}, False),
        ({
            "evaluated_at": NOW - timedelta(days=2),
            "proxy_denial_verified_at": NOW - timedelta(days=2),
        }, False),
        ({
            "proxy_denial_verified_at": NOW + timedelta(minutes=1),
        }, False),
        ({
            "evaluated_at": NOW - timedelta(minutes=10),
        }, False),
    ],
)
def test_proxy_enforcement_evidence(changes, expected):
    receipt = {**RECEIPT, **changes}

    assert dynamic_compliance.verified_proxy_denial(
        APPLICATION, receipt, NOW
    ) is expected


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({}, True),
        ({"allowed": False}, False),
        ({"review_verified": False}, False),
        ({"application_id": str(uuid4())}, False),
        ({"governance_decision_id": None}, False),
        ({"observation_id": None}, False),
    ],
)
def test_current_reviewed_release(monkeypatch, changes, expected):

    application = {
        **APPLICATION,
        "platform": "appsmith",
        "external_id": "a" * 24,
        "governance_status": "pending_review",
        "governance_outcome": "SECURITY_REVIEW",
    }

    response = {
        "allowed": True,
        "review_verified": True,
        "application_id": str(APP_ID),
        "governance_decision_id": str(uuid4()),
        "observation_id": str(uuid4()),
        **changes,
    }

    def check(external_id, *, record_receipt=True):
        assert external_id == application["external_id"]
        assert record_receipt is False
        return response

    monkeypatch.setattr(
        appsmith_publish,
        "check_publish",
        check,
    )

    result = dynamic_compliance.current_reviewed_release(
        application
    )

    assert (result is not None) is expected
