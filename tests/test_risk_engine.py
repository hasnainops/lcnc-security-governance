import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RISK_ENGINE_APP_DIR = ROOT / "risk-engine" / "app"

package_name = "risk_engine_app"

package = types.ModuleType(package_name)
package.__path__ = [str(RISK_ENGINE_APP_DIR)]
package.__package__ = package_name

sys.modules[package_name] = package

main_module = importlib.import_module(
    "risk_engine_app.main"
)

models_module = importlib.import_module(
    "risk_engine_app.models"
)

calculate_risk = main_module.calculate_risk
ApplicationRiskInput = models_module.ApplicationRiskInput


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
