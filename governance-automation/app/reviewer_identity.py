"""Authenticate a Security/GRC reviewer using the local Vault identity store."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID


class ReviewerAccessError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


REVIEWER_POLICIES = {
    "Security/GRC Reviewer": "lcnc-security-reviewer",
    "Senior Security/GRC Reviewer": "lcnc-senior-security-reviewer",
}


def reviewer_policy_for_role(required_role):
    policy = REVIEWER_POLICIES.get(required_role)
    if not policy:
        raise ReviewerAccessError(403, "Unsupported reviewer role.")
    return policy


def verified_reviewer(
    authorization,
    assigned_to=None,
    required_role="Security/GRC Reviewer",
):
    required_policy = reviewer_policy_for_role(required_role)
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or not token.isascii() or not token.isprintable() or " " in token:
        raise ReviewerAccessError(401, "A reviewer bearer credential is required.")
    address = os.environ.get("VAULT_ADDR", "http://vault:8200").rstrip("/")
    request = Request(address + "/v1/auth/token/lookup-self", headers={"X-Vault-Token": token})
    client = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with client.open(request, timeout=3) as response:
            data = json.load(response)["data"]
        policies = data["policies"]
        entity = str(UUID(data["entity_id"]))
    except HTTPError as exc:
        if exc.code in (400, 401, 403):
            raise ReviewerAccessError(403, "Reviewer credential refused.") from None
        raise ReviewerAccessError(503, "Reviewer identity service unavailable.") from None
    except (URLError, OSError, KeyError, TypeError, ValueError, AttributeError):
        raise ReviewerAccessError(403, "Reviewer identity could not be verified.") from None
    if not isinstance(policies, list) or required_policy not in policies:
        raise ReviewerAccessError(403, "Security reviewer role required.")
    actor = "vault:" + entity
    if assigned_to is not None and assigned_to != actor:
        raise ReviewerAccessError(403, "Request is assigned to another reviewer.")
    return actor
