from pydantic import BaseModel


class ApplicationRiskInput(BaseModel):
    registration_status: str
    owner_name: str | None = None
    business_purpose: str | None = None
    data_classification: str = "unknown"
    internet_exposed: bool = False
    external_integration: bool | None = None
    integration_approved: bool | None = None
    credential_type: str | None = None


class RiskFactor(BaseModel):
    code: str
    weight: int
    reason: str


class RiskAssessment(BaseModel):
    score: int
    level: str
    factors: list[RiskFactor]
    model_version: str
