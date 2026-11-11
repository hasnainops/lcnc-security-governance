import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from discovery_health import clear_success, record_success


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



def extract_page_field_evidence(page_data: dict):
    """Extract structural field identifiers from Appsmith widget DSL.

    Never return widget values, binding expressions, query text,
    request bodies, credentials, or arbitrary widget properties.

    Evidence is scoped to inspected widget DSL, not complete
    underlying database schemas.
    """
    import re

    def safe_identifier(value):
        if not isinstance(value, str):
            return None

        if not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]{0,63}",
            value,
        ):
            return None

        return value

    layouts = page_data.get("layouts")

    if not isinstance(layouts, list) or not layouts:
        return {
            "coverage": "uncollected",
            "scope": "appsmith_widget_dsl",
            "field_identifiers": [],
            "widgets_inspected": 0,
            "dynamic_bindings_detected": 0,
        }

    fields = set()
    widgets_inspected = 0
    dynamic_bindings = 0

    for layout in layouts:
        if not isinstance(layout, dict):
            raise RuntimeError("Invalid Appsmith layout")

        root = layout.get("dsl")

        if not isinstance(root, dict):
            raise RuntimeError("Invalid Appsmith widget DSL")

        stack = [root]

        while stack:
            node = stack.pop()

            if not isinstance(node, dict):
                raise RuntimeError("Invalid Appsmith widget node")

            widgets_inspected += 1

            if widgets_inspected > 5000:
                raise RuntimeError(
                    "Appsmith widget inspection limit exceeded"
                )

            widget_type = node.get("widgetType", "")

            if not isinstance(widget_type, str):
                raise RuntimeError("Invalid widget type")

            widget_type = widget_type.upper()

            bindings = node.get("dynamicBindingPathList", [])

            if not isinstance(bindings, list):
                raise RuntimeError(
                    "Invalid dynamic binding metadata"
                )

            dynamic_bindings += len(bindings)

            # Table column identifiers are structural keys.
            # Do not inspect computedValue or tableData.
            if "TABLE" in widget_type:
                columns = node.get("primaryColumns", {})

                if not isinstance(columns, dict):
                    raise RuntimeError(
                        "Invalid table column metadata"
                    )

                for column_key in columns:
                    identifier = safe_identifier(column_key)

                    if identifier:
                        fields.add(identifier)

            # Explicit form/input field keys, not labels,
            # displayed values, or arbitrary widget names.
            if any(
                kind in widget_type
                for kind in (
                    "INPUT",
                    "FORM",
                    "SELECT",
                    "CHECKBOX",
                    "RADIO",
                    "DATE_PICKER",
                )
            ):
                for property_name in (
                    "fieldName",
                    "fieldKey",
                    "inputKey",
                ):
                    identifier = safe_identifier(
                        node.get(property_name)
                    )

                    if identifier:
                        fields.add(identifier)

            children = node.get("children", [])

            if not isinstance(children, list):
                raise RuntimeError(
                    "Invalid widget children"
                )

            stack.extend(children)

    return {
        "coverage": (
            "partial"
            if fields or dynamic_bindings
            else "none_observed"
        ),
        "scope": "appsmith_widget_dsl",
        "field_identifiers": sorted(fields),
        "widgets_inspected": widgets_inspected,
        "dynamic_bindings_detected": dynamic_bindings,
    }



