import os
import sys
import time
from datetime import datetime, timezone

import httpx


APPSMITH_BASE_URL = os.getenv(
    "APPSMITH_BASE_URL",
    "http://appsmith",
)

APPSMITH_USER = os.environ["APPSMITH_USER"]
APPSMITH_PASSWORD = os.environ["APPSMITH_PASSWORD"]

GOVERNANCE_API_URL = os.getenv(
    "GOVERNANCE_API_URL",
    "http://governance-api:8000",
)

DISCOVERY_INTERVAL_SECONDS = int(
    os.getenv(
        "DISCOVERY_INTERVAL_SECONDS",
        "60",
    )
)

ANOMALY_REQUIRED_FIELDS = [
    "external_integration_count",
    "unapproved_integration_count",
    "connector_count",
    "external_domain_count",
    "changes_last_24h",
]

CLASSIFICATION_REQUIRED_FIELDS = [
    "business_purpose",
    "data_fields",
    "connector_metadata",
]


def login(client: httpx.Client):
    response = client.post(
        f"{APPSMITH_BASE_URL}/api/v1/login",
        headers={"X-Requested-By": "Appsmith"},
        data={
            "username": APPSMITH_USER,
            "password": APPSMITH_PASSWORD,
        },
    )

    response.raise_for_status()


def get_workspaces(client: httpx.Client):
    response = client.get(
        f"{APPSMITH_BASE_URL}/api/v1/workspaces/home"
    )

    response.raise_for_status()

    payload = response.json()

    if not payload.get(
        "responseMeta",
        {},
    ).get("success"):
        raise RuntimeError(
            "Failed to retrieve Appsmith workspaces"
        )

    return payload.get("data", [])


def get_applications(
    client: httpx.Client,
    workspace_id: str,
):
    response = client.get(
        f"{APPSMITH_BASE_URL}/api/v1/applications/home",
        params={
            "workspaceId": workspace_id
        },
    )

    response.raise_for_status()

    payload = response.json()

    if not payload.get(
        "responseMeta",
        {},
    ).get("success"):
        raise RuntimeError(
            "Failed to retrieve applications "
            f"for workspace {workspace_id}"
        )

    return payload.get("data", [])


def get_inventory():
    response = httpx.get(
        f"{GOVERNANCE_API_URL}/applications",
        timeout=10.0,
    )

    response.raise_for_status()

    return {
        application["external_id"]: application
        for application in response.json()
    }


def register_shadow_application(application):
    payload = {
        "external_id": application["id"],
        "name": application["name"],
        "platform": "appsmith",
        "registration_status": "unregistered",
        "lifecycle_status": "active",
        "data_classification": "unknown",
        "internet_exposed": bool(
            application.get(
                "isPublic",
                False,
            )
        ),
        "external_integration": None,
    }

    response = httpx.post(
        f"{GOVERNANCE_API_URL}/applications",
        json=payload,
        timeout=10.0,
    )

    if response.status_code == 201:
        return response.json()

    if response.status_code == 409:
        return None

    response.raise_for_status()


def mark_seen(application_id):
    response = httpx.patch(
        (
            f"{GOVERNANCE_API_URL}"
            f"/applications/{application_id}/seen"
        ),
        timeout=10.0,
    )

    response.raise_for_status()

    return response.json()


def trigger_anomaly_analysis(application):
    name = application["name"]

    if application.get(
        "ml_anomaly_status"
    ) == "assessed":
        return

    missing = [
        field
        for field in ANOMALY_REQUIRED_FIELDS
        if application.get(field) is None
    ]

    if missing:
        print(
            f"[ML-PENDING] {name}: "
            "anomaly metadata incomplete: "
            + ", ".join(missing),
            flush=True,
        )
        return

    try:
        response = httpx.post(
            (
                f"{GOVERNANCE_API_URL}"
                f"/applications/{application['id']}"
                "/ml-analyze"
            ),
            timeout=15.0,
        )

        response.raise_for_status()

        result = response.json()

        print(
            f"[ML-ANOMALY] {name}: "
            f"anomalous={result['anomalous']} "
            f"score={result['decision_score']} "
            f"model={result['model_version']}",
            flush=True,
        )

    except httpx.HTTPError as exc:
        print(
            f"[ML-ERROR] {name}: {exc}",
            file=sys.stderr,
            flush=True,
        )


def trigger_classification(application):
    name = application["name"]

    if application.get(
        "ml_classification_status"
    ) == "assessed":
        return

    missing = [
        field
        for field in CLASSIFICATION_REQUIRED_FIELDS
        if not application.get(field)
    ]

    if missing:
        print(
            f"[CLASSIFICATION-PENDING] {name}: "
            "content metadata incomplete: "
            + ", ".join(missing),
            flush=True,
        )
        return

    try:
        response = httpx.post(
            (
                f"{GOVERNANCE_API_URL}"
                f"/applications/{application['id']}"
                "/ml-classify"
            ),
            timeout=15.0,
        )

        response.raise_for_status()

        result = response.json()

        print(
            f"[ML-CLASSIFY] {name}: "
            f"suggested="
            f"{result['suggested_classification']} "
            f"confidence={result['confidence']} "
            f"review_required="
            f"{result['review_required']}",
            flush=True,
        )

    except httpx.HTTPError as exc:
        print(
            f"[CLASSIFICATION-ERROR] "
            f"{name}: {exc}",
            file=sys.stderr,
            flush=True,
        )


