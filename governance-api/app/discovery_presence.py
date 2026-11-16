"""Refresh observed Appsmith names without changing governed application facts.

Identity matching protects against an accidental cross-application update; it
does not add caller authentication to the existing local collector endpoint.
Migration 022 invalidates advisory classification when the name changes.
"""
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .database import get_connection


class AppsmithSeenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    source: Literal["appsmith"]
    external_id: str = Field(
        strict=True, min_length=1, max_length=255,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    name: str = Field(strict=True, min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip() or any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Expected a nonempty application name without control characters")
        return value


def persist_application_seen(application_id: UUID, payload: AppsmithSeenRequest | None = None):
    with get_connection() as connection:
        if payload is None:
            # Compatibility with existing clients that send no request body.
            application = connection.execute(
                """UPDATE applications SET last_seen_at=NOW(), updated_at=NOW()
                   WHERE id=%s RETURNING *;""", (application_id,),
            ).fetchone()
        else:
            application = connection.execute(
                """UPDATE applications
                   SET name=%s, last_seen_at=NOW(), updated_at=NOW()
                   WHERE id=%s AND platform=%s AND external_id=%s
                   RETURNING *;""",
                (payload.name, application_id, payload.source, payload.external_id),
            ).fetchone()
            if application is None:
                existing = connection.execute(
                    "SELECT id FROM applications WHERE id=%s;", (application_id,),
                ).fetchone()
                if existing is not None:
                    raise HTTPException(409, "Observed Appsmith identity does not match the inventory application")
        if application is None:
            raise HTTPException(404, "Application not found")
    return application
