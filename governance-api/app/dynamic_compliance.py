import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException

from .database import get_connection


CONTROL_REFERENCES = {
    "CTRL-01": {
        "iso": [
            "ISO/IEC 27001:2022 / 27002:2022 — information security roles and responsibilities"
        ],
        "owasp": [
            "OWASP ASVS 5.0 — Architecture and Access Control"
        ],
    },
    "CTRL-02": {
        "iso": [
            "ISO/IEC 27001:2022 / 27002:2022 — information classification"
        ],
        "owasp": [
            "OWASP ASVS 5.0 — Data Protection"
        ],
    },
    "CTRL-03": {
        "iso": [
            "ISO/IEC 27001:2022 / 27002:2022 — supplier and external-party security"
        ],
        "owasp": [
            "OWASP ASVS 5.0 — Secure Communication, Web APIs, and Configuration"
        ],
    },
    "CTRL-04": {
        "iso": [
            "ISO/IEC 27001:2022 / 27002:2022 — technical vulnerability management"
        ],
        "owasp": [
            "OWASP ASVS 5.0 — application security verification"
        ],
    },
    "CTRL-05": {
        "iso": [
            "ISO/IEC 27001:2022 / 27002:2022 — data leakage prevention"
        ],
        "owasp": [
            "OWASP ASVS 5.0 — Data Protection and Secure Communication"
        ],
    },
    "CTRL-06": {
        "iso": [
            "ISO/IEC 27001:2022 / 27002:2022 — access control and access rights"
        ],
        "owasp": [
            "OWASP ASVS 5.0 — Access Control"
        ],
    },
    "CTRL-07": {
        "iso": [
            "ISO/IEC 27001:2022 — information-security risk governance"
        ],
        "owasp": [
            "OWASP ASVS 5.0 — Architecture and documented security decisions"
        ],
    },
}


def control(
    control_id,
    title,
    status,
    evidence,
    remediation=None,
):
    return {
        "control_id": control_id,
        "title": title,
        "status": status,
        "evidence": evidence,
        "remediation": remediation,
        "framework_references": CONTROL_REFERENCES.get(
            control_id,
            {
                "iso": [],
                "owasp": [],
            },
        ),
    }


