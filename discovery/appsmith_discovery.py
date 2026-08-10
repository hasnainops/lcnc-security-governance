import os
import sys

import httpx


APPSMITH_BASE_URL = os.getenv("APPSMITH_BASE_URL", "http://appsmith")
APPSMITH_USER = os.environ["APPSMITH_USER"]
APPSMITH_PASSWORD = os.environ["APPSMITH_PASSWORD"]
GOVERNANCE_API_URL = os.getenv(
    "GOVERNANCE_API_URL",
    "http://governance-api:8000"
)


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

    if not payload.get("responseMeta", {}).get("success"):
        raise RuntimeError("Failed to retrieve Appsmith workspaces")

    return payload.get("data", [])


def get_applications(client: httpx.Client, workspace_id: str):
    response = client.get(
        f"{APPSMITH_BASE_URL}/api/v1/applications/home",
        params={"workspaceId": workspace_id},
    )
    response.raise_for_status()

    payload = response.json()

    if not payload.get("responseMeta", {}).get("success"):
        raise RuntimeError(
            f"Failed to retrieve applications for workspace {workspace_id}"
        )

    return payload.get("data", [])


def get_inventory():
    response = httpx.get(
        f"{GOVERNANCE_API_URL}/applications",
        timeout=10.0
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
        "internet_exposed": bool(application.get("isPublic", False)),
        "external_integration": None,
    }

    response = httpx.post(
        f"{GOVERNANCE_API_URL}/applications",
        json=payload,
        timeout=10.0,
    )

    if response.status_code not in (201, 409):
        response.raise_for_status()



def mark_seen(application_id):
    response = httpx.patch(
        f"{GOVERNANCE_API_URL}/applications/{application_id}/seen",
        timeout=10.0,
    )
    response.raise_for_status()

def main():
    print("=== Appsmith Discovery ===")

    with httpx.Client(
        follow_redirects=True,
        timeout=15.0
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
                workspace_id
            )

            for application in applications:
                discovered += 1

                external_id = application["id"]
                name = application["name"]

                if external_id in inventory:
                    known += 1

                    mark_seen(inventory[external_id]["id"])

                    print(
                        f"[KNOWN]  {name} "
                        f"({external_id})"
                    )

                else:
                    shadow += 1

                    print(
                        f"[SHADOW] {name} "
                        f"({external_id})"
                    )

                    register_shadow_application(application)

        print()
        print("=== Discovery Summary ===")
        print(f"Discovered: {discovered}")
        print(f"Known:      {known}")
        print(f"Shadow:     {shadow}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Discovery failed: {exc}", file=sys.stderr)
        sys.exit(1)
