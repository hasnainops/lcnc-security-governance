import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("lo1_grants", Path(__file__).resolve().parents[1] / "scripts/configure-lo1-vault-grants.py")
grants = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grants)


def test_role_update_preserves_receipts_grants_and_credential_lifetimes():
    original = {"db_name": "lcnc-postgres", "creation_statements": [
        'CREATE ROLE "{{name}}" WITH LOGIN;',
        'GRANT SELECT, INSERT ON public.controlled_egress_enforcement_receipts TO "{{name}}";'],
        "default_ttl": 900, "max_ttl": 3600, "credential_type": "password", "credential_config": {},
        "revocation_statements": ["custom revocation"], "renew_statements": [], "rollback_statements": []}
    updated = grants.updated_role(original)
    assert updated["creation_statements"][:2] == original["creation_statements"]
    for key in set(original) - {"creation_statements"}:
        assert updated[key] == original[key]
    assert grants.updated_role(updated) == updated
    credential_grant = next(item for item in updated["creation_statements"] if "application_owner_credentials" in item)
    assert credential_grant.startswith("GRANT SELECT ON TABLE")


def test_unrecognized_role_fields_are_not_silently_discarded():
    with pytest.raises(RuntimeError):
        grants.updated_role({"future_field": "keep-me", "creation_statements": ["existing"]})
