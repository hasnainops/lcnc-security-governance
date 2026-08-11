import json
import os
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status

from .database import get_connection


CONTROL_MATRIX_PATH = Path(
    os.getenv(
        "CONTROL_MATRIX_PATH",
        "/compliance/control-matrix.json",
    )
)


def load_control_matrix():
    try:
        with CONTROL_MATRIX_PATH.open() as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Compliance control matrix unavailable: {exc}",
        ) from exc


def get_controls():
    return load_control_matrix()


def get_application_compliance_evidence(application_id: UUID):
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

        risk_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM risk_assessments
            WHERE application_id = %s;
            """,
            (application_id,),
        ).fetchone()["count"]

        policy_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM policy_decisions
            WHERE application_id = %s;
            """,
            (application_id,),
        ).fetchone()["count"]

        governance_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM governance_decisions
            WHERE application_id = %s;
            """,
            (application_id,),
        ).fetchone()["count"]

    matrix = load_control_matrix()

    evidence_state = {
        "LCNC-GOV-01": (
            "available"
            if application["first_discovered_at"]
            and application["last_seen_at"]
            else "missing"
        ),
        "LCNC-GOV-02": (
            "available" if risk_count > 0 else "missing"
        ),
        "LCNC-GOV-03": (
            "available" if policy_count > 0 else "missing"
        ),
        "LCNC-GOV-04": (
            "available" if governance_count > 0 else "missing"
        ),
        "LCNC-GOV-05": (
            "available"
            if risk_count > 1 and governance_count > 1
            else "limited"
        ),
        "LCNC-GOV-06": (
            "available"
            if risk_count + policy_count + governance_count > 0
            else "missing"
        ),
        "LCNC-GOV-07": "platform_level",
        "LCNC-GOV-08": "platform_level",
    }

    evidence_summary = {
        "LCNC-GOV-01": (
            f"Discovered {application['first_discovered_at']} "
            f"and last seen {application['last_seen_at']}."
        ),
        "LCNC-GOV-02": (
            f"{risk_count} persisted risk assessment(s)."
        ),
        "LCNC-GOV-03": (
            f"{policy_count} persisted OPA policy decision(s)."
        ),
        "LCNC-GOV-04": (
            f"{governance_count} persisted governance decision(s)."
        ),
        "LCNC-GOV-05": (
            f"{risk_count} risk assessment(s) and "
            f"{governance_count} governance decision(s) "
            "available for lifecycle comparison."
        ),
        "LCNC-GOV-06": (
            f"Audit history contains {risk_count} risk, "
            f"{policy_count} policy and "
            f"{governance_count} governance record(s)."
        ),
        "LCNC-GOV-07": (
            "Platform-level evidence is provided by "
            "Prometheus and Grafana."
        ),
        "LCNC-GOV-08": (
            "Platform-level evidence is provided by "
            "GitHub Actions, Trivy and security tests."
        ),
    }

    controls = []

    for control in matrix["controls"]:
        control_id = control["id"]

        controls.append(
            {
                "id": control_id,
                "control_objective": control["control_objective"],
                "evidence_status": evidence_state.get(
                    control_id,
                    "unknown",
                ),
                "evidence_summary": evidence_summary.get(
                    control_id,
                    "No application-specific evidence mapping.",
                ),
                "responsible_role": control["responsible_role"],
                "framework_mapping": control["framework_mapping"],
                "implementation_status": control[
                    "implementation_status"
                ],
            }
        )

    return {
        "application": {
            "id": application["id"],
            "name": application["name"],
            "platform": application["platform"],
        },
        "disclaimer": matrix["metadata"]["disclaimer"],
        "evidence_counts": {
            "risk_assessments": risk_count,
            "policy_decisions": policy_count,
            "governance_decisions": governance_count,
        },
        "controls": controls,
    }
