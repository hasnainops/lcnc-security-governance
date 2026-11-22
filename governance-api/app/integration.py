import http.client
import os
import socket
import ssl
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from types import SimpleNamespace
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from .database import get_connection


INTEGRATION_GATEWAY_URL = os.getenv(
    "INTEGRATION_GATEWAY_URL",
    "http://integration-gateway:8005",
)


class TransferEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_url: str

    content: str = ""

    field_names: list[str] = Field(
        default_factory=list
    )


class ControlledEgressRequest(
    TransferEvaluationRequest
):
    """Outbound request that must pass DLP policy first."""

    method: Literal["POST"] = "POST"


def _approved_external_hosts():
    """Return the server-owned egress destination allowlist."""

    return {
        host.strip().lower().rstrip(".")
        for host in os.getenv(
            "CONTROLLED_EGRESS_APPROVED_HOSTS",
            "",
        ).split(",")
        if host.strip()
    }


def _classify_destination(destination_url, *, include_addresses=False):
    """Validate a target and derive destination trust server-side."""

    parsed = urlparse(destination_url)

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "destination_url must be a valid "
                "HTTP or HTTPS URL"
            ),
        )

    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=422,
            detail=(
                "destination_url must not contain "
                "embedded credentials"
            ),
        )

    hostname = parsed.hostname.lower().rstrip(".")

    try:
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                "destination_url contains an invalid port"
            ),
        ) from exc

    if port is None:
        port = (
            443
            if parsed.scheme == "https"
            else 80
        )

    try:
        resolved = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "decision": "block",
                "reason": (
                    "destination_resolution_failed"
                ),
            },
        ) from exc

    addresses = {
        ip_address(
            record[4][0].split("%", 1)[0]
        )
        for record in resolved
    }

    if (
        not addresses
        or any(
            not address.is_global
            for address in addresses
        )
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "decision": "block",
                "reason": "unsafe_destination",
                "message": (
                    "Controlled egress cannot target "
                    "loopback, private, link-local, "
                    "reserved, or other non-public "
                    "addresses."
                ),
            },
        )

    destination_trust = (
        "approved_external"
        if hostname in _approved_external_hosts()
        else "unapproved_external"
    )

    if include_addresses:
        return (
            parsed,
            destination_trust,
            tuple(
                sorted(
                    addresses,
                    key=lambda address: (
                        address.version,
                        int(address),
                    ),
                )
            ),
        )

    return parsed, destination_trust


def evaluate_and_persist(
    application_id: UUID,
    payload: TransferEvaluationRequest,
):
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
            status_code=404,
            detail="Application not found",
        )

    parsed, destination_trust = (
        _classify_destination(
            payload.destination_url
        )
    )

    gateway_payload = {
        "application_id": str(application_id),
        "application_name": application["name"],
        "destination_url": payload.destination_url,
        "destination_trust": destination_trust,
        "declared_classification": (
            application["data_classification"]
        ),
        "content": payload.content,
        "field_names": payload.field_names,
    }

    try:
        response = httpx.post(
            (
                f"{INTEGRATION_GATEWAY_URL}"
                "/evaluate-transfer"
            ),
            json=gateway_payload,
            timeout=15.0,
        )

        response.raise_for_status()

    except (
        httpx.ConnectError,
        httpx.TimeoutException,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "decision": "block",
                "reason": (
                    "integration_gateway_unavailable"
                ),
                "message": (
                    "Transfer blocked because the "
                    "integration control is unavailable."
                ),
            },
        ) from exc

    except httpx.HTTPStatusError as exc:
        detail = (
            exc.response.json()
            if exc.response.content
            else {
                "decision": "block",
                "reason": "gateway_error",
            }
        )

        raise HTTPException(
            status_code=502,
            detail=detail,
        ) from exc

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "decision": "block",
                "reason": "gateway_request_failed",
            },
        ) from exc

    result = response.json()
    event_id = uuid4()

    with get_connection() as connection:
        persisted = connection.execute(
            """
            INSERT INTO integration_transfer_events (
                id,
                application_id,
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
                dlp_engine_version
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            RETURNING evaluated_at;
            """,
            (
                event_id,
                application_id,
                parsed.scheme,
                parsed.hostname,
                destination_trust,
                application["data_classification"],
                result["effective_sensitivity"],
                result["decision"],
                result["allowed"],
                Jsonb(result["reasons"]),
                result["dlp"][
                    "sensitive_data_detected"
                ],
                result["dlp"]["finding_count"],
                result["dlp"][
                    "highest_sensitivity"
                ],
                Jsonb(
                    result["dlp"][
                        "detected_types"
                    ]
                ),
                result["gateway_version"],
                result["dlp"]["engine_version"],
            ),
        ).fetchone()

    return {
        "event_id": event_id,
        "application_id": application_id,
        "application_name": application["name"],
        "destination": {
            "scheme": parsed.scheme,
            "host": parsed.hostname,
            "trust": destination_trust,
        },
        "declared_classification": (
            application["data_classification"]
        ),
        "effective_sensitivity": (
            result["effective_sensitivity"]
        ),
        "decision": result["decision"],
        "allowed": result["allowed"],
        "reasons": result["reasons"],
        "dlp": result["dlp"],
        "evaluated_at": persisted["evaluated_at"],
    }

