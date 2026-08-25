import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_API = ROOT / "governance-api"

sys.path.insert(
    0,
    str(GOVERNANCE_API),
)

from app.workflow import determine_outcome


def low_risk():
    return {
        "level": "low",
        "score": 10,
    }


def allowed_policy():
    return {
        "allowed": True,
        "action": "allow",
        "reasons": [],
    }


def denied_policy():
    return {
        "allowed": False,
        "action": "deny",
        "reasons": [
            "Hard governance policy failed.",
        ],
    }


def assessed_anomaly():
    return {
        "ml_anomaly_status": "assessed",
        "ml_anomalous": True,
        "ml_decision_score": -0.127144,
        "ml_model_version": "isolation-forest-v1",
    }


def pending_ai():
    return {
        "ml_anomaly_status": "pending",
        "ml_anomalous": True,
        "ml_decision_score": None,
        "ml_model_version": None,
    }


def test_opa_deny_remains_block_even_with_ai_anomaly():
    result = determine_outcome(
        low_risk(),
        denied_policy(),
        assessed_anomaly(),
    )

    assert result["outcome"] == "BLOCK"
    assert result["status"] == "blocked"


def test_assessed_ai_anomaly_escalates_allowed_low_risk_to_security_review():
    result = determine_outcome(
        low_risk(),
        allowed_policy(),
        assessed_anomaly(),
    )

    assert result["outcome"] == "SECURITY_REVIEW"
    assert result["status"] == "pending_review"
    assert result["required_role"] == (
        "Security/GRC Reviewer"
    )


def test_pending_ai_does_not_override_existing_low_risk_route():
    result = determine_outcome(
        low_risk(),
        allowed_policy(),
        pending_ai(),
    )

    assert result["outcome"] == "AUTO_APPROVE"
    assert result["status"] == "completed"
