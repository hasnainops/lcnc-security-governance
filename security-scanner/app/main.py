from fastapi import FastAPI
from pydantic import BaseModel, Field

from .scanner import scan_application


app = FastAPI(
    title="LCNC Security Scanner",
    version="0.1.0",
)


class ScanInput(BaseModel):
    registration_status: str
    owner_known: bool

    data_classification: str

    internet_exposed: bool = False

    external_integration_count: int = Field(
        ge=0
    )

    unapproved_integration_count: int = Field(
        ge=0
    )

    credential_type: str | None = None
    connector_metadata: str | None = None


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "security-scanner",
        "scanner_version": "lcnc-scanner-v1",
    }


@app.post("/scan")
def scan(payload: ScanInput):
    return scan_application(
        payload.model_dump()
    )
