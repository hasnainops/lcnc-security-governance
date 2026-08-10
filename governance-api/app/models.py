from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=100)

    owner_name: str | None = None
    owner_email: str | None = None
    business_unit: str | None = None
    business_purpose: str | None = None

    registration_status: str = "unregistered"
    lifecycle_status: str = "active"
    data_classification: str = "unknown"

    internet_exposed: bool = False
    external_integration: bool = False
    integration_approved: bool | None = None

    credential_type: str | None = None
