from time import perf_counter
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .approval_automation import route_governance_approval
from .assessment import assess_and_persist
from .database import get_connection
from .metrics import (
    GOVERNANCE_OUTCOMES_TOTAL,
    GOVERNANCE_WORKFLOW_DURATION,
    POLICY_DECISIONS_TOTAL,
    RISK_ASSESSMENTS_TOTAL,
    RISK_SCORE,
)
from .policy import evaluate_and_persist


def determine_outcome(assessment, policy):
    if not policy["allowed"]:
        return {
            "outcome": "BLOCK",
            "status": "blocked",
            "required_role": "Security/GRC Reviewer",
            "reasons": policy["reasons"],
        }

    risk_level = assessment["level"].lower()

    if risk_level == "low":
        return {
            "outcome": "AUTO_APPROVE",
            "status": "completed",
            "required_role": None,
            "reasons": [
                "Low risk assessment and all hard governance policies passed."
            ],
        }

    if risk_level == "medium":
        return {
            "outcome": "BUSINESS_REVIEW",
            "status": "pending_review",
            "required_role": "Business Application Owner",
            "reasons": [
                "Medium risk requires business owner review."
            ],
        }

    return {
        "outcome": "SECURITY_REVIEW",
        "status": "pending_review",
        "required_role": "Security/GRC Reviewer",
        "reasons": [
            f"{risk_level.title()} risk requires security/GRC review."
        ],
    }


def run_governance_workflow(application_id: UUID):
    started_at = perf_counter()

    try:
        assessment = assess_and_persist(application_id)

        RISK_ASSESSMENTS_TOTAL.labels(
            level=assessment["level"]
        ).inc()

        RISK_SCORE.observe(
            assessment["score"]
        )

        policy = evaluate_and_persist(application_id)

        POLICY_DECISIONS_TOTAL.labels(
            action=policy["action"]
        ).inc()

        governance = determine_outcome(
            assessment,
            policy,
        )

        governance_id = uuid4()

        with get_connection() as connection:
            decision = connection.execute(
                """
                INSERT INTO governance_decisions (
                    id,
                    application_id,
                    risk_assessment_id,
                    policy_decision_id,
                    outcome,
                    status,
                    required_role,
                    reasons
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *;
                """,
                (
                    governance_id,
                    application_id,
                    assessment["assessment_id"],
                    policy["decision_id"],
                    governance["outcome"],
                    governance["status"],
                    governance["required_role"],
                    Jsonb(governance["reasons"]),
                ),
            ).fetchone()

            connection.execute(
                """
                UPDATE applications
                SET
                    governance_status = %s,
                    governance_outcome = %s,
                    governance_decided_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (
                    governance["status"],
                    governance["outcome"],
                    application_id,
                ),
            )

        GOVERNANCE_OUTCOMES_TOTAL.labels(
            outcome=governance["outcome"],
            status=governance["status"],
        ).inc()

        approval_automation = route_governance_approval(
            application_id
        )

        return {
            "application_id": application_id,
            "application_name": assessment["application_name"],
            "risk": {
                "score": assessment["score"],
                "level": assessment["level"],
                "model_version": assessment["model_version"],
                "factors": assessment["factors"],
            },
            "policy": {
                "action": policy["action"],
                "allowed": policy["allowed"],
                "reasons": policy["reasons"],
                "policy_version": policy["policy_version"],
            },
            "governance": {
                "decision_id": decision["id"],
                "outcome": decision["outcome"],
                "status": decision["status"],
                "required_role": decision["required_role"],
                "reasons": decision["reasons"],
                "created_at": decision["created_at"],
            },
            "approval_automation": approval_automation,
        }

    finally:
        GOVERNANCE_WORKFLOW_DURATION.observe(
            perf_counter() - started_at
        )
