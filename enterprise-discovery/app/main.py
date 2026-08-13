import json
import os
import urllib.request

from datetime import datetime, timezone
from uuid import uuid4

import psycopg
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field


app = FastAPI(
    title="LCNC Enterprise Discovery",
    version="0.2.0",
)


DATABASE_URL = os.environ["DATABASE_URL"]

ML_ANALYTICS_URL = os.getenv(
    "ML_ANALYTICS_URL",
    "http://ml-analytics:8002",
)


class DiscoveryEvent(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=100)

    authorization_status: str = "unknown"

    owner_known: bool | None = None
    business_purpose_known: bool | None = None
    internet_exposed: bool | None = None
    uses_api_key: bool | None = None

    external_integration_count: int | None = Field(
        default=None,
        ge=0,
    )
    unapproved_integration_count: int | None = Field(
        default=None,
        ge=0,
    )
    connector_count: int | None = Field(
        default=None,
        ge=0,
    )
    external_domain_count: int | None = Field(
        default=None,
        ge=0,
    )
    changes_last_24h: int | None = Field(
        default=None,
        ge=0,
    )

    evidence: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None


SOURCES = [
    {
        "source": "appsmith",
        "type": "lcnc_platform",
        "purpose": "Citizen application inventory",
        "status": "existing_live_worker",
        "configured": True,
    },
    {
        "source": "generic_security_feed",
        "type": "enterprise_shadow_it",
        "purpose": "Normalized enterprise discovery events",
        "status": "ready",
        "configured": True,
    },
    {
        "source": "defender_cloud_apps",
        "type": "enterprise_shadow_it",
        "purpose": "Microsoft Defender for Cloud Apps discovery adapter",
        "status": "adapter_not_configured",
        "configured": False,
    },
]


ML_FEATURES = [
    "owner_known",
    "business_purpose_known",
    "internet_exposed",
    "external_integration_count",
    "unapproved_integration_count",
    "uses_api_key",
    "connector_count",
    "external_domain_count",
    "changes_last_24h",
]


def get_connection():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    )


def analyze_with_ml(record: dict) -> dict:
    missing = [
        feature
        for feature in ML_FEATURES
        if record.get(feature) is None
    ]

    if missing:
        return {
            "status": "pending",
            "missing_features": missing,
        }

    payload = {}

    for feature in ML_FEATURES:
        value = record[feature]

        if isinstance(value, bool):
            value = int(value)

        payload[feature] = value

    request = urllib.request.Request(
        f"{ML_ANALYTICS_URL}/analyze",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=5,
        ) as response:
            result = json.loads(
                response.read().decode()
            )

        return {
            "status": "assessed",
            "result": result,
        }

    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
        }


def get_latest_discovery():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM enterprise_discoveries
                ORDER BY last_seen_at DESC
                LIMIT 1
                """
            )
            return cursor.fetchone()


@app.get("/", response_class=HTMLResponse)
def dashboard():
    latest = get_latest_discovery()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM enterprise_discoveries
                """
            )
            count = cursor.fetchone()["count"]

    latest_name = latest["name"] if latest else "None"
    latest_source = latest["source"] if latest else "None"
    latest_status = latest["handoff_status"] if latest else "None"
    latest_authorization = (
        latest["authorization_status"]
        if latest
        else "None"
    )

    ml_result = (
        latest.get("ml_result") or {}
        if latest
        else {}
    )

    ml_status = (
        latest["ml_status"]
        if latest
        else "None"
    )

    ml_anomalous = ml_result.get(
        "anomalous",
        "None",
    )

    ml_score = ml_result.get(
        "raw_decision_score",
        "None",
    )

    ml_model = ml_result.get(
        "model_version",
        "None",
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>LCNC Enterprise Discovery</title>
        <meta http-equiv="refresh" content="10">

        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 40px;
                max-width: 900px;
            }}

            .card {{
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 18px;
                margin-bottom: 16px;
            }}

            a {{
                margin-right: 18px;
            }}
        </style>
    </head>

    <body>
        <h1>LCNC Enterprise Discovery</h1>

        <div class="card">
            <strong>Status:</strong> Healthy<br>
            <strong>Version:</strong> enterprise-discovery-v2<br>
            <strong>Persistent discoveries:</strong> {count}
        </div>

        <div class="card">
            <h3>Latest Discovery</h3>
            <strong>Name:</strong> {latest_name}<br>
            <strong>Source:</strong> {latest_source}<br>
            <strong>Authorization:</strong> {latest_authorization}<br>
            <strong>Handoff:</strong> {latest_status}
        </div>

        <div class="card">
            <h3>ML Shadow IT Assessment</h3>
            <strong>Status:</strong> {ml_status}<br>
            <strong>Anomalous:</strong> {ml_anomalous}<br>
            <strong>Decision score:</strong> {ml_score}<br>
            <strong>Model:</strong> {ml_model}
        </div>

        <div class="card">
            <a href="/sources">Discovery Sources</a>
            <a href="/discoveries">Discovery Records</a>
            <a href="/docs">API Documentation</a>
            <a href="/health">Health</a>
        </div>
    </body>
    </html>
    """


@app.get("/health")
def health():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

    return {
        "status": "healthy",
        "service": "enterprise-discovery",
        "version": "enterprise-discovery-v2",
        "storage": "postgresql",
    }


@app.get("/sources")
def sources():
    return {
        "sources": SOURCES,
        "configured_sources": sum(
            1
            for source in SOURCES
            if source["configured"]
        ),
    }


@app.get("/discoveries")
def discoveries(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM enterprise_discoveries
                ORDER BY last_seen_at DESC
                LIMIT %s
                """,
                (limit,),
            )

            records = cursor.fetchall()

    return {
        "count": len(records),
        "discoveries": records,
    }


