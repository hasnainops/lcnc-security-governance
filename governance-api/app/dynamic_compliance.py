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
    if external_count == 0:
        dlp_status = "pass"
        dlp_evidence = (
            "No external integrations reported; "
            "external DLP enforcement is not currently applicable."
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
        dlp_status = "pass"
        dlp_evidence = (
            "Latest transfer was evaluated by "
            f"{latest_transfer['dlp_engine_version']} "
            f"through {latest_transfer['gateway_version']}; "
            f"decision={latest_transfer['decision']}."
        )
        dlp_remediation = None

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
        access_status = "pass"
        access_evidence = (
            "OPA access-control decision recorded: "
            f"role={latest_access['role']}, "
            f"action={latest_access['requested_action']}, "
            f"decision={latest_access['decision']}."
        )
        access_remediation = None

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

    else:
        governance_control_status = "pass"
        governance_remediation = None

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