def aggregate_page_field_evidence(
    application: dict,
    page_field_evidence: list,
):
    """Aggregate sanitized widget evidence across Appsmith pages.

    Coverage is limited to inspected widget DSL.
    It does not certify underlying database schemas.
    """
    import re

    pages = application.get("pages")

    if not isinstance(pages, list):
        raise RuntimeError("Invalid application page listing")

    expected_ids = []

    for page in pages:
        if not isinstance(page, dict):
            raise RuntimeError("Invalid Appsmith page")

        page_id = page.get("id")

        if not isinstance(page_id, str) or not page_id:
            raise RuntimeError("Missing Appsmith page identity")

        expected_ids.append(page_id)

    if len(expected_ids) != len(set(expected_ids)):
        raise RuntimeError("Duplicate application page identity")

    if not isinstance(page_field_evidence, list):
        raise RuntimeError("Invalid page field evidence")

    collected = {}

    for item in page_field_evidence:
        if not isinstance(item, dict):
            raise RuntimeError("Invalid field evidence record")

        page_id = item.get("page_id")

        if (
            not isinstance(page_id, str)
            or page_id in collected
        ):
            raise RuntimeError(
                "Invalid or duplicate field evidence page"
            )

        if item.get("scope") != "appsmith_widget_dsl":
            raise RuntimeError("Unexpected field evidence scope")

        if item.get("coverage") not in {
            "partial",
            "none_observed",
            "uncollected",
        }:
            raise RuntimeError("Invalid field coverage")

        identifiers = item.get("field_identifiers")

        if not isinstance(identifiers, list):
            raise RuntimeError("Invalid field identifiers")

        for identifier in identifiers:
            if (
                not isinstance(identifier, str)
                or not re.fullmatch(
                    r"[A-Za-z][A-Za-z0-9_]{0,63}",
                    identifier,
                )
            ):
                raise RuntimeError(
                    "Unsafe field identifier"
                )

        for key in (
            "widgets_inspected",
            "dynamic_bindings_detected",
        ):
            value = item.get(key)

            if type(value) is not int or value < 0:
                raise RuntimeError(
                    "Invalid field evidence count"
                )

        collected[page_id] = item

    if set(collected) != set(expected_ids):
        raise RuntimeError(
            "Page field evidence does not match application pages"
        )

    fields = set()
    widgets = 0
    bindings = 0
    inspected_pages = 0

    for item in collected.values():
        fields.update(item["field_identifiers"])
        widgets += item["widgets_inspected"]
        bindings += item["dynamic_bindings_detected"]

        if item["coverage"] != "uncollected":
            inspected_pages += 1

    if inspected_pages == 0:
        coverage = "uncollected"
    elif (
        inspected_pages != len(expected_ids)
        or fields
        or bindings
    ):
        coverage = "partial"
    else:
        coverage = "none_observed"

    return {
        "scope": "appsmith_widget_dsl",
        "coverage": coverage,
        "field_identifiers": sorted(fields),
        "pages_expected": len(expected_ids),
        "pages_inspected": inspected_pages,
        "widgets_inspected": widgets,
        "dynamic_bindings_detected": bindings,
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


def _validated_observation_data(payload, expected_type, *, require_response_meta=False):
    """Reject malformed observations without exposing upstream content."""
    message = "Invalid Appsmith observation response"

    if not isinstance(payload, dict):
        raise RuntimeError(message)

    if require_response_meta and (
        not isinstance(payload.get("responseMeta"), dict)
        or payload["responseMeta"].get("success") is not True
    ):
        raise RuntimeError(message)

    if "responseMeta" in payload:
        meta = payload["responseMeta"]
        if not isinstance(meta, dict) or meta.get("success") is not True:
            raise RuntimeError(message)

    data = payload.get("data")
    if not isinstance(data, expected_type):
        raise RuntimeError(message)

    if expected_type is dict and not data:
        raise RuntimeError(message)

    if expected_type is list and any(
        not isinstance(item, dict) for item in data
    ):
        raise RuntimeError(message)

    return data


def _get_workspace_datasources(
    client: httpx.Client,
    workspace_id: str,
):
    """Retrieve verified saved datasource identities from Appsmith."""

    response = client.get(
        f"{APPSMITH_BASE_URL}/api/v1/datasources",
        params={"workspaceId": workspace_id},
    )

    response.raise_for_status()
    payload = response.json()

    if (
        not isinstance(payload, dict)
        or payload.get("responseMeta", {}).get("success") is not True
    ):
        raise RuntimeError(
            "Appsmith datasource enumeration was unsuccessful"
        )

    datasources = _validated_observation_data(
        payload, list
    )

    identities = set()

    for datasource in datasources:
        if not isinstance(datasource, dict):
            raise RuntimeError(
                "Invalid Appsmith datasource record"
            )

        datasource_id = datasource.get("id")

        if (
            not isinstance(datasource_id, str)
            or not datasource_id.strip()
        ):
            raise RuntimeError(
                "Appsmith datasource identity missing"
            )

        if datasource_id in identities:
            raise RuntimeError(
                "Duplicate Appsmith datasource identity"
            )

        datasource_workspace = datasource.get("workspaceId")

        if (
            datasource_workspace is not None
            and datasource_workspace != workspace_id
        ):
            raise RuntimeError(
                "Appsmith datasource workspace mismatch"
            )

        identities.add(datasource_id)

    return datasources


def _get_page_data(client: httpx.Client, page_id: str):
    response = client.get(
        f"{APPSMITH_BASE_URL}/api/v1/pages/{page_id}"
    )
    response.raise_for_status()
    return _validated_observation_data(response.json(), dict, require_response_meta=True)


def _get_page_actions(
    client: httpx.Client,
    page_id: str,
):
    response = client.get(
        f"{APPSMITH_BASE_URL}/api/v1/actions",
        params={"pageId": page_id},
    )
    response.raise_for_status()
    return _validated_observation_data(response.json(), list, require_response_meta=True)


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


def _sanitize_action_observation(action: dict):
    """Extract action identity and sanitized HTTP destination evidence."""
    import re
    from ipaddress import ip_address
    from urllib.parse import urlsplit

    action_id = action.get("id")

    if (
        not isinstance(action_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,255}", action_id)
    ):
        raise RuntimeError("Invalid Appsmith action identity")

    result = {
        "action_id": action_id,
        "destination_state": "unresolved",
        "uses_api_key": None,
    }

    raw_url = _extract_action_url(action)

    if not isinstance(raw_url, str) or not raw_url.strip():
        return result

    try:
        parsed = urlsplit(raw_url.strip())
        host = parsed.hostname
        port = parsed.port

        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
        ):
            return result

        host = host.lower().rstrip(".")

        if not host.isascii() or "%" in host:
            return result

        try:
            ip_address(host)
        except ValueError:
            label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
            if (
                len(host) > 253
                or not all(
                    re.fullmatch(label, part)
                    for part in host.split(".")
                )
            ):
                return result

    except ValueError:
        return result

    destination = {
        "scheme": parsed.scheme,
        "host": host,
    }

    if port is not None:
        destination["port"] = port

    result["destination_state"] = "observed"
    result["destination"] = destination

    return result


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
    observed_actions: list | None = None,
    action_datasource_refs: list | None = None,
    page_field_evidence: list | None = None,
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

    if page_field_evidence is not None:
        evidence = extract_page_field_evidence(page_data)
        page_field_evidence.append({
            "page_id": page_id,
            **evidence,
        })

    for action in _get_page_actions(
        client,
        page_id,
    ):
        _record_action_metadata(
            metadata,
            action,
        )
        if observed_actions is not None:
            observed_actions.append(
                _sanitize_action_observation(action)
            )
        if action_datasource_refs is not None:
            datasource = action.get("datasource")

            if not isinstance(datasource, dict):
                datasource = {}

            datasource_id = datasource.get("id")

            action_datasource_refs.append({
                "action_id": action.get("id"),
                "datasource_id": (
                    datasource_id
                    if isinstance(datasource_id, str)
                    and datasource_id.strip()
                    else None
                ),
                "plugin_type": action.get("pluginType"),
            })