def evaluate_dynamic_compliance(
    application_id: UUID,
):
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
                status_code=404,
                detail="Application not found",
            )

        latest_transfer = connection.execute(
            """
            SELECT *
            FROM integration_transfer_events
            WHERE application_id = %s
            ORDER BY evaluated_at DESC
            LIMIT 1;
            """,
            (application_id,),
        ).fetchone()

        latest_access = connection.execute(
            """
            SELECT *
            FROM access_decisions
            WHERE application_id = %s
            ORDER BY evaluated_at DESC
            LIMIT 1;
            """,
            (application_id,),
        ).fetchone()

    controls = []

    # CTRL-01 — accountable ownership
    owner_known = bool(
        application["owner_name"]
        or application["owner_email"]
    )

    controls.append(
        control(
            "CTRL-01",
            "Accountable owner assigned",
            "pass" if owner_known else "fail",
            (
                "Application has accountable ownership metadata."
                if owner_known
                else "No accountable owner is assigned."
            ),
            (
                None
                if owner_known
                else "Assign an accountable application or business owner."
            ),
        )
    )

    # CTRL-02 — classification
    classification = (
        application["data_classification"]
        or "unknown"
    ).lower()

    classification_known = (
        classification != "unknown"
    )

    controls.append(
        control(
            "CTRL-02",
            "Data classification established",
            (
                "pass"
                if classification_known
                else "fail"
            ),
            f"Current classification: {classification}",
            (
                None
                if classification_known
                else "Complete authoritative data classification."
            ),
        )
    )

    # CTRL-03 — integration approval
    external_count = application[
        "external_integration_count"
    ]

    unapproved_count = application[
        "unapproved_integration_count"
    ]

    if (
        external_count is None
        or unapproved_count is None
    ):
        integration_status = "not_assessed"
        integration_evidence = (
            "Integration telemetry is incomplete."
        )
        integration_remediation = (
            "Collect external and unapproved integration counts."
        )

    elif unapproved_count > 0:
        integration_status = "fail"
        integration_evidence = (
            f"{unapproved_count} unapproved integration(s) "
            f"out of {external_count} external integration(s)."
        )
        integration_remediation = (
            "Approve or remove unapproved external integrations."
        )

    else:
        integration_status = "pass"
        integration_evidence = (
            f"{external_count} external integration(s); "
            "none currently marked unapproved."
        )
        integration_remediation = None

    controls.append(
        control(
            "CTRL-03",
            "External integrations approved",
            integration_status,
            integration_evidence,
            integration_remediation,
        )
    )

    # CTRL-04 — security scanning
    scan_status = application[
        "security_scan_status"
    ]

    if scan_status != "scanned":
        security_status = "not_assessed"
        security_evidence = (
            f"Current security scan state: {scan_status}"
        )
        security_remediation = (
            "Run the citizen-application security scanner."
        )

    elif application[
        "security_scan_passed"
    ] is True:
        security_status = "pass"
        security_evidence = (
            "Latest security scan passed."
        )
        security_remediation = None

    else:
        security_status = "fail"
        security_evidence = (
            "Latest security scan did not pass; "
            f"findings={application['security_finding_count']}, "
            f"highest_severity="
            f"{application['security_highest_severity']}."
        )
        security_remediation = (
            "Remediate security findings and rescan."
        )

    controls.append(
        control(
            "CTRL-04",
            "Security scan completed and acceptable",
            security_status,
            security_evidence,
            security_remediation,
        )
    )

    # CTRL-05 — DLP / egress protection
    if external_count is None:
        dlp_status = "not_assessed"
        dlp_evidence = (
            "External integration count is unknown; "
            "historical DLP transfer records do not establish "
            "current integration coverage."
        )
        dlp_remediation = (
            "Complete verified integration discovery "
            "before determining DLP applicability."
        )

    elif external_count == 0:
        if (
            unapproved_count is None
            or application["connector_metadata"] is None
        ):
            dlp_status = "not_assessed"
            dlp_evidence = (
                "Zero external integrations reported, "
                "but supporting integration evidence is incomplete."
            )
            dlp_remediation = (
                "Verify integration enumeration and approval metadata."
            )
        else:
            dlp_status = "pass"
            dlp_evidence = (
                "Zero external integrations reported with "
                "integration metadata present; external DLP "
                "is currently not applicable."
            )
            dlp_remediation = None

    elif latest_transfer is None:
        dlp_status = "not_assessed"
        dlp_evidence = (
            "No integration-gateway DLP transfer evidence exists."
        )
        dlp_remediation = (
            "Route an outbound integration through the DLP gateway."
        )

    else:
        outcome = latest_transfer.get("enforcement_outcome")
        enforced_at = latest_transfer.get("enforced_at")
        evaluated_at = latest_transfer.get("evaluated_at")

        blocked = (
            outcome == "blocked_before_send"
            and latest_transfer.get("allowed") is False
            and latest_transfer.get("decision") == "block"
        )

        forwarded = (
            outcome == "forwarded_upstream"
            and latest_transfer.get("allowed") is True
            and latest_transfer.get("decision") == "allow"
            and isinstance(
                latest_transfer.get("upstream_status_code"), int
            )
            and 100 <= latest_transfer["upstream_status_code"] <= 599
        )

        valid_timestamps = (
            isinstance(enforced_at, datetime)
            and isinstance(evaluated_at, datetime)
            and enforced_at.tzinfo is not None
            and evaluated_at.tzinfo is not None
        )

        fresh = False

        if valid_timestamps:
            age = datetime.now(timezone.utc) - enforced_at
            max_age = timedelta(
                seconds=int(
                    os.getenv(
                        "DLP_RECEIPT_MAX_AGE_SECONDS",
                        "86400",
                    )
                )
            )
            fresh = (
                max_age.total_seconds() > 0
                and timedelta(0) <= age <= max_age
                and evaluated_at <= enforced_at
            )

        if fresh and (blocked or forwarded):
            dlp_status = "pass"
            dlp_evidence = (
                "Recent controlled-egress enforcement verified: "
                f"outcome={outcome}; "
                f"enforced_at={enforced_at.isoformat()}. "
                "Evidence applies only to the controlled-egress "
                "operation, not universal integration coverage."
            )
            dlp_remediation = None
        else:
            dlp_status = "not_assessed"
            dlp_evidence = (
                "Recent controlled-egress enforcement is not "
                "verified. Gateway evaluation records alone "
                "do not establish enforcement."
            )
            dlp_remediation = (
                "Verify a current transfer through controlled "
                "egress and retain its enforcement receipt."
            )

    controls.append(
        control(
            "CTRL-05",
            "Sensitive-data egress protected by DLP",
            dlp_status,
            dlp_evidence,
            dlp_remediation,
        )
    )

    # CTRL-06 — OPA authorization
    if latest_access is None:
        access_status = "not_assessed"
        access_evidence = (
            "No OPA authorization evidence exists."
        )
        access_remediation = (
            "Evaluate at least one application action through OPA."
        )

    else:
        # A recorded OPA decision is evaluation evidence,
        # not proof that the requested operation was enforced.
        access_status = "not_assessed"
        access_evidence = (
            "OPA authorization decision recorded, but "
            "operation-level enforcement is not verified: "
            f"role={latest_access['role']}, "
            f"action={latest_access['requested_action']}, "
            f"decision={latest_access['decision']}."
        )
        access_remediation = (
            "Verify that the governed operation was allowed "
            "or blocked at its execution boundary."
        )

    controls.append(
        control(
            "CTRL-06",
            "Access decisions enforced through OPA",
            access_status,
            access_evidence,
            access_remediation,
        )
    )

    # CTRL-07 — governance state
    governance_state = (
        application["governance_status"]
        or "not_assessed"
    ).lower()

    if governance_state in {
        "stale",
        "pending",
        "pending_review",
        "not_assessed",
        "not_evaluated",
    }:
        governance_control_status = (
            "not_assessed"
        )
        governance_remediation = (
            "Run the current governance workflow."
        )

    elif governance_state in {
        "denied",
        "deny",
        "rejected",
        "blocked",
    }:
        governance_control_status = "fail"
        governance_remediation = (
            "Resolve governance denial reasons "
            "before approval."
        )

    elif (
        governance_state == "completed"
        and application["governance_decided_at"] is not None
    ):
        decided_at = application["governance_decided_at"]

        evidence_timestamps = (
            application.get("risk_assessed_at"),
            application.get("security_scanned_at"),
            application.get("ml_assessed_at"),
        )

        newer_evidence = any(
            timestamp is not None and timestamp > decided_at
            for timestamp in evidence_timestamps
        )

        stale_evidence = any(
            application.get(field) == "stale"
            for field in (
                "risk_status",
                "security_scan_status",
                "ml_anomaly_status",
            )
        )

        if newer_evidence or stale_evidence:
            governance_control_status = "not_assessed"
            governance_remediation = (
                "Governance-relevant assessment evidence is newer "
                "than the decision or explicitly stale. "
                "Re-run the governance workflow."
            )
        else:
            governance_control_status = "pass"
            governance_remediation = None

    else:
        governance_control_status = "not_assessed"
        governance_remediation = (
            "Verify a completed, recorded governance decision "
            "and confirm its evidence is current."
        )

    controls.append(
        control(
            "CTRL-07",
            "Governance decision current",
            governance_control_status,
            (
                "Current governance state: "
                f"{governance_state}"
            ),
            governance_remediation,
        )
    )

    statuses = [
        item["status"]
        for item in controls
    ]

    if "fail" in statuses:
        overall_status = "fail"
    elif "not_assessed" in statuses:
        overall_status = "not_assessed"
    else:
        overall_status = "pass"

    summary = {
        "pass": statuses.count("pass"),
        "fail": statuses.count("fail"),
        "not_assessed": statuses.count(
            "not_assessed"
        ),
    }

    return {
        "application_id": application_id,
        "application_name": application["name"],
        "assessment_version": (
            "dynamic-compliance-v1"
        ),
        "overall_status": overall_status,
        "summary": summary,
        "controls": controls,
    }