def trigger_security_scan(application):
    name = application["name"]

    if application.get(
        "security_scan_status"
    ) == "scanned":
        return

    required_fields = [
        "external_integration_count",
        "unapproved_integration_count",
        "connector_metadata",
    ]

    missing = [
        field
        for field in required_fields
        if application.get(field) is None
        or (
            isinstance(
                application.get(field),
                str,
            )
            and not application.get(field).strip()
        )
    ]

    if missing:
        print(
            f"[SCAN-PENDING] {name}: "
            "security metadata incomplete: "
            + ", ".join(missing),
            flush=True,
        )
        return

    try:
        response = httpx.post(
            (
                f"{GOVERNANCE_API_URL}"
                f"/applications/{application['id']}"
                "/security-scan"
            ),
            timeout=15.0,
        )

        response.raise_for_status()
        result = response.json()

        print(
            f"[SECURITY-SCAN] {name}: "
            f"passed={result['passed']} "
            f"findings={result['finding_count']} "
            f"highest={result['highest_severity']}",
            flush=True,
        )

    except httpx.HTTPError as exc:
        print(
            f"[SCAN-ERROR] {name}: {exc}",
            file=sys.stderr,
            flush=True,
        )


def trigger_security_scan(application):
    name = application["name"]

    if application.get(
        "security_scan_status"
    ) == "scanned":
        return

    required_fields = [
        "external_integration_count",
        "unapproved_integration_count",
        "connector_metadata",
    ]

    missing = [
        field
        for field in required_fields
        if application.get(field) is None
        or (
            isinstance(
                application.get(field),
                str,
            )
            and not application.get(field).strip()
        )
    ]

    if missing:
        print(
            f"[SCAN-PENDING] {name}: "
            "security metadata incomplete: "
            + ", ".join(missing),
            flush=True,
        )
        return

    try:
        response = httpx.post(
            (
                f"{GOVERNANCE_API_URL}"
                f"/applications/{application['id']}"
                "/security-scan"
            ),
            timeout=15.0,
        )

        response.raise_for_status()
        result = response.json()

        print(
            f"[SECURITY-SCAN] {name}: "
            f"passed={result['passed']} "
            f"findings={result['finding_count']} "
            f"highest={result['highest_severity']}",
            flush=True,
        )

    except httpx.HTTPError as exc:
        print(
            f"[SCAN-ERROR] {name}: {exc}",
            file=sys.stderr,
            flush=True,
        )


def run_ai_pipeline(application):
    trigger_anomaly_analysis(application)
    trigger_classification(application)
    trigger_security_scan(application)
    trigger_security_scan(application)


def run_discovery_cycle():
    started_at = datetime.now(
        timezone.utc
    ).isoformat()

    print()
    print(
        f"=== Appsmith Discovery Cycle {started_at} ===",
        flush=True,
    )

    with httpx.Client(
        follow_redirects=True,
        timeout=15.0,
    ) as client:

        login(client)

        workspaces = get_workspaces(client)
        inventory = get_inventory()

        discovered = 0
        known = 0
        shadow = 0

        for workspace in workspaces:
            workspace_id = workspace["id"]

            applications = get_applications(
                client,
                workspace_id,
            )

            for application in applications:
                discovered += 1

                external_id = application["id"]
                name = application["name"]

                if external_id in inventory:
                    known += 1

                    record = mark_seen(
                        inventory[
                            external_id
                        ]["id"]
                    )

                    print(
                        f"[KNOWN]  {name} "
                        f"({external_id})",
                        flush=True,
                    )

                else:
                    shadow += 1

                    print(
                        f"[SHADOW] {name} "
                        f"({external_id})",
                        flush=True,
                    )

                    record = (
                        register_shadow_application(
                            application
                        )
                    )

                    if record is None:
                        refreshed = get_inventory()
                        record = refreshed.get(
                            external_id
                        )

                if record is not None:
                    run_ai_pipeline(record)

        print(
            "=== Discovery Summary ===",
            flush=True,
        )

        print(
            f"Discovered: {discovered}",
            flush=True,
        )

        print(
            f"Known:      {known}",
            flush=True,
        )

        print(
            f"Shadow:     {shadow}",
            flush=True,
        )


def main():
    print(
        "=== Continuous Appsmith Discovery ===",
        flush=True,
    )

    print(
        "Discovery interval: "
        f"{DISCOVERY_INTERVAL_SECONDS} seconds",
        flush=True,
    )

    while True:
        try:
            run_discovery_cycle()

        except Exception as exc:
            print(
                f"[ERROR] Discovery cycle failed: {exc}",
                file=sys.stderr,
                flush=True,
            )

        time.sleep(
            DISCOVERY_INTERVAL_SECONDS
        )


if __name__ == "__main__":
    main()
