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

from .status_routes import router as status_router

app.include_router(status_router)


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


from .risk_orchestration import assess_risk_if_needed


@app.post("/applications/{application_id}/assess-if-needed")
def assess_application_risk_if_needed(application_id: UUID):
    return assess_risk_if_needed(application_id)


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
                shadow_it_candidate = FALSE,
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
    ControlledEgressRequest,
    TransferEvaluationRequest,
    evaluate_and_persist as evaluate_transfer_and_persist,
    execute_controlled_egress,
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


@app.post(
    "/applications/{application_id}/controlled-egress"
)
def execute_application_controlled_egress(
    application_id: UUID,
    payload: ControlledEgressRequest,
):
    return execute_controlled_egress(
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
    assign_required_training,
    complete_training,
    get_training_assignments,
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
    "/applications/{application_id}/training/assignments"
)
def get_application_training_assignments(
    application_id: UUID,
):
    return get_training_assignments(
        application_id
    )


@app.post(
    "/applications/{application_id}/training/automation/run"
)
def run_application_training_automation(
    application_id: UUID,
):
    return assign_required_training(
        application_id
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


from .enterprise_handoff import (
    EnterpriseDiscoveryHandoff,
    persist_enterprise_discovery_handoff,
)


@app.post("/enterprise-discovery/handoff")
def enterprise_discovery_handoff(
    payload: EnterpriseDiscoveryHandoff,
):
    return persist_enterprise_discovery_handoff(
        payload.model_dump()
    )


from .workflow_evidence import (
    WorkflowSecurityMetadata,
    persist_workflow_security_metadata,
)


@app.post(
    "/applications/{application_id}/observed-workflow-security"
)
def ingest_observed_workflow_security(
    application_id: UUID,
    payload: WorkflowSecurityMetadata,
):
    return persist_workflow_security_metadata(
        application_id,
        payload,
    )


from .discovery_observation import AppsmithObservation
from .observation_store import persist_discovery_observation


from .feature_assembly import assemble_features


@app.post("/applications/{application_id}/discovery-observations")
def ingest_discovery_observation(
    application_id: UUID,
    payload: AppsmithObservation,
):
    stored = persist_discovery_observation(
        application_id,
        payload,
    )

    from datetime import timedelta
    from .database import get_connection
    from .feature_assembly import verified_changes_from_history

    cutoff = payload.observed_at - timedelta(hours=24)

    with get_connection() as connection:
        baseline = connection.execute(
            """
            SELECT payload
            FROM discovery_observations
            WHERE application_id = %s
              AND source = %s
              AND observed_at < %s
            ORDER BY observed_at DESC
            LIMIT 1;
            """,
            (application_id, payload.source, cutoff),
        ).fetchone()

        recent = connection.execute(
            """
            SELECT payload
            FROM discovery_observations
            WHERE application_id = %s
              AND source = %s
              AND observed_at >= %s
              AND observed_at <= %s
            ORDER BY observed_at ASC;
            """,
            (
                application_id,
                payload.source,
                cutoff,
                payload.observed_at,
            ),
        ).fetchall()

    rows = ([baseline] if baseline else []) + list(recent)

    observations = [
        AppsmithObservation.model_validate(row["payload"])
        for row in rows
    ]

    verified_changes = verified_changes_from_history(
        observations,
        payload.observed_at,
    )

    feature_result = assemble_features(
        payload,
        verified_changes_24h=verified_changes,
    )

    feature_result["feature_columns_updated"] = False

    if feature_result["ready_for_ml"]:
        values = feature_result["features"]

        names = (
            "external_integration_count",
            "unapproved_integration_count",
            "connector_count",
            "external_domain_count",
            "changes_last_24h",
        )

        if (
            set(values) != set(names)
            or any(
                type(values[name]) is not int
                or values[name] < 0
                for name in names
            )
        ):
            raise RuntimeError(
                "Invalid verified ML feature vector"
            )

        with get_connection() as connection:
            current = connection.execute(
                """
                SELECT
                    external_integration_count,
                    unapproved_integration_count,
                    connector_count,
                    external_domain_count,
                    changes_last_24h
                FROM applications
                WHERE id = %s
                FOR UPDATE;
                """,
                (application_id,),
            ).fetchone()

            if current is None:
                raise HTTPException(
                    404, "Application not found"
                )

            changed = any(
                current[name] != values[name]
                for name in names
            )

            if changed:
                connection.execute(
                    """
                    UPDATE applications
                    SET
                        external_integration_count = %s,
                        unapproved_integration_count = %s,
                        connector_count = %s,
                        external_domain_count = %s,
                        changes_last_24h = %s,
                        ml_anomaly_status = 'stale',
                        ml_anomalous = NULL,
                        ml_decision_score = NULL,
                        ml_model_version = NULL,
                        ml_assessed_at = NULL,
                        updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (
                        *(values[name] for name in names),
                        application_id,
                    ),
                )

            feature_result["feature_columns_updated"] = changed

    feature_result["ml_execution"] = {
        "action": "pending_evidence"
    }

    if feature_result["ready_for_ml"]:
        from .ml import analyze_ml_if_needed

        feature_result["ml_execution"] = (
            analyze_ml_if_needed(application_id)
        )

    feature_result["cold_start_diagnostic"] = {
        "action": "not_eligible"
    }

    if (
        stored["created"]
        and not feature_result["ready_for_ml"]
    ):
        from .feature_assembly import (
            cold_start_witnessed_evidence,
        )

        evidence = cold_start_witnessed_evidence(
            observations
        )

        required = (
            "external_integration_count",
            "unapproved_integration_count",
            "connector_count",
            "external_domain_count",
        )

        values = feature_result["features"]

        eligible = (
            evidence is not None
            and all(
                type(values[name]) is int
                and values[name] >= 0
                for name in required
            )
        )

        if eligible:
            from .ml import analyze_and_persist

            diagnostic_features = {
                name: values[name]
                for name in required
            }

            diagnostic_features["changes_last_24h"] = (
                evidence["witnessed_changes"]
            )

            provenance = {
                **evidence,
                "source_observation_id": str(
                    stored["id"]
                ),
                "change_count_scope": (
                    "witnessed_partial_history"
                ),
            }

            with get_connection() as connection:
                connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        41012, hashtext(%s)
                    );
                    """,
                    (str(application_id),),
                )

                latest = connection.execute(
                    """
                    SELECT id
                    FROM discovery_observations
                    WHERE application_id = %s
                      AND source = %s
                    ORDER BY
                        observed_at DESC,
                        received_at DESC
                    LIMIT 1;
                    """,
                    (application_id, payload.source),
                ).fetchone()

                if (
                    latest is None
                    or latest["id"] != stored["id"]
                ):
                    feature_result[
                        "cold_start_diagnostic"
                    ] = {
                        "action": "superseded"
                    }
                else:
                    previous = connection.execute(
                        """
                        SELECT
                            context_signals
                        FROM ml_assessments
                        WHERE application_id = %s
                          AND analysis_type =
                              'shadow-it-anomaly'
                        ORDER BY
                            assessed_at DESC,
                            id DESC
                        LIMIT 1;
                        """,
                        (application_id,),
                    ).fetchone()

                    status_row = connection.execute(
                        """
                        SELECT ml_anomaly_status
                        FROM applications
                        WHERE id = %s;
                        """,
                        (application_id,),
                    ).fetchone()

                    prior_evidence = None

                    if previous is not None:
                        signals = previous[
                            "context_signals"
                        ]

                        if isinstance(signals, list):
                            for item in signals:
                                if isinstance(item, dict):
                                    candidate = item.get(
                                        "lo1_diagnostic_provenance"
                                    )

                                    if isinstance(
                                        candidate, dict
                                    ):
                                        prior_evidence = candidate

                    unchanged = (
                        prior_evidence is not None
                        and status_row is not None
                        and status_row[
                            "ml_anomaly_status"
                        ] == "diagnostic"
                        and prior_evidence.get(
                            "observation_fingerprint"
                        ) == evidence[
                            "observation_fingerprint"
                        ]
                        and prior_evidence.get(
                            "witnessed_changes"
                        ) == evidence[
                            "witnessed_changes"
                        ]
                    )

                    if unchanged:
                        feature_result[
                            "cold_start_diagnostic"
                        ] = {
                            "action": "skipped_unchanged"
                        }
                    else:
                        result = analyze_and_persist(
                            application_id,
                            diagnostic_features=(
                                diagnostic_features
                            ),
                            diagnostic_provenance=(
                                provenance
                            ),
                        )

                        feature_result[
                            "cold_start_diagnostic"
                        ] = {
                            "action": "assessed",
                            "assessment_tier": (
                                "cold_start_witnessed"
                            ),
                            "assessment_id": str(
                                result["assessment_id"]
                            ),
                            "anomalous": result[
                                "anomalous"
                            ],
                            "decision_score": result[
                                "decision_score"
                            ],
                        }

    return {
        **stored,
        "feature_assembly": feature_result,
    }
