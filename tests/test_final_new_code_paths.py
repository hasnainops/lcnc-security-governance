import importlib
import os
import sys
import types
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test:test@localhost:5432/test",
)

ROOT = Path(__file__).resolve().parents[1]

GOVERNANCE_APP_DIR = (
    ROOT
    / "governance-api"
    / "app"
)

AUTOMATION_APP_DIR = (
    ROOT
    / "governance-automation"
    / "app"
)


def load_package_module(
    package_name,
    package_dir,
    module_name,
):
    package = types.ModuleType(
        package_name
    )

    package.__path__ = [
        str(package_dir)
    ]

    sys.modules[package_name] = package

    return importlib.import_module(
        f"{package_name}.{module_name}"
    )


security_scan = load_package_module(
    "governance_security_scan_final",
    GOVERNANCE_APP_DIR,
    "security_scan",
)

jit = load_package_module(
    "governance_automation_jit_final",
    AUTOMATION_APP_DIR,
    "jit",
)


APPLICATION_ID = UUID(
    "11111111-2222-3333-4444-555555555555"
)


class FakeResult:
    def __init__(
        self,
        *,
        one=None,
    ):
        self.one = one

    def fetchone(self):
        return self.one


class FakeConnection:
    def __init__(
        self,
        row,
    ):
        self.row = row

    def execute(
        self,
        *args,
        **kwargs,
    ):
        return FakeResult(
            one=self.row
        )

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False


def test_security_scan_fails_closed_without_trusted_observation(
    monkeypatch,
):
    application = {
        "id": APPLICATION_ID,
        "registration_status": "registered",
        "owner_name": "Citizen Developer",
        "owner_email": "citizen@example.com",
        "data_classification": "confidential",
        "internet_exposed": True,
        "external_integration_count": None,
        "unapproved_integration_count": None,
        "credential_type": "api_key",
        "connector_metadata": None,
        "workflow_security_metadata": None,
    }

    monkeypatch.setattr(
        security_scan,
        "get_connection",
        lambda: FakeConnection(
            application
        ),
    )

    with pytest.raises(
        HTTPException
    ) as exc:
        security_scan.scan_and_persist(
            APPLICATION_ID
        )

    assert exc.value.status_code == 409

    assert exc.value.detail["message"] == (
        "Security scan requires either "
        "trusted workflow evidence or "
        "complete observed integration metadata."
    )

    assert set(
        exc.value.detail["missing_fields"]
    ) == {
        "external_integration_count",
        "unapproved_integration_count",
        "connector_metadata",
    }


def test_jit_check_fails_closed_without_active_grant(
    monkeypatch,
):
    monkeypatch.setattr(
        jit,
        "get_connection",
        lambda: FakeConnection(None),
    )

    result = jit.check_privilege(
        application_id=APPLICATION_ID,
        subject_id="citizen@example.com",
        action="export",
    )

    assert result == {
        "active": False,
        "grant": None,
    }
