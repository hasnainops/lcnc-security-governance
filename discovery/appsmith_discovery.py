import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


APPSMITH_BASE_URL = os.getenv(
    "APPSMITH_BASE_URL",
    "http://appsmith",
)

VAULT_ADDR = os.getenv(
    "VAULT_ADDR",
    "http://vault:8200",  # NOSONAR - local Docker-internal Vault transport; production requires TLS/mTLS
).rstrip("/")

VAULT_ROLE_ID = os.getenv("VAULT_ROLE_ID")

VAULT_SECRET_ID_FILE = os.getenv(
    "VAULT_SECRET_ID_FILE"
)

APPSMITH_VAULT_SECRET_PATH = os.getenv(
    "APPSMITH_VAULT_SECRET_PATH",
    "secret/data/integrations/appsmith",
)

_vault_token = None
_vault_token_valid_until = 0.0

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


def _read_vault_secret_id():
    if not VAULT_SECRET_ID_FILE:
        raise RuntimeError(
            "VAULT_SECRET_ID_FILE is required."
        )

    try:
        secret_id = Path(
            VAULT_SECRET_ID_FILE
        ).read_text().strip()
    except OSError as exc:
        raise RuntimeError(
            "Unable to read Vault SecretID file."
        ) from exc

    if not secret_id:
        raise RuntimeError(
            "Vault SecretID file is empty."
        )

    return secret_id


def _vault_login():
    global _vault_token
    global _vault_token_valid_until

    if not VAULT_ROLE_ID:
        raise RuntimeError(
            "VAULT_ROLE_ID is required."
        )

    response = httpx.post(
        f"{VAULT_ADDR}/v1/auth/approle/login",
        json={
            "role_id": VAULT_ROLE_ID,
            "secret_id": _read_vault_secret_id(),
        },
        timeout=5,
    )

    response.raise_for_status()

    auth = response.json().get("auth", {})

    token = auth.get("client_token")
    ttl = int(auth.get("lease_duration") or 0)

    if not token or ttl <= 0:
        raise RuntimeError(
            "Vault AppRole authentication returned "
            "an invalid token or TTL."
        )

    _vault_token = token

    _vault_token_valid_until = (
        time.monotonic()
        + max(30, ttl - 60)
    )

    return token


def _get_vault_token():
    global _vault_token
    global _vault_token_valid_until

    if (
        _vault_token
        and time.monotonic()
        < _vault_token_valid_until
    ):
        return _vault_token

    if _vault_token:
        try:
            response = httpx.post(
                (
                    f"{VAULT_ADDR}"
                    "/v1/auth/token/renew-self"
                ),
                headers={
                    "X-Vault-Token": _vault_token,
                },
                json={},
                timeout=5,
            )

            response.raise_for_status()

            auth = response.json().get(
                "auth",
                {}
            )

            ttl = int(
                auth.get("lease_duration")
                or 0
            )

            if ttl > 0:
                _vault_token_valid_until = (
                    time.monotonic()
                    + max(30, ttl - 60)
                )

                return _vault_token

        except httpx.HTTPError:
            _vault_token = None
            _vault_token_valid_until = 0.0

    return _vault_login()


def get_appsmith_credentials():
    token = _get_vault_token()

    response = httpx.get(
        (
            f"{VAULT_ADDR}/v1/"
            f"{APPSMITH_VAULT_SECRET_PATH}"
        ),
        headers={
            "X-Vault-Token": token,
        },
        timeout=5,
    )

    response.raise_for_status()

    payload = response.json()

    secret = (
        payload
        .get("data", {})
        .get("data", {})
    )

    username = secret.get("username")
    password = secret.get("password")

    if not username or not password:
        raise RuntimeError(
            "Vault Appsmith credential is incomplete."
        )

    return username, password


