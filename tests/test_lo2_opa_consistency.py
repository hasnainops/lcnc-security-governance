
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from app import access, policy


APP_ID = UUID("11111111-2222-3333-4444-555555555555")


@pytest.mark.parametrize("module_name", ["policy", "access"])
@pytest.mark.parametrize(
    "allowed,action,valid",
    [
        (True, "allow", True),
        (False, "deny", True),
        (True, "deny", False),
        (False, "allow", False),
    ],
)
def test_opa_decision_consistency(
    monkeypatch, module_name, allowed, action, valid
):
    module = policy if module_name == "policy" else access

    application = {
        "id": APP_ID,
        "name": "LO2 OPA Test",
        "registration_status": "registered",
        "data_classification": "internal",
        "internet_exposed": False,
        "external_integration": False,
        "integration_approved": True,
        "external_integration_count": 0,
        "unapproved_integration_count": 0,
        "credential_type": "managed",
        "risk_score": 10,
        "risk_level": "low",
    }

    writes = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            if "FROM applications" in sql:
                self.row = application
            elif "INSERT INTO policy_decisions" in sql:
                writes.append(sql)
                self.row = {
                    "id": params[0],
                    "action": params[2],
                    "allowed": params[3],
                    "reasons": [],
                    "policy_version": params[5],
                    "evaluated_at": datetime.now(timezone.utc),
                }
            elif "INSERT INTO access_decisions" in sql:
                writes.append(sql)
                self.row = {
                    "evaluated_at": datetime.now(timezone.utc),
                }
            else:
                raise AssertionError("Unexpected SQL")
            return self

        def fetchone(self):
            return self.row

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "result": {
                    "allow": allowed,
                    "action": action,
                    "reasons": [],
                }
            }

    monkeypatch.setattr(
        module, "get_connection", FakeConnection
    )
    monkeypatch.setattr(
        module.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )

    if module_name == "access":
        monkeypatch.setattr(
            access,
            "check_jit_privilege",
            lambda *args, **kwargs: {
                "active": False,
                "grant_id": None,
            },
        )
        request = SimpleNamespace(
            subject_id="lo2-test-user",
            role="developer",
            action="read",
        )
        evaluate = lambda: access.authorize_and_persist(
            APP_ID, request
        )
    else:
        evaluate = lambda: policy.evaluate_and_persist(
            APP_ID
        )

    if valid:
        result = evaluate()
        assert result["allowed"] is allowed

        key = (
            "action"
            if module_name == "policy"
            else "decision"
        )
        assert result[key] == action
        assert len(writes) == 1
    else:
        with pytest.raises(HTTPException) as error:
            evaluate()

        assert error.value.status_code == 502
        assert len(writes) == 0