def collect_workflow_security_metadata(
    client: httpx.Client,
    application: dict,
    observed_actions: list | None = None,
    action_datasource_refs: list | None = None,
    page_field_evidence: list | None = None,
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

    if not isinstance(application.get("pages"), list):
        raise RuntimeError("Invalid Appsmith application page listing")

    page_ids = []

    for page in pages:
        if not isinstance(page, dict):
            raise RuntimeError("Invalid Appsmith page record")

        page_id = page.get("id")

        if not isinstance(page_id, str) or not page_id.strip():
            raise RuntimeError("Missing Appsmith page identity")

        page_ids.append(page_id)

    if len(page_ids) != len(set(page_ids)):
        raise RuntimeError("Duplicate Appsmith page identity")

    metadata["page_count"] = len(pages)

    for page in pages:
        _collect_page_security_metadata(
            client,
            page["id"],
            metadata,
            observed_actions,
            action_datasource_refs,
            page_field_evidence,
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


def reconcile_action_datasources(
    workspace_datasources,
    action_datasource_refs,
):
    """Match actions only to verified saved datasource identities.

    Never infer connector identities from action or plugin counts.
    None means workspace datasource enumeration failed.
    """

    enumeration_succeeded = workspace_datasources is not None

    saved_ids = set()

    if enumeration_succeeded:
        if not isinstance(workspace_datasources, list):
            raise RuntimeError("Invalid workspace datasource collection")

        for datasource in workspace_datasources:
            if not isinstance(datasource, dict):
                raise RuntimeError("Invalid datasource record")

            datasource_id = datasource.get("id")

            if not isinstance(datasource_id, str) or not datasource_id:
                raise RuntimeError("Missing datasource identity")

            if datasource_id in saved_ids:
                raise RuntimeError("Duplicate datasource identity")

            saved_ids.add(datasource_id)

    if not isinstance(action_datasource_refs, list):
        raise RuntimeError("Invalid action reference collection")

    referenced_ids = set()
    unbound_action_ids = set()
    seen_action_ids = set()

    for entry in action_datasource_refs:
        if not isinstance(entry, dict):
            raise RuntimeError("Invalid action reference")

        action_id = entry.get("action_id")
        datasource_id = entry.get("datasource_id")

        if not isinstance(action_id, str) or not action_id:
            raise RuntimeError("Missing action identity")

        if action_id in seen_action_ids:
            raise RuntimeError("Duplicate action identity")

        seen_action_ids.add(action_id)

        if datasource_id is None:
            unbound_action_ids.add(action_id)
        elif isinstance(datasource_id, str) and datasource_id:
            referenced_ids.add(datasource_id)
        else:
            raise RuntimeError("Invalid referenced datasource identity")

    verified_ids = (
        referenced_ids & saved_ids
        if enumeration_succeeded
        else set()
    )

    unverified_ids = referenced_ids - verified_ids

    return {
        "datasource_enumeration_succeeded": enumeration_succeeded,
        "verified_saved_datasource_ids": sorted(verified_ids),
        "unverified_referenced_datasource_ids": sorted(
            unverified_ids
        ),
        "actions_without_datasource_id": sorted(
            unbound_action_ids
        ),
    }


def evaluate_collection_evidence(
    application,
    observed_actions,
    action_datasource_refs,
    workspace_datasources,
    datasource_reconciliation,
):
    """Evaluate verified Appsmith collection evidence conservatively."""

    reasons = []

    pages = application.get("pages")
    page_ids = []

    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                break
            page_id = page.get("id")
            if not isinstance(page_id, str) or not page_id:
                break
            page_ids.append(page_id)

    if (
        not isinstance(pages, list)
        or len(page_ids) != len(pages)
        or len(set(page_ids)) != len(page_ids)
    ):
        reasons.append("pages_incomplete")

    action_ids = []
    reference_ids = []

    if isinstance(observed_actions, list):
        action_ids = [
            item.get("action_id")
            for item in observed_actions
            if isinstance(item, dict)
        ]

    if isinstance(action_datasource_refs, list):
        reference_ids = [
            item.get("action_id")
            for item in action_datasource_refs
            if isinstance(item, dict)
        ]

    if (
        not isinstance(observed_actions, list)
        or not isinstance(action_datasource_refs, list)
        or len(action_ids) != len(observed_actions)
        or len(reference_ids) != len(action_datasource_refs)
        or not all(isinstance(x, str) and x for x in action_ids)
        or len(set(action_ids)) != len(action_ids)
        or len(set(reference_ids)) != len(reference_ids)
        or set(action_ids) != set(reference_ids)
    ):
        reasons.append("actions_incomplete")

    if (
        not isinstance(workspace_datasources, list)
        or not isinstance(datasource_reconciliation, dict)
        or datasource_reconciliation.get(
            "datasource_enumeration_succeeded"
        ) is not True
    ):
        reasons.append("datasources_incomplete")

    elif (
        datasource_reconciliation.get(
            "unverified_referenced_datasource_ids"
        )
        or datasource_reconciliation.get(
            "actions_without_datasource_id"
        )
    ):
        # Verified saved datasource identities do not make
        # otherwise complete collection evidence incomplete.
        # Unverified or missing datasource identities still block.
        reasons.append("connector_identity_unresolved")

    return {
        "collection_complete": not reasons,
        "pending_reasons": reasons,
    }


def build_verified_saved_connector_evidence(
    workspace_datasources,
    reconciliation,
):
    """Build sanitized evidence for application-referenced datasources.

    A verified datasource ID proves identity, not its destination,
    security approval, or whether it uses credentials.
    """

    if (
        workspace_datasources is None
        or reconciliation is None
    ):
        return []

    if (
        not isinstance(workspace_datasources, list)
        or not isinstance(reconciliation, dict)
        or reconciliation.get(
            "datasource_enumeration_succeeded"
        ) is not True
    ):
        raise RuntimeError("Invalid datasource evidence")

    saved_ids = set()

    for datasource in workspace_datasources:
        if not isinstance(datasource, dict):
            raise RuntimeError("Invalid saved datasource")

        datasource_id = datasource.get("id")

        if (
            not isinstance(datasource_id, str)
            or not datasource_id
            or datasource_id in saved_ids
        ):
            raise RuntimeError("Invalid datasource identity")

        saved_ids.add(datasource_id)

    verified = reconciliation.get(
        "verified_saved_datasource_ids"
    )

    if (
        not isinstance(verified, list)
        or any(
            not isinstance(item, str) or not item
            for item in verified
        )
        or len(set(verified)) != len(verified)
        or not set(verified).issubset(saved_ids)
    ):
        raise RuntimeError("Invalid verified datasource references")

    return [
        {
            "connector_id": datasource_id,
            "destination_state": "unresolved",
            "uses_api_key": None,
        }
        for datasource_id in sorted(verified)
    ]


def group_inline_api_evidence(
    observed_actions,
    action_datasource_refs,
):
    """Group inline HTTP destinations without assigning connector IDs."""

    if not isinstance(observed_actions, list):
        raise RuntimeError("Invalid action observations")

    if not isinstance(action_datasource_refs, list):
        raise RuntimeError("Invalid action references")

    references = {}

    for entry in action_datasource_refs:
        if not isinstance(entry, dict):
            raise RuntimeError("Invalid action reference")

        action_id = entry.get("action_id")

        if (
            not isinstance(action_id, str)
            or not action_id
            or action_id in references
        ):
            raise RuntimeError("Invalid or duplicate action identity")

        references[action_id] = entry

    groups = {}
    unresolved = []
    seen = set()
    inline_count = 0

    for action in observed_actions:
        if not isinstance(action, dict):
            raise RuntimeError("Invalid observed action")

        action_id = action.get("action_id")

        if (
            not isinstance(action_id, str)
            or action_id in seen
            or action_id not in references
        ):
            raise RuntimeError("Invalid action relationship")

        seen.add(action_id)
        reference = references[action_id]

        if (
            reference.get("datasource_id") is not None
            or reference.get("plugin_type") != "API"
        ):
            continue

        inline_count += 1
        state = action.get("destination_state")

        if state == "observed":
            destination = action.get("destination")

            if not isinstance(destination, dict):
                raise RuntimeError("Missing observed destination")

            scheme = destination.get("scheme")
            host = destination.get("host")
            port = destination.get("port")

            if (
                scheme not in {"http", "https"}
                or not isinstance(host, str)
                or not host
                or (
                    port is not None
                    and (
                        type(port) is not int
                        or not 1 <= port <= 65535
                    )
                )
            ):
                raise RuntimeError("Invalid destination evidence")

            origin = (scheme, host, port)
            groups.setdefault(origin, []).append(action_id)

        elif state in {"unresolved", "unsupported"}:
            unresolved.append(action_id)

        else:
            raise RuntimeError("Invalid destination state")

    if seen != set(references):
        raise RuntimeError("Action evidence coverage mismatch")

    origins = [
        {
            "scheme": scheme,
            "host": host,
            "port": port,
            "action_ids": sorted(action_ids),
        }
        for (scheme, host, port), action_ids
        in sorted(
            groups.items(),
            key=lambda item: (
                item[0][0],
                item[0][1],
                item[0][2] or 0,
            ),
        )
    ]

    return {
        "inline_action_count": inline_count,
        "observed_origin_count": len(origins),
        "origins": origins,
        "unresolved_action_ids": sorted(unresolved),
    }


def build_appsmith_observation(application, observed_actions):
    """Build evidence without inventing connector identities."""

    pending_reasons = ["datasources_incomplete"]

    if observed_actions:
        pending_reasons.append("connector_identity_unresolved")

    return {
        "contract_version": "appsmith-observation-v1",
        "source": "appsmith",
        "external_id": application["id"],
        "collector_version": "appsmith-discovery-v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "collection_complete": False,
        "pending_reasons": pending_reasons,
        "connectors": [],
        "page_ids": sorted(
            page["id"] for page in application["pages"]
        ),
        "observed_actions": observed_actions,
    }


def send_appsmith_observation(application_id, observation):
    """Submit sanitized observation to existing Governance API."""

    response = httpx.post(
        (
            f"{GOVERNANCE_API_URL}"
            f"/applications/{application_id}"
            "/discovery-observations"
        ),
        json=observation,
        timeout=10.0,
    )

    response.raise_for_status()
    return response.json()


def request_risk_assessment_if_needed(application_id):
    """Request risk scoring independently of ML readiness."""

    response = httpx.post(
        (
            f"{GOVERNANCE_API_URL}"
            f"/applications/{application_id}"
            "/assess-if-needed"
        ),
        timeout=15.0,
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

            try:
                workspace_datasources = _get_workspace_datasources(
                    client,
                    workspace_id,
                )
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                workspace_datasources = None
                print(
                    "[DATASOURCE-PENDING] "
                    f"type={type(exc).__name__}",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(
                    "[DATASOURCE-ENUMERATED] "
                    f"saved={len(workspace_datasources)}",
                    flush=True,
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
                    observed_actions = []
                    action_datasource_refs = []
                    page_field_evidence = []
                    try:
                        workflow_metadata = (
                            collect_workflow_security_metadata(
                                client,
                                application,
                                observed_actions,
                                action_datasource_refs,
                                page_field_evidence,
                            )
                        )
                    except (httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError) as exc:
                        print(
                            f"[WORKFLOW-PENDING] {name} "
                            f"type={type(exc).__name__}",
                            file=sys.stderr,
                            flush=True,
                        )
                        continue
                    datasource_reconciliation = None
                    try:
                        datasource_reconciliation = reconcile_action_datasources(
                            workspace_datasources,
                            action_datasource_refs,
                        )
                    except (RuntimeError, ValueError, TypeError) as exc:
                        print(
                            "[DATASOURCE-RECONCILIATION-PENDING] "
                            f"type={type(exc).__name__}",
                            file=sys.stderr,
                            flush=True,
                        )
                    else:
                        print(
                            "[DATASOURCE-RECONCILED] "
                            f"enumerated={datasource_reconciliation['datasource_enumeration_succeeded']} "
                            f"verified={len(datasource_reconciliation['verified_saved_datasource_ids'])} "
                            f"unverified={len(datasource_reconciliation['unverified_referenced_datasource_ids'])} "
                            f"unbound={len(datasource_reconciliation['actions_without_datasource_id'])}",
                            flush=True,
                        )

                    try:
                        inline_evidence = group_inline_api_evidence(
                            observed_actions,
                            action_datasource_refs,
                        )
                    except (RuntimeError, ValueError, TypeError) as exc:
                        print(
                            "[INLINE-API-PENDING] "
                            f"type={type(exc).__name__}",
                            file=sys.stderr,
                            flush=True,
                        )
                    else:
                        print(
                            "[INLINE-API-OBSERVED] "
                            f"actions={inline_evidence['inline_action_count']} "
                            f"origins={inline_evidence['observed_origin_count']} "
                            f"unresolved={len(inline_evidence['unresolved_action_ids'])}",
                            flush=True,
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

                    observation = build_appsmith_observation(
                        application,
                        observed_actions,
                    )

                    observation["connectors"] = build_verified_saved_connector_evidence(
                        workspace_datasources,
                        datasource_reconciliation,
                    )

                    collection_evidence = evaluate_collection_evidence(
                        application,
                        observed_actions,
                        action_datasource_refs,
                        workspace_datasources,
                        datasource_reconciliation,
                    )

                    observation["collection_complete"] = (
                        collection_evidence["collection_complete"]
                    )

                    observation["pending_reasons"] = (
                        collection_evidence["pending_reasons"]
                    )
                    # Attach sanitized, application-wide field evidence.
                    # This does not claim complete backend schema coverage.
                    field_evidence = aggregate_page_field_evidence(
                        application,
                        page_field_evidence,
                    )
                    observation["data_field_evidence"] = field_evidence

                    try:
                        result = send_appsmith_observation(
                            record["id"],
                            observation,
                        )
                        print(
                            f"[OBSERVATION-STORED] {name} "
                            f"id={result.get('id')} "
                            f"created={result.get('created')}",
                            flush=True,
                        )
                    except httpx.HTTPStatusError as exc:
                        print(
                            f"[OBSERVATION-ERROR] {name} "
                            f"HTTP {exc.response.status_code}",
                            file=sys.stderr,
                            flush=True,
                        )
                    except httpx.HTTPError as exc:
                        print(
                            f"[OBSERVATION-ERROR] {name} "
                            f"type={type(exc).__name__}",
                            file=sys.stderr,
                            flush=True,
                        )

                    try:
                        risk_result = request_risk_assessment_if_needed(
                            record["id"]
                        )
                        print(
                            f"[RISK-ASSESSMENT] {name} "
                            f"action={risk_result.get('action')} "
                            f"status={risk_result.get('risk_status')} "
                            f"score={risk_result.get('score')}",
                            flush=True,
                        )
                    except httpx.HTTPStatusError as exc:
                        print(
                            f"[RISK-ERROR] {name} "
                            f"HTTP {exc.response.status_code}",
                            file=sys.stderr,
                            flush=True,
                        )
                    except httpx.HTTPError as exc:
                        print(
                            f"[RISK-ERROR] {name} "
                            f"type={type(exc).__name__}",
                            file=sys.stderr,
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
    clear_success()
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
            record_success()

        except Exception as exc:
            clear_success()
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
