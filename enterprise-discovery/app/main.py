from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


app = FastAPI(
    title="LCNC Enterprise Discovery",
    version="0.1.0",
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


_lock = Lock()
_discoveries: list[dict] = []


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

@app.get("/", response_class=HTMLResponse)
def dashboard():
    with _lock:
        count = len(_discoveries)
        latest = _discoveries[-1] if _discoveries else None

    latest_name = latest["name"] if latest else "None"
    latest_source = latest["source"] if latest else "None"
    latest_status = latest["handoff_status"] if latest else "None"

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
            <strong>Version:</strong> enterprise-discovery-v1<br>
            <strong>Total discoveries:</strong> {count}
        </div>

        <div class="card">
            <strong>Latest discovery:</strong> {latest_name}<br>
            <strong>Source:</strong> {latest_source}<br>
            <strong>Handoff:</strong> {latest_status}
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
    return {
        "status": "healthy",
        "service": "enterprise-discovery",
        "version": "enterprise-discovery-v1",
    }


@app.get("/sources")
def sources():
    return {
        "sources": SOURCES,
        "configured_sources": sum(
            1 for source in SOURCES if source["configured"]
        ),
    }


@app.get("/discoveries")
def discoveries(
    limit: int = Query(default=50, ge=1, le=500),
):
    with _lock:
        records = list(reversed(_discoveries[-limit:]))

    return {
        "count": len(records),
        "discoveries": records,
    }


@app.post("/discoveries", status_code=201)
def create_discovery(payload: DiscoveryEvent):
    now = datetime.now(timezone.utc)

    record = {
        "discovery_id": str(uuid4()),
        **payload.model_dump(
            exclude={"observed_at"}
        ),
        "observed_at": (
            payload.observed_at or now
        ).isoformat(),
        "received_at": now.isoformat(),
        "handoff_status": "pending",
    }

    with _lock:
        _discoveries.append(record)

    return record
