"""Verified Vault identities for application access evaluation.

Uses the same verification logic and role-policy mapping as
Governance Automation. Keep both implementations synchronized.
"""

import json
import os

from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)
from uuid import UUID


class ReviewerAccessError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


ACCESS_ROLE_POLICIES = (
    ("security_admin", (
        "lcnc-security-reviewer",
        "lcnc-senior-security-reviewer",
    )),
    ("developer", ("lcnc-access-developer",)),
    ("viewer", ("lcnc-access-viewer",)),
)


def verified_access_principal(authorization):
    """Bind an access principal to a verified Vault identity and role."""

    scheme, _, token = (authorization or "").partition(" ")

    if (
        scheme.lower() != "bearer"
        or not token
        or not token.isascii()
        or not token.isprintable()
        or " " in token
    ):
        raise ReviewerAccessError(
            401, "An access bearer credential is required."
        )

    address = os.environ.get(
        "VAULT_ADDR", "http://vault:8200"
    ).rstrip("/")

    request = Request(
        address + "/v1/auth/token/lookup-self",
        headers={"X-Vault-Token": token},
    )

    client = build_opener(ProxyHandler({}), NoRedirect())

    try:
        with client.open(request, timeout=3) as response:
            data = json.load(response)["data"]

        policies = data["policies"]
        entity = str(UUID(data["entity_id"]))

    except HTTPError as exc:
        if exc.code in (400, 401, 403):
            raise ReviewerAccessError(
                403, "Access credential refused."
            ) from None

        raise ReviewerAccessError(
            503, "Identity service unavailable."
        ) from None

    except (
        URLError, OSError, KeyError, TypeError,
        ValueError, AttributeError,
    ):
        raise ReviewerAccessError(
            403, "Access identity could not be verified."
        ) from None

    if not isinstance(policies, list) or not all(
        isinstance(policy, str) for policy in policies
    ):
        raise ReviewerAccessError(
            403, "Invalid Vault policy claims."
        )

    for role, accepted_policies in ACCESS_ROLE_POLICIES:
        if any(
            policy in policies
            for policy in accepted_policies
        ):
            return {
                "subject_id": "vault:" + entity,
                "role": role,
            }

    raise ReviewerAccessError(
        403, "An authorized application role is required."
    )
