from fastapi import FastAPI

from .models import (
    ApplicationRiskInput,
    RiskAssessment,
    RiskFactor,
)


app = FastAPI(
    title="LCNC Governance Risk Engine",
    version="1.0.0",
)


def add_factor(
    factors: list[RiskFactor],
    code: str,
    weight: int,
    reason: str,
):
    factors.append(
        RiskFactor(
            code=code,
            weight=weight,
            reason=reason,
        )
    )


def calculate_risk(application: ApplicationRiskInput) -> RiskAssessment:
    factors: list[RiskFactor] = []

    if application.registration_status.lower() != "registered":
        add_factor(
            factors,
            "UNREGISTERED_APPLICATION",
            20,
            "Application is not registered with governance.",
        )

    if not application.owner_name:
        add_factor(
            factors,
            "OWNER_UNKNOWN",
            10,
            "No accountable application owner is recorded.",
        )

    if not application.business_purpose:
        add_factor(
            factors,
            "BUSINESS_PURPOSE_UNKNOWN",
            5,
            "Business purpose has not been documented.",
        )

    classification = application.data_classification.lower()

    if classification == "unknown":
        add_factor(
            factors,
            "DATA_CLASSIFICATION_UNKNOWN",
            10,
            "Data sensitivity has not been classified.",
        )

    elif classification == "confidential":
        add_factor(
            factors,
            "CONFIDENTIAL_DATA",
            20,
            "Application processes confidential data.",
        )

    elif classification == "restricted":
        add_factor(
            factors,
            "RESTRICTED_DATA",
            25,
            "Application processes restricted or highly sensitive data.",
        )

    if application.internet_exposed:
        add_factor(
            factors,
            "INTERNET_EXPOSED",
            15,
            "Application is externally accessible.",
        )

    if application.external_integration is None:
        add_factor(
            factors,
            "INTEGRATION_STATUS_UNKNOWN",
            10,
            "External integration status has not been assessed.",
        )

    elif application.external_integration:
        add_factor(
            factors,
            "EXTERNAL_INTEGRATION",
            15,
            "Application connects to an external system.",
        )

        if application.integration_approved is False:
            add_factor(
                factors,
                "UNAPPROVED_INTEGRATION",
                15,
                "External integration has not been approved.",
            )

        elif application.integration_approved is None:
            add_factor(
                factors,
                "INTEGRATION_APPROVAL_UNKNOWN",
                10,
                "Approval status of the external integration is unknown.",
            )

    if application.credential_type:
        credential = application.credential_type.lower()

        if credential in {"api_key", "api-key", "apikey"}:
            add_factor(
                factors,
                "API_KEY_CREDENTIAL",
                10,
                "Application uses an API key credential.",
            )

    score = min(
        sum(factor.weight for factor in factors),
        100,
    )

    if score >= 75:
        level = "critical"
    elif score >= 50:
        level = "high"
    elif score >= 25:
        level = "medium"
    else:
        level = "low"

    return RiskAssessment(
        score=score,
        level=level,
        factors=factors,
        model_version="deterministic-v1",
    )


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "risk-engine",
        "version": "1.0.0",
    }


@app.post("/assess", response_model=RiskAssessment)
def assess(application: ApplicationRiskInput):
    return calculate_risk(application)
