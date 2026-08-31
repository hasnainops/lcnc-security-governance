from uuid import UUID

from .dynamic_compliance import (
    evaluate_dynamic_compliance,
)


TRAINING_CATALOG = {
    "CTRL-01": {
        "module_id": "ownership-basics",
        "title": "Application Ownership Basics",
        "guidance": [
            "Assign a named accountable owner.",
            "Keep owner contact information current.",
            "Define who approves security and business changes.",
        ],
    },
    "CTRL-02": {
        "module_id": "data-classification",
        "title": "Data Classification for Citizen Apps",
        "guidance": [
            "Identify the most sensitive data handled by the app.",
            "Classify data before enabling external integrations.",
            "Escalate restricted or regulated data for review.",
        ],
    },
    "CTRL-03": {
        "module_id": "integration-security",
        "title": "Secure Integration Practices",
        "guidance": [
            "Use only approved integrations and destinations.",
            "Remove unused or unapproved connectors.",
            "Use encrypted HTTPS connections for external services.",
        ],
    },
    "CTRL-04": {
        "module_id": "secure-lcnc-development",
        "title": "Secure Low-Code Development",
        "guidance": [
            "Resolve high-severity scanner findings before release.",
            "Avoid embedded credentials in application configuration.",
            "Rescan after security-relevant application changes.",
        ],
    },
    "CTRL-05": {
        "module_id": "dlp-egress-protection",
        "title": "DLP and Safe Data Sharing",
        "guidance": [
            "Route sensitive outbound transfers through the DLP gateway.",
            "Do not send restricted data to external destinations without approval.",
            "Use only the minimum data required for the business purpose.",
        ],
    },
    "CTRL-06": {
        "module_id": "least-privilege-access",
        "title": "Least Privilege and Access Control",
        "guidance": [
            "Request only the permissions required for the task.",
            "Use role-based access rather than shared privileged accounts.",
            "Route sensitive actions through the OPA authorization control.",
        ],
    },
    "CTRL-07": {
        "module_id": "governance-workflow",
        "title": "Citizen App Governance Workflow",
        "guidance": [
            "Re-run governance after material application changes.",
            "Resolve denied or stale controls before production use.",
            "Keep risk, policy, and compliance evidence current.",
        ],
    },
}


def calculate_score(controls):
    points = 0.0

    for item in controls:
        if item["status"] == "pass":
            points += 1.0
        elif item["status"] == "not_assessed":
            points += 0.5

    if not controls:
        return 0

    return round(
        (points / len(controls)) * 100
    )


def badge_for_score(score):
    if score >= 90:
        return "gold"

    if score >= 75:
        return "silver"

    if score >= 60:
        return "bronze"

    return "needs_attention"


def build_guidance(
    application_id: UUID,
):
    compliance = evaluate_dynamic_compliance(
        application_id
    )

    controls = compliance["controls"]

    score = calculate_score(controls)
    badge = badge_for_score(score)

    recommendations = []

    for item in controls:
        if item["status"] == "pass":
            continue

        training = TRAINING_CATALOG.get(
            item["control_id"]
        )

        if training is None:
            continue

        recommendations.append(
            {
                **training,
                "trigger_control": (
                    item["control_id"]
                ),
                "control_status": (
                    item["status"]
                ),
                "reason": item["evidence"],
                "remediation": (
                    item["remediation"]
                ),
            }
        )

    return {
        "application_id": (
            compliance["application_id"]
        ),
        "application_name": (
            compliance["application_name"]
        ),
        "guidance_version": (
            "citizen-guidance-v1"
        ),
        "security_score": score,
        "badge": badge,
        "overall_compliance_status": (
            compliance["overall_status"]
        ),
        "control_summary": (
            compliance["summary"]
        ),
        "recommended_training_count": (
            len(recommendations)
        ),
        "recommended_training": (
            recommendations
        ),
    }
