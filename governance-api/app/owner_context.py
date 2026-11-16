"""Application-scoped owner declarations, with server-owned identity binding."""

import hashlib
import json
import re
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from .database import get_connection


class OwnerField(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    description: str = Field(min_length=1, max_length=255)


class OwnerContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    contract_version: Literal["owner-context-v1"] = "owner-context-v1"
    business_purpose: str = Field(min_length=10, max_length=2000)
    field_scope: Literal["declared_schema", "no_data_fields"]
    data_fields: list[OwnerField] = Field(max_length=100)
    attested: StrictBool

    @field_validator("business_purpose")
    @classmethod
    def real_purpose(cls, value):
        if value.casefold() in {"not available", "not applicable", "unknown purpose"}:
            raise ValueError("Supply an actual business purpose")
        return value

    @model_validator(mode="after")
    def check_declaration(self):
        if not self.attested:
            raise ValueError("Owner attestation is required")
        if (self.field_scope == "declared_schema") != bool(self.data_fields):
            raise ValueError("Supply field definitions, or explicitly attest no data fields")
        names = [field.name.casefold() for field in self.data_fields]
        if len(names) != len(set(names)):
            raise ValueError("Field names must be unique")
        return self


def canonical_context(payload):
    body = payload.model_dump(mode="json")
    body["data_fields"].sort(key=lambda field: field["name"].casefold())
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return body, digest


def token_digest(authorization):
    if not isinstance(authorization, str):
        raise HTTPException(401, "Owner credential required", headers={"WWW-Authenticate": "Bearer"})
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not re.fullmatch(r"lo1_[A-Za-z0-9_-]{43}", value):
        raise HTTPException(401, "Invalid owner credential", headers={"WWW-Authenticate": "Bearer"})
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def save_owner_context(application_id: UUID, payload: OwnerContextRequest, authorization: str | None):
    digest = token_digest(authorization)
    body, payload_hash = canonical_context(payload)
    with get_connection() as connection:
        # Serialize with the operator revocation helper without granting this
        # workload UPDATE permission on the credential table.
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0));", (digest,))
        credential = connection.execute(
            """SELECT id, application_id, subject_id, owner_name, owner_email
               FROM application_owner_credentials
               WHERE token_sha256 = %s AND revoked_at IS NULL
                 AND expires_at > clock_timestamp();""", (digest,),
        ).fetchone()
        if credential is None:
            raise HTTPException(401, "Invalid, expired or revoked owner credential")
        if credential["application_id"] != application_id:
            raise HTTPException(403, "Owner credential does not cover this application")
        application = connection.execute(
            "SELECT * FROM applications WHERE id = %s FOR UPDATE;", (application_id,),
        ).fetchone()
        if application is None:
            raise HTTPException(404, "Application not found")
        if application["platform"] != "appsmith":
            raise HTTPException(409, "This declaration flow covers the Appsmith MVP")
        existing = None
        if application.get("owner_context_id"):
            existing = connection.execute(
                "SELECT * FROM application_owner_contexts WHERE id = %s AND application_id = %s;",
                (application["owner_context_id"], application_id),
            ).fetchone()
        if existing and existing["payload_sha256"] == payload_hash and existing["subject_id"] == credential["subject_id"]:
            return {"action": "unchanged", "context_id": existing["id"], "declared_at": existing["declared_at"]}
        context_id = uuid4()
        saved = connection.execute(
            """INSERT INTO application_owner_contexts
               (id, application_id, credential_id, subject_id, owner_name, owner_email, payload, payload_sha256)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING declared_at;""",
            (context_id, application_id, credential["id"], credential["subject_id"],
             credential["owner_name"], credential["owner_email"], Jsonb(body), payload_hash),
        ).fetchone()
        fields = "; ".join(f"{item['name']}: {item['description']}" for item in body["data_fields"])
        if not fields:
            fields = "Owner attests that this application has no data fields."
        connection.execute(
            """UPDATE applications SET owner_context_id = %s,
               owner_name = %s, owner_email = %s, business_purpose = %s, data_fields = %s,
               risk_status = 'stale', risk_score = NULL, risk_level = NULL,
               risk_model_version = NULL, risk_assessed_at = NULL,
               ml_anomaly_status = 'stale', ml_anomalous = NULL, ml_decision_score = NULL,
               ml_model_version = NULL, ml_assessed_at = NULL,
               security_scan_status = 'stale', security_scan_passed = NULL,
               security_finding_count = NULL, security_highest_severity = NULL,
               security_scanner_version = NULL, security_scanned_at = NULL,
               governance_status = 'stale', governance_outcome = NULL,
               governance_decided_at = NULL, updated_at = NOW()
               WHERE id = %s;""",
            (context_id, credential["owner_name"], credential["owner_email"],
             body["business_purpose"], fields, application_id),
        )
    return {"action": "saved", "context_id": context_id, "declared_at": saved["declared_at"]}
