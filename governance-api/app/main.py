from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, status
from psycopg.errors import UniqueViolation

from app.database import get_connection
from app.models import ApplicationCreate


app = FastAPI(
    title="LCNC Security Governance API",
    description="Governance control plane for low-code/no-code applications",
    version="0.2.0"
)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "governance-api",
        "version": "0.2.0"
    }


@app.post("/applications", status_code=status.HTTP_201_CREATED)
def create_application(application: ApplicationCreate):
    application_id = uuid4()

    query = """
        INSERT INTO applications (
            id,
            external_id,
            name,
            platform,
            owner_name,
            owner_email,
            business_unit,
            business_purpose,
            registration_status,
            lifecycle_status,
            data_classification,
            internet_exposed,
            external_integration,
            integration_approved,
            credential_type,
            data_fields,
            connector_metadata
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        )
        RETURNING *;
    """

    values = (
        application_id,
        application.external_id,
        application.name,
        application.platform,
        application.owner_name,
        application.owner_email,
        application.business_unit,
        application.business_purpose,
        application.registration_status,
        application.lifecycle_status,
        application.data_classification,
        application.internet_exposed,
        application.external_integration,
        application.integration_approved,
        application.credential_type,
        application.data_fields,
        application.connector_metadata,
    )

    try:
        with get_connection() as connection:
            result = connection.execute(query, values).fetchone()

    except UniqueViolation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application with this external_id already exists"
        )

    return result


@app.get("/applications")
def list_applications():
    with get_connection() as connection:
        applications = connection.execute(
            """
            SELECT *
            FROM applications
            ORDER BY first_discovered_at DESC;
            """
        ).fetchall()

    return applications


@app.get("/applications/{application_id}")
def get_application(application_id: UUID):
    with get_connection() as connection:
        application = connection.execute(
            """
            SELECT *
            FROM applications
            WHERE id = %s;
            """,
            (application_id,)
        ).fetchone()

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )

    return application


@app.patch("/applications/{application_id}/seen")
def mark_application_seen(application_id: UUID):
    with get_connection() as connection:
        application = connection.execute(
            """
            UPDATE applications
            SET
                last_seen_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *;
            """,
            (application_id,)
        ).fetchone()

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )

    return application


from .assessment import assess_and_persist as assess_risk_and_persist


@app.post("/applications/{application_id}/assess")
def assess_application_risk(application_id: UUID):
    return assess_risk_and_persist(application_id)


from .models import ApplicationUpdate


@app.patch("/applications/{application_id}")
def update_application(
    application_id: UUID,
    update: ApplicationUpdate
):
    changes = update.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No application fields supplied"
        )

    assignments = ", ".join(
        f"{field} = %s"
        for field in changes
    )

    values = list(changes.values())
    values.append(application_id)

    with get_connection() as connection:
        application = connection.execute(
            f"""
            UPDATE applications
            SET
                {assignments},
                risk_status = 'stale',
                risk_score = NULL,
                risk_level = NULL,
                risk_model_version = NULL,
                risk_assessed_at = NULL,
                ml_anomaly_status = 'stale',
                ml_anomalous = NULL,
                ml_decision_score = NULL,
                ml_model_version = NULL,
                ml_assessed_at = NULL,
                ml_classification_status = 'stale',
                ml_suggested_classification = NULL,
                ml_classification_confidence = NULL,
                ml_classification_review_required = NULL,
                ml_classification_model_version = NULL,
                ml_classified_at = NULL,
                security_scan_status = 'stale',
                security_finding_count = NULL,
                security_highest_severity = NULL,
                security_scan_passed = NULL,
                security_scanner_version = NULL,
                security_scanned_at = NULL,
                governance_status = 'stale',
                governance_outcome = NULL,
                governance_decided_at = NULL,
                updated_at = NOW()
            WHERE id = %s
            RETURNING *;
            """,
            values
        ).fetchone()

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )

    return application


from .policy import evaluate_and_persist as evaluate_policy_and_persist


@app.post("/applications/{application_id}/policy-evaluate")
def evaluate_application_policy(application_id: UUID):
    return evaluate_policy_and_persist(application_id)


from .workflow import run_governance_workflow


@app.post("/applications/{application_id}/governance-evaluate")
def evaluate_application_governance(application_id: UUID):
    return run_governance_workflow(application_id)


from .history import get_application_history


@app.get("/applications/{application_id}/history")
def application_history(application_id: UUID):
    return get_application_history(application_id)


from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


@app.get("/metrics")
def prometheus_metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


from .compliance import (
    get_application_compliance_evidence,
    get_controls,
)


@app.get("/compliance/controls")
def compliance_controls():
    return get_controls()


@app.get("/applications/{application_id}/compliance-evidence")
def application_compliance_evidence(application_id: UUID):
    return get_application_compliance_evidence(application_id)


from .ml import analyze_and_persist as analyze_ml_and_persist


@app.post("/applications/{application_id}/ml-analyze")
def analyze_application_ml(application_id: UUID):
    return analyze_ml_and_persist(application_id)


from .classification import classify_and_persist


@app.post("/applications/{application_id}/ml-classify")
def classify_application_ml(application_id: UUID):
    return classify_and_persist(application_id)


from .security_scan import scan_and_persist


@app.post("/applications/{application_id}/security-scan")
def scan_application_security(application_id: UUID):
    return scan_and_persist(application_id)


from .integration import (
    TransferEvaluationRequest,
    evaluate_and_persist as evaluate_transfer_and_persist,
)


@app.post(
    "/applications/{application_id}/evaluate-transfer"
)
def evaluate_application_transfer(
    application_id: UUID,
    payload: TransferEvaluationRequest,
):
    return evaluate_transfer_and_persist(
        application_id,
        payload,
    )


from .access import (
    AccessRequest,
    authorize_and_persist,
)


@app.post(
    "/applications/{application_id}/authorize"
)
def authorize_application_action(
    application_id: UUID,
    payload: AccessRequest,
):
    return authorize_and_persist(
        application_id,
        payload,
    )


from .dynamic_compliance import (
    evaluate_dynamic_compliance,
)


@app.get(
    "/applications/{application_id}/compliance/dynamic"
)
def get_dynamic_compliance(
    application_id: UUID,
):
    return evaluate_dynamic_compliance(
        application_id
    )


from .compliance_assessment import (
    assess_and_persist as assess_compliance_and_persist,
)


@app.post(
    "/applications/{application_id}/compliance/dynamic/assess"
)
def assess_application_compliance(
    application_id: UUID,
):
    return assess_compliance_and_persist(
        application_id
    )


from .citizen_guidance import (
    build_guidance,
)


@app.get(
    "/applications/{application_id}/citizen-guidance"
)
def get_citizen_guidance(
    application_id: UUID,
):
    return build_guidance(
        application_id
    )


from .training import (
    TrainingCompletionRequest,
    complete_training,
    get_training_status,
)


@app.post(
    "/applications/{application_id}/training/complete"
)
def complete_application_training(
    application_id: UUID,
    payload: TrainingCompletionRequest,
):
    return complete_training(
        application_id,
        payload,
    )


@app.get(
    "/applications/{application_id}/training/status"
)
def get_application_training_status(
    application_id: UUID,
    subject_id: str,
):
    return get_training_status(
        application_id,
        subject_id,
    )