def record_controlled_egress_enforcement(
    event_id,
    outcome,
    upstream_status_code=None,
):
    """Record execution-boundary evidence for one transfer event."""

    if outcome not in {
        "blocked_before_send",
        "forwarded_upstream",
        "delivery_unconfirmed",
    }:
        raise ValueError("Invalid controlled-egress outcome")

    with get_connection() as connection:
        saved = connection.execute(
            """
            UPDATE integration_transfer_events
            SET
                enforcement_outcome = %s,
                enforced_at = NOW(),
                upstream_status_code = %s
            WHERE id = %s
              AND enforcement_outcome IS NULL
            RETURNING id;
            """,
            (
                outcome,
                upstream_status_code,
                event_id,
            ),
        ).fetchone()

    if saved is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "Controlled-egress enforcement receipt "
                "could not be persisted."
            ),
        )



class _PinnedSocketDialer:
    """Connect directly to a validated numeric IP, not DNS."""

    def _install_pin(self, pinned_ip):
        self._pinned_ip = ip_address(str(pinned_ip))

        if not self._pinned_ip.is_global:
            raise ValueError(
                "Pinned destination must be globally routable"
            )

        self._create_connection = self._dial_pinned

    def _dial_pinned(
        self,
        address,
        timeout,
        source_address=None,
    ):
        if (
            address != (self.host, self.port)
            or source_address is not None
        ):
            raise ValueError(
                "Unexpected outbound connection target"
            )

        ip = self._pinned_ip

        family = (
            socket.AF_INET6
            if ip.version == 6
            else socket.AF_INET
        )

        sock = socket.socket(
            family,
            socket.SOCK_STREAM,
        )

        try:
            sock.settimeout(timeout)

            destination = (
                (str(ip), self.port, 0, 0)
                if ip.version == 6
                else (str(ip), self.port)
            )

            # Numeric IP: no second hostname DNS lookup.
            sock.connect(destination)

            return sock

        except BaseException:
            sock.close()
            raise


class _PinnedHTTPConnection(
    http.client.HTTPConnection,
    _PinnedSocketDialer,
):
    def __init__(
        self,
        hostname,
        port,
        *,
        pinned_ip,
        timeout,
    ):
        super().__init__(
            hostname,
            port=port,
            timeout=timeout,
        )

        self._install_pin(pinned_ip)


class _PinnedHTTPSConnection(
    http.client.HTTPSConnection,
    _PinnedSocketDialer,
):
    def __init__(
        self,
        hostname,
        port,
        *,
        pinned_ip,
        timeout,
        context=None,
    ):
        if context is None:
            context = ssl.create_default_context()

        super().__init__(
            hostname,
            port=port,
            timeout=timeout,
            context=context,
        )

        self._install_pin(pinned_ip)


def _send_pinned_request(
    *,
    method,
    url,
    content,
    timeout,
    follow_redirects=False,
):
    """Send once to a freshly validated, pinned destination."""

    if follow_redirects:
        raise ValueError(
            "Controlled egress must not follow redirects"
        )

    parsed, _trust, addresses = _classify_destination(
        url,
        include_addresses=True,
    )

    hostname = parsed.hostname.lower().rstrip(".")

    port = parsed.port

    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    pinned_ip = addresses[0]

    connection_type = (
        _PinnedHTTPSConnection
        if parsed.scheme == "https"
        else _PinnedHTTPConnection
    )

    connection = connection_type(
        hostname,
        port,
        pinned_ip=pinned_ip,
        timeout=timeout,
    )

    # HTTPX parses and percent-encodes the request target,
    # but performs no network operation here.
    target = httpx.URL(url).raw_path.decode("ascii")

    try:
        connection.request(
            method,
            target,
            body=content.encode("utf-8"),
        )

        response = connection.getresponse()

        # Redirects are returned as status codes only.
        # No Location header is followed.
        return SimpleNamespace(
            status_code=response.status,
        )

    finally:
        connection.close()


def execute_controlled_egress(
    application_id: UUID,
    payload: ControlledEgressRequest,
):
    """Evaluate DLP, then send only to a validated IP."""

    evaluation_payload = TransferEvaluationRequest(
        destination_url=payload.destination_url,
        content=payload.content,
        field_names=payload.field_names,
    )

    evaluation = evaluate_and_persist(
        application_id,
        evaluation_payload,
    )

    if not evaluation["allowed"]:
        record_controlled_egress_enforcement(
            evaluation["event_id"],
            "blocked_before_send",
        )

        return {
            **evaluation,
            "executed": False,
            "upstream_status_code": None,
        }

    try:
        response = _send_pinned_request(
            method=payload.method,
            url=payload.destination_url,
            content=payload.content,
            timeout=15.0,
            follow_redirects=False,
        )

    except HTTPException:
        # A destination failing the final public-IP check
        # must not be contacted.
        record_controlled_egress_enforcement(
            evaluation["event_id"],
            "blocked_before_send",
        )
        raise

    except (
        OSError,
        httpx.ConnectError,
        httpx.TimeoutException,
    ) as exc:
        record_controlled_egress_enforcement(
            evaluation["event_id"],
            "delivery_unconfirmed",
        )

        raise HTTPException(
            status_code=502,
            detail={
                "decision": "allow",
                "executed": False,
                "reason": (
                    "controlled_egress_destination_unavailable"
                ),
            },
        ) from exc

    except Exception as exc:
        record_controlled_egress_enforcement(
            evaluation["event_id"],
            "delivery_unconfirmed",
        )

        raise HTTPException(
            status_code=502,
            detail={
                "decision": "allow",
                "executed": False,
                "reason": (
                    "controlled_egress_request_failed"
                ),
            },
        ) from exc

    record_controlled_egress_enforcement(
        evaluation["event_id"],
        "forwarded_upstream",
        response.status_code,
    )

    return {
        **evaluation,
        "executed": True,
        "upstream_status_code": response.status_code,
    }
