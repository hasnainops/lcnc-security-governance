from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from .database import get_connection


class WorkflowSecurityMetadata(BaseModel):
    page_count: int = Field(ge=0)
    widget_count: int = Field(ge=0)
    action_count: int = Field(ge=0)
    api_action_count: int = Field(ge=0)
    dynamic_binding_count: int = Field(ge=0)
    invalid_action_count: int = Field(ge=0)
    http_action_count: int = Field(ge=0)
    https_action_count: int = Field(ge=0)
    sensitive_header_action_count: int = Field(ge=0)


def persist_workflow_security_metadata(
    application_id: UUID,
    metadata: WorkflowSecurityMetadata,
):
    """Persist sanitized observed workflow evidence.

    Raw workflow bodies, URLs, header values, and credentials
    are deliberately not accepted or stored here.
    """

    with get_connection() as connection:
        application = connection.execute(
            """
            UPDATE applications
            SET
                workflow_security_metadata =
                    incoming.metadata,

                security_scan_status =
                    CASE
                        WHEN
                            applications
                            .workflow_security_metadata
                            IS DISTINCT FROM
                            incoming.metadata
                        THEN 'stale'
                        ELSE security_scan_status
                    END,

                security_finding_count =
                    CASE
                        WHEN
                            applications
                            .workflow_security_metadata
                            IS DISTINCT FROM
                            incoming.metadata
                        THEN NULL
                        ELSE security_finding_count
                    END,

                security_highest_severity =
                    CASE
                        WHEN
                            applications
                            .workflow_security_metadata
                            IS DISTINCT FROM
                            incoming.metadata
                        THEN NULL
                        ELSE security_highest_severity
                    END,

                security_scan_passed =
                    CASE
                        WHEN
                            applications
                            .workflow_security_metadata
                            IS DISTINCT FROM
                            incoming.metadata
                        THEN NULL
                        ELSE security_scan_passed
                    END,

                security_scanner_version =
                    CASE
                        WHEN
                            applications
                            .workflow_security_metadata
                            IS DISTINCT FROM
                            incoming.metadata
                        THEN NULL
                        ELSE security_scanner_version
                    END,

                security_scanned_at =
                    CASE
                        WHEN
                            applications
                            .workflow_security_metadata
                            IS DISTINCT FROM
                            incoming.metadata
                        THEN NULL
                        ELSE security_scanned_at
                    END,

                updated_at =
                    CASE
                        WHEN
                            applications
                            .workflow_security_metadata
                            IS DISTINCT FROM
                            incoming.metadata
                        THEN NOW()
                        ELSE updated_at
                    END

            FROM (
                SELECT %s::jsonb AS metadata
            ) AS incoming

            WHERE applications.id = %s
            RETURNING applications.*;
            """,
            (
                Jsonb(metadata.model_dump()),
                application_id,
            ),
        ).fetchone()

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    return application
