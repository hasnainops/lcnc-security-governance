import re


SECRET_PATTERNS = [
    re.compile(
        r"(?i)(api[_-]?key|token|password|secret)"
        r"\s*[:=]\s*[A-Za-z0-9_\-]{8,}"
    ),
]


def finding(
    rule_id,
    title,
    severity,
    evidence,
    remediation,
):
    return {
        "rule_id": rule_id,
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "remediation": remediation,
    }


def scan_application(payload):
    findings = []

    registration_status = (
        payload.get("registration_status")
        or "unknown"
    ).lower()

    classification = (
        payload.get("data_classification")
        or "unknown"
    ).lower()

    credential_type = (
        payload.get("credential_type")
        or ""
    ).lower()

    connector_metadata = (
        payload.get("connector_metadata")
        or ""
    )

    external_count = int(
        payload.get(
            "external_integration_count"
        )
        or 0
    )

    unapproved_count = int(
        payload.get(
            "unapproved_integration_count"
        )
        or 0
    )

    if registration_status != "registered":
        findings.append(
            finding(
                "SEC-001",
                "Application is not governance registered",
                "high",
                f"registration_status={registration_status}",
                "Register the application and assign accountable ownership.",
            )
        )

    if not payload.get("owner_known"):
        findings.append(
            finding(
                "SEC-002",
                "Accountable owner is missing",
                "medium",
                "owner_known=false",
                "Assign an accountable business or application owner.",
            )
        )

    if classification == "unknown":
        findings.append(
            finding(
                "SEC-003",
                "Data classification is unknown",
                "medium",
                "data_classification=unknown",
                "Complete data classification before production use.",
            )
        )

    if unapproved_count > 0:
        findings.append(
            finding(
                "SEC-004",
                "Unapproved external integration detected",
                "high",
                (
                    "unapproved_integration_count="
                    f"{unapproved_count}"
                ),
                "Review and approve or remove the external integration.",
            )
        )

    if credential_type in {
        "api_key",
        "api-key",
        "apikey",
    }:
        findings.append(
            finding(
                "SEC-005",
                "API-key credential usage detected",
                "medium",
                f"credential_type={credential_type}",
                "Use a managed secret reference and rotate credentials regularly.",
            )
        )

    if "http://" in connector_metadata.lower():
        findings.append(
            finding(
                "SEC-006",
                "Unencrypted HTTP integration detected",
                "high",
                "connector_metadata contains http://",
                "Use HTTPS/TLS for external integrations.",
            )
        )

    for pattern in SECRET_PATTERNS:
        match = pattern.search(
            connector_metadata
        )

        if match:
            findings.append(
                finding(
                    "SEC-007",
                    "Possible embedded secret detected",
                    "critical",
                    "credential-like value found in connector metadata",
                    "Remove the embedded credential and use managed secret storage.",
                )
            )
            break

    if (
        classification
        in {"confidential", "restricted"}
        and external_count > 0
    ):
        findings.append(
            finding(
                "SEC-008",
                "Sensitive data uses external integration",
                "medium",
                (
                    f"data_classification={classification}; "
                    "external_integration_count="
                    f"{external_count}"
                ),
                "Require DLP and policy validation before allowing data egress.",
            )
        )

    severity_order = {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
    }

    highest_severity = None

    if findings:
        highest_severity = max(
            (
                item["severity"]
                for item in findings
            ),
            key=lambda value: (
                severity_order[value]
            ),
        )

    return {
        "scanner_version": "lcnc-scanner-v1",
        "finding_count": len(findings),
        "highest_severity": highest_severity,
        "passed": len(findings) == 0,
        "findings": findings,
    }
