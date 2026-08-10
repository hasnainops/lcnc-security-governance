import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "risk-engine"))

from app.main import calculate_risk
from app.models import ApplicationRiskInput


def test_shadow_application_scores_55_high():
    application = ApplicationRiskInput(
        registration_status="unregistered",
        owner_name=None,
        business_purpose=None,
        data_classification="unknown",
        internet_exposed=False,
        external_integration=None,
        integration_approved=None,
        credential_type=None,
    )

    result = calculate_risk(application)

    assert result.score == 55
    assert result.level == "high"


def test_remediated_confidential_application_scores_20_low():
    application = ApplicationRiskInput(
        registration_status="registered",
        owner_name="Customer Operations Owner",
        business_purpose="Controlled internal processing",
        data_classification="confidential",
        internet_exposed=False,
        external_integration=False,
        integration_approved=None,
        credential_type=None,
    )

    result = calculate_risk(application)

    assert result.score == 20
    assert result.level == "low"


def test_risky_external_application_scores_90_critical():
    application = ApplicationRiskInput(
        registration_status="unregistered",
        owner_name=None,
        business_purpose="Exports customer records",
        data_classification="confidential",
        internet_exposed=False,
        external_integration=True,
        integration_approved=False,
        credential_type="api_key",
    )

    result = calculate_risk(application)

    assert result.score == 90
    assert result.level == "critical"
