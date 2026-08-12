from fastapi import FastAPI
from pydantic import BaseModel, Field

from .analyzer import (
    analyze_application,
    model_version,
)

from .classifier import (
    classify_application,
    classification_model_version,
)


app = FastAPI(
    title="LCNC ML Analytics",
    version="0.2.0",
)


class ApplicationFeatures(BaseModel):
    owner_known: int = Field(ge=0, le=1)
    business_purpose_known: int = Field(ge=0, le=1)
    internet_exposed: int = Field(ge=0, le=1)
    external_integration_count: int = Field(ge=0)
    unapproved_integration_count: int = Field(ge=0)
    uses_api_key: int = Field(ge=0, le=1)
    connector_count: int = Field(ge=0)
    external_domain_count: int = Field(ge=0)
    changes_last_24h: int = Field(ge=0)


class ClassificationInput(BaseModel):
    application_name: str = Field(min_length=1)
    business_purpose: str = Field(min_length=1)
    data_fields: str = Field(min_length=1)
    connector_metadata: str = Field(min_length=1)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "ml-analytics",
        "anomaly_model_version": model_version,
        "classification_model_version": (
            classification_model_version
        ),
    }


@app.post("/analyze")
def analyze(payload: ApplicationFeatures):
    result = analyze_application(
        payload.model_dump()
    )

    return {
        "analysis_type": "shadow-it-anomaly",
        **result,
    }


@app.post("/classify")
def classify(payload: ClassificationInput):
    result = classify_application(
        payload.model_dump()
    )

    return {
        "analysis_type": (
            "data-sensitivity-classification"
        ),
        **result,
    }