@app.post("/discoveries", status_code=201)
def create_discovery(payload: DiscoveryEvent):
    now = datetime.now(timezone.utc)

    observed_at = payload.observed_at or now

    record = {
        **payload.model_dump(
            exclude={"observed_at"}
        ),
        "observed_at": observed_at,
        "received_at": now,
    }

    ml = analyze_with_ml(record)

    if ml["status"] == "assessed":
        handoff_status = "ml_assessed"

    elif ml["status"] == "error":
        handoff_status = "ml_error"

    else:
        handoff_status = "ml_pending"

    ml_result = ml.get("result")

    discovery_id = str(uuid4())

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO enterprise_discoveries (
                    discovery_id,
                    source,
                    external_id,
                    name,
                    platform,
                    authorization_status,
                    owner_known,
                    business_purpose_known,
                    internet_exposed,
                    uses_api_key,
                    external_integration_count,
                    unapproved_integration_count,
                    connector_count,
                    external_domain_count,
                    changes_last_24h,
                    evidence,
                    handoff_status,
                    ml_status,
                    ml_result,
                    observed_at,
                    received_at,
                    last_seen_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (
                    source,
                    external_id
                )
                DO UPDATE SET
                    name = EXCLUDED.name,
                    platform = EXCLUDED.platform,
                    authorization_status =
                        EXCLUDED.authorization_status,
                    owner_known =
                        EXCLUDED.owner_known,
                    business_purpose_known =
                        EXCLUDED.business_purpose_known,
                    internet_exposed =
                        EXCLUDED.internet_exposed,
                    uses_api_key =
                        EXCLUDED.uses_api_key,
                    external_integration_count =
                        EXCLUDED.external_integration_count,
                    unapproved_integration_count =
                        EXCLUDED.unapproved_integration_count,
                    connector_count =
                        EXCLUDED.connector_count,
                    external_domain_count =
                        EXCLUDED.external_domain_count,
                    changes_last_24h =
                        EXCLUDED.changes_last_24h,
                    evidence =
                        EXCLUDED.evidence,
                    handoff_status =
                        EXCLUDED.handoff_status,
                    ml_status =
                        EXCLUDED.ml_status,
                    ml_result =
                        EXCLUDED.ml_result,
                    observed_at =
                        EXCLUDED.observed_at,
                    received_at =
                        EXCLUDED.received_at,
                    last_seen_at =
                        NOW()
                RETURNING *
                """,
                (
                    discovery_id,
                    payload.source,
                    payload.external_id,
                    payload.name,
                    payload.platform,
                    payload.authorization_status,
                    payload.owner_known,
                    payload.business_purpose_known,
                    payload.internet_exposed,
                    payload.uses_api_key,
                    payload.external_integration_count,
                    payload.unapproved_integration_count,
                    payload.connector_count,
                    payload.external_domain_count,
                    payload.changes_last_24h,
                    Jsonb(payload.evidence),
                    handoff_status,
                    ml["status"],
                    (
                        Jsonb(ml_result)
                        if ml_result is not None
                        else None
                    ),
                    observed_at,
                    now,
                    now,
                ),
            )

            stored = cursor.fetchone()

        connection.commit()

    stored["ml"] = ml

    return stored