def login(client: httpx.Client):
    username, password = (
        get_appsmith_credentials()
    )

    response = client.post(
        f"{APPSMITH_BASE_URL}/api/v1/login",
        headers={"X-Requested-By": "Appsmith"},
        data={
            "username": username,
            "password": password,
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


SENSITIVE_HEADER_NAMES = {
    "authorization",
    "x-api-key",
    "api-key",
    "token",
    "access-token",
}


def _count_widgets(node):
    if not isinstance(node, dict):
        return 0

    total = 0

    for child in node.get("children", []):
        if not isinstance(child, dict):
            continue

        total += 1
        total += _count_widgets(child)

    return total


def _new_workflow_security_metadata():
    return {
        "page_count": 0,
        "widget_count": 0,
        "action_count": 0,
        "api_action_count": 0,
        "dynamic_binding_count": 0,
        "invalid_action_count": 0,
        "http_action_count": 0,
        "https_action_count": 0,
        "sensitive_header_action_count": 0,
    }


def _get_page_data(
    client: httpx.Client,
    page_id: str,
):
    response = client.get(
        (
            f"{APPSMITH_BASE_URL}"
            f"/api/v1/pages/{page_id}"
        )
    )
    response.raise_for_status()

    return (
        response
        .json()
        .get("data", {})
    )


def _get_page_actions(
    client: httpx.Client,
    page_id: str,
):
    response = client.get(
        (
            f"{APPSMITH_BASE_URL}"
            "/api/v1/actions"
        ),
        params={
            "pageId": page_id,
        },
    )
    response.raise_for_status()

    return (
        response
        .json()
        .get("data", [])
    )


def _count_page_widgets(page_data: dict):
    total = 0

    for layout in page_data.get(
        "layouts",
        [],
    ):
        total += _count_widgets(
            layout.get("dsl", {})
        )

    return total


def _extract_action_url(action: dict):
    datasource = action.get(
        "datasource",
        {},
    )

    if not isinstance(datasource, dict):
        return None

    config = datasource.get(
        "datasourceConfiguration"
    )

    if not isinstance(config, dict):
        return None

    for key in (
        "url",
        "endpoint",
        "host",
    ):
        value = config.get(key)

        if isinstance(value, str) and value:
            return value

    return None


def _record_transport_metadata(
    metadata: dict,
    raw_url,
):
    if not isinstance(raw_url, str):
        return

    normalized_url = (
        raw_url
        .strip()
        .lower()
    )

    if normalized_url.startswith(
        "http://"  # NOSONAR - intentionally detects insecure HTTP metadata
    ):
        metadata[
            "http_action_count"
        ] += 1

    elif normalized_url.startswith(
        "https://"
    ):
        metadata[
            "https_action_count"
        ] += 1


def _has_sensitive_header(action: dict):
    config = action.get(
        "actionConfiguration",
        {},
    )

    headers = (
        config.get("headers", [])
        if isinstance(config, dict)
        else []
    )

    if not isinstance(headers, list):
        return False

    for header in headers:
        if not isinstance(header, dict):
            continue

        name = (
            header.get("key")
            or header.get("name")
        )

        if (
            isinstance(name, str)
            and name.lower()
            in SENSITIVE_HEADER_NAMES
        ):
            return True

    return False


def _record_action_metadata(
    metadata: dict,
    action: dict,
):
    metadata["action_count"] += 1

    if action.get("pluginType") == "API":
        metadata[
            "api_action_count"
        ] += 1

    metadata[
        "dynamic_binding_count"
    ] += len(
        action.get(
            "dynamicBindingPathList",
            [],
        )
    )

    if action.get("isValid") is False:
        metadata[
            "invalid_action_count"
        ] += 1

    _record_transport_metadata(
        metadata,
        _extract_action_url(action),
    )

    if _has_sensitive_header(action):
        metadata[
            "sensitive_header_action_count"
        ] += 1


def _collect_page_security_metadata(
    client: httpx.Client,
    page_id: str,
    metadata: dict,
):
    page_data = _get_page_data(
        client,
        page_id,
    )

    metadata[
        "widget_count"
    ] += _count_page_widgets(
        page_data
    )

    for action in _get_page_actions(
        client,
        page_id,
    ):
        _record_action_metadata(
            metadata,
            action,
        )


def collect_workflow_security_metadata(
    client: httpx.Client,
    application: dict,
):
    """Collect sanitized Appsmith workflow security evidence.

    Only aggregate security counts are returned. Raw URLs,
    request bodies, header values, bindings, tokens, and
    credentials are never returned.
    """

    metadata = (
        _new_workflow_security_metadata()
    )

    pages = application.get(
        "pages",
        [],
    )

    metadata["page_count"] = len(pages)

    for page in pages:
        _collect_page_security_metadata(
            client,
            page["id"],
            metadata,
        )

    return metadata

def send_workflow_security_metadata(
    application_id: str,
    metadata: dict,
):
    """Send sanitized observed workflow evidence to Governance."""

    response = httpx.post(
        (
            f"{GOVERNANCE_API_URL}"
            f"/applications/{application_id}"
            "/observed-workflow-security"
        ),
        json=metadata,
        timeout=10.0,
    )

    response.raise_for_status()

    return response.json()


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

    workflow_observed = (
        application.get(
            "workflow_security_metadata"
        )
        is not None
    )

    if missing and not workflow_observed:
        print(
            f"[SCAN-PENDING] {name}: "
            "security metadata incomplete: "
            + ", ".join(missing),
            flush=True,
        )
        return

    if missing and workflow_observed:
        print(
            f"[SCAN-PARTIAL] {name}: "
            "workflow evidence available; "
            "integration-dependent rules "
            "not evaluable: "
            + ", ".join(missing),
            flush=True,
        )

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
                    workflow_metadata = (
                        collect_workflow_security_metadata(
                            client,
                            application,
                        )
                    )

                    record = (
                        send_workflow_security_metadata(
                            record["id"],
                            workflow_metadata,
                        )
                    )

                    print(
                        f"[WORKFLOW-OBSERVED] {name}: "
                        f"pages="
                        f"{workflow_metadata['page_count']} "
                        f"widgets="
                        f"{workflow_metadata['widget_count']} "
                        f"actions="
                        f"{workflow_metadata['action_count']} "
                        f"http_actions="
                        f"{workflow_metadata['http_action_count']}",
                        flush=True,
                    )

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
