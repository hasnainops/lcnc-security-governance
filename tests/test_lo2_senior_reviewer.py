
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

path = Path("governance-automation/app/reviewer_identity.py")

spec = importlib.util.spec_from_file_location(
    "lo2_reviewer_identity", path
)
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


@pytest.mark.parametrize("policies,role,expected", [
    (["lcnc-security-reviewer"], "Security/GRC Reviewer", True),
    (["lcnc-security-reviewer"], "Senior Security/GRC Reviewer", False),
    (["lcnc-senior-security-reviewer"], "Senior Security/GRC Reviewer", True),
    ([], "Senior Security/GRC Reviewer", False),
    (["unrelated-policy"], "Senior Security/GRC Reviewer", False),
])
def test_role_specific_authorization(monkeypatch, policies, role, expected):
    entity = str(uuid4())

    response = io.BytesIO(json.dumps({
        "data": {
            "policies": policies,
            "entity_id": entity,
        }
    }).encode())

    opener = MagicMock()
    opener.open.return_value = response

    monkeypatch.setattr(
        identity, "build_opener", lambda *args: opener
    )

    if expected:
        assert identity.verified_reviewer(
            "Bearer test-token", None, role
        ) == "vault:" + entity
    else:
        with pytest.raises(identity.ReviewerAccessError):
            identity.verified_reviewer(
                "Bearer test-token", None, role
            )


def test_unknown_reviewer_role_is_denied():
    with pytest.raises(identity.ReviewerAccessError):
        identity.reviewer_policy_for_role("Unknown Reviewer")
