import json
import os
import urllib.request


GOVERNANCE_AUTOMATION_URL = os.getenv(
    "GOVERNANCE_AUTOMATION_URL",
    "http://governance-automation:8007",
)


def route_governance_approval(application_id):
    request = urllib.request.Request(
        (
            f"{GOVERNANCE_AUTOMATION_URL}"
            f"/applications/{application_id}/route"
        ),
        data=b"",
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
            "status": "routed",
            "approval": result,
        }

    except Exception as exc:
        return {
            "status": "routing_error",
            "error": str(exc),
        }
