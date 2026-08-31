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
    external_integration: bool | None = None
    integration_approved: bool | None = None

    credential_type: str | None = None
    data_fields: str | None = None
    connector_metadata: str | None = None


class ApplicationUpdate(BaseModel):
    owner_name: str | None = None
    owner_email: str | None = None
    business_unit: str | None = None
    business_purpose: str | None = None
    registration_status: str | None = None
    lifecycle_status: str | None = None
    data_classification: str | None = None
    internet_exposed: bool | None = None
    external_integration: bool | None = None
    integration_approved: bool | None = None
    credential_type: str | None = None
    data_fields: str | None = None
    connector_metadata: str | None = None
