import os
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status

from .database import get_connection


SECURITY_SCANNER_URL = os.getenv(
    "SECURITY_SCANNER_URL",
    "http://security-scanner:8003",
)


REQUIRED_OBSERVED_FIELDS = [
    "external_integration_count",
    "unapproved_integration_count",
    "connector_metadata",
]


def scan_and_persist(application_id: UUID):
    with get_connection() as connection:
        application = connection.execute(
            """
            SELECT *
            FROM applications
            WHERE id = %s;
            """,
            (application_id,),
        ).fetchone()

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    missing_fields = [
        field
        for field in REQUIRED_OBSERVED_FIELDS
        if application[field] is None
        or (
            isinstance(application[field], str)
            and not application[field].strip()
        )
    ]

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "Security scan requires complete "
                    "observed integration metadata."
                ),
                "missing_fields": missing_fields,
            },
        )

    payload = {
        "registration_status": (
            application["registration_status"]
        ),
        "owner_known": bool(
            application["owner_name"]
            or application["owner_email"]
        ),
        "data_classification": (
            application["data_classification"]
        ),
        "internet_exposed": bool(
            application["internet_exposed"]
        ),
        "external_integration_count": (
            application["external_integration_count"]
        ),
        "unapproved_integration_count": (
            application["unapproved_integration_count"]
        ),
        "credential_type": (
            application["credential_type"]
        ),
        "connector_metadata": (
            application["connector_metadata"]
        ),
    }

    try:
        response = httpx.post(
            f"{SECURITY_SCANNER_URL}/scan",
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()

    except (
        httpx.ConnectError,
        httpx.TimeoutException,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Security Scanner unavailable. "
                "No security scan was persisted."
            ),
        ) from exc

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Security Scanner returned an "
                "upstream HTTP error."
            ),
        ) from exc

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Security Scanner request failed.",
        ) from exc

    result = response.json()
    scan_id = uuid4()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO security_scans (
                id,
                application_id,
                scanner_version,
                finding_count,
                highest_severity,
                passed
            )
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (
                scan_id,
                application_id,
                result["scanner_version"],
                result["finding_count"],
                result["highest_severity"],
                result["passed"],
            ),
        )

        persisted_findings = []

        for item in result["findings"]:
            finding_id = uuid4()

            connection.execute(
                """
                INSERT INTO security_findings (
                    id,
                    scan_id,
                    application_id,
                    rule_id,
                    title,
                    severity,
                    evidence,
                    remediation
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                );
                """,
                (
                    finding_id,
                    scan_id,
                    application_id,
                    item["rule_id"],
                    item["title"],
                    item["severity"],
                    item["evidence"],
                    item["remediation"],
                ),
            )

            persisted_findings.append(
                {
                    "id": finding_id,
                    **item,
                }
            )

        updated_application = connection.execute(
            """
            UPDATE applications
            SET
                security_scan_status = 'scanned',
                security_finding_count = %s,
                security_highest_severity = %s,
                security_scan_passed = %s,
                security_scanner_version = %s,
                security_scanned_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *;
            """,
            (
                result["finding_count"],
                result["highest_severity"],
                result["passed"],
                result["scanner_version"],
                application_id,
            ),
        ).fetchone()

    return {
        "scan_id": scan_id,
        "application_id": application_id,
        "application_name": (
            updated_application["name"]
        ),
        "scanner_version": result["scanner_version"],
        "finding_count": result["finding_count"],
        "highest_severity": result["highest_severity"],
        "passed": result["passed"],
        "findings": persisted_findings,
        "security_scan_status": (
            updated_application["security_scan_status"]
        ),
        "scanned_at": (
            updated_application["security_scanned_at"]
        ),
    }
