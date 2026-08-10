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
            credential_type
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
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


from .assessment import assess_and_persist


@app.post("/applications/{application_id}/assess")
def assess_application_risk(application_id: UUID):
    return assess_and_persist(application_id)


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


from .policy import evaluate_and_persist


@app.post("/applications/{application_id}/policy-evaluate")
def evaluate_application_policy(application_id: UUID):
    return evaluate_and_persist(application_id)
