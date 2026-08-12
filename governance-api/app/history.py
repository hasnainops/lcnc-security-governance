from uuid import UUID

from fastapi import HTTPException, status

from .database import get_connection


def get_application_history(application_id: UUID):
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

        risk_history = connection.execute(
            """
            SELECT
                id,
                score,
                level,
                model_version,
                factors,
                assessed_at
            FROM risk_assessments
            WHERE application_id = %s
            ORDER BY assessed_at DESC;
            """,
            (application_id,),
        ).fetchall()

        ml_history = connection.execute(
            """
            SELECT
                id,
                analysis_type,
                anomalous,
                decision_score,
                model_version,
                features,
                context_signals,
                assessed_at
            FROM ml_assessments
            WHERE application_id = %s
            ORDER BY assessed_at DESC;
            """,
            (application_id,),
        ).fetchall()

        classification_history = connection.execute(
            """
            SELECT
                id,
                suggested_classification,
                confidence,
                review_required,
                review_threshold,
                model_version,
                class_probabilities,
                inputs,
                authority,
                classified_at
            FROM classification_assessments
            WHERE application_id = %s
            ORDER BY classified_at DESC;
            """,
            (application_id,),
        ).fetchall()

        security_scan_history = connection.execute(
            """
            SELECT
                id,
                scanner_version,
                finding_count,
                highest_severity,
                passed,
                scanned_at
            FROM security_scans
            WHERE application_id = %s
            ORDER BY scanned_at DESC;
            """,
            (application_id,),
        ).fetchall()

        security_finding_history = connection.execute(
            """
            SELECT
                id,
                scan_id,
                rule_id,
                title,
                severity,
                evidence,
                remediation,
                created_at
            FROM security_findings
            WHERE application_id = %s
            ORDER BY created_at DESC;
            """,
            (application_id,),
        ).fetchall()

        transfer_history = connection.execute(
            """
            SELECT
                id,
                destination_scheme,
                destination_host,
                destination_trust,
                declared_classification,
                effective_sensitivity,
                decision,
                allowed,
                reasons,
                dlp_sensitive_data_detected,
                dlp_finding_count,
                dlp_highest_sensitivity,
                dlp_detected_types,
                gateway_version,
                dlp_engine_version,
                evaluated_at
            FROM integration_transfer_events
            WHERE application_id = %s
            ORDER BY evaluated_at DESC;
            """,
            (application_id,),
        ).fetchall()

        access_history = connection.execute(
            """
            SELECT
                id,
                subject_id,
                role,
                requested_action,
                allowed,
                decision,
                reasons,
                registration_status,
                data_classification,
                policy_version,
                evaluated_at
            FROM access_decisions
            WHERE application_id = %s
            ORDER BY evaluated_at DESC;
            """,
            (application_id,),
        ).fetchall()

        policy_history = connection.execute(
            """
            SELECT
                id,
                action,
                allowed,
                reasons,
                policy_version,
                evaluated_at
            FROM policy_decisions
            WHERE application_id = %s
            ORDER BY evaluated_at DESC;
            """,
            (application_id,),
        ).fetchall()

        governance_history = connection.execute(
            """
            SELECT
                id,
                outcome,
                status,
                required_role,
                reasons,
                created_at
            FROM governance_decisions
            WHERE application_id = %s
            ORDER BY created_at DESC;
            """,
            (application_id,),
        ).fetchall()

    return {
        "application": application,
        "risk_assessments": risk_history,
        "ml_assessments": ml_history,
        "classification_assessments": classification_history,
        "security_scans": security_scan_history,
        "security_findings": security_finding_history,
        "integration_transfer_events": transfer_history,
        "access_decisions": access_history,
        "policy_decisions": policy_history,
        "governance_decisions": governance_history,
    }
