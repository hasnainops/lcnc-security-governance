import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "discovery_observation_contract_test",
    ROOT / "governance-api/app/discovery_observation.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Observation = module.AppsmithObservation


def payload():
    return {
        "contract_version": "appsmith-observation-v1",
        "source": "appsmith",
        "external_id": "app-1",
        "collector_version": "collector-v1",
        "observed_at": "2026-11-04T09:00:00Z",
        "collection_complete": True,
        "pending_reasons": [],
        "connectors": [{
            "connector_id": "datasource:one",
            "destination_state": "observed",
            "destination": {
                "scheme": "https",
                "host": "API.Example.COM.",
            },
        }],
    }


def test_round_trip_preserves_unknown_credential_usage():
    observed = Observation.model_validate(payload())
    assert observed.connectors[0].destination.host == "api.example.com"
    assert observed.connectors[0].uses_api_key is None
    assert observed.observed_at.utcoffset().total_seconds() == 0
    restored = Observation.model_validate_json(
        observed.model_dump_json()
    )
    assert restored == observed


@pytest.mark.parametrize("complete,reasons", [
    (True, []),
    (False, ["actions_incomplete"]),
])
def test_empty_collection_keeps_its_completeness(complete, reasons):
    data = payload()
    data.update(
        connectors=[],
        collection_complete=complete,
        pending_reasons=reasons,
    )
    observed = Observation.model_validate(data)
    assert observed.collection_complete is complete
    assert "connector_count" not in observed.model_dump()


@pytest.mark.parametrize("field", [
    "contract_version", "source", "external_id", "collector_version",
    "observed_at", "collection_complete", "pending_reasons", "connectors",
])
def test_required_evidence_cannot_be_omitted(field):
    data = payload()
    del data[field]
    with pytest.raises(ValidationError):
        Observation.model_validate(data)


@pytest.mark.parametrize("field,value", [
    ("destination_trust", "approved_external"),
    ("connector_count", 0),
    ("unapproved_integration_count", 0),
    ("changes_last_24h", 0),
    ("policy_fingerprint", "claimed-policy"),
    ("headers", {"Authorization": "SENTINEL"}),
])
def test_caller_cannot_supply_decisions_counts_or_raw_headers(
    field, value
):
    data = payload()
    data[field] = value
    with pytest.raises(ValidationError):
        Observation.model_validate(data)


@pytest.mark.parametrize("host", [
    "https://example.com",
    "user:secret@example.com",
    "example.com/path",
    "example.com?token=SENTINEL",
    "example.com#fragment",
    "{{dynamicHost}}",
    "*.example.com",
    " example.com",
    "example.com..",
    "fe80::1%eth0",
])
def test_destination_host_rejects_url_components_and_unresolved_templates(
    host,
):
    data = payload()
    data["connectors"][0]["destination"]["host"] = host
    with pytest.raises(ValidationError):
        Observation.model_validate(data)


@pytest.mark.parametrize("host", [
    "governance-api", "127.0.0.1", "2001:db8::1",
])
def test_host_observation_does_not_assert_transfer_permission(host):
    data = payload()
    data["connectors"][0]["destination"]["host"] = host
    observed = Observation.model_validate(data)
    assert observed.connectors[0].destination.host == host
    assert "destination_trust" not in observed.connectors[0].model_dump()


@pytest.mark.parametrize("state", ["unresolved", "unsupported"])
def test_unresolved_destination_is_retained_without_fabricated_values(
    state,
):
    data = payload()
    data["connectors"][0].update(
        destination_state=state,
        destination=None,
    )
    observed = Observation.model_validate(data)
    assert observed.connectors[0].destination is None


@pytest.mark.parametrize("case", [
    "duplicate_connector",
    "missing_destination",
    "unexpected_destination",
    "naive_timestamp",
    "string_boolean",
    "missing_reason",
    "contradictory_reason",
    "duplicate_reason",
    "invalid_port",
    "boolean_port",
    "string_api_key_flag",
    "nested_approval",
    "nested_raw_header",
])
def test_inconsistent_or_unsafe_observations_are_rejected(case):
    data = payload()
    connector = data["connectors"][0]

    if case == "duplicate_connector":
        data["connectors"].append(connector.copy())
    elif case == "missing_destination":
        connector["destination"] = None
    elif case == "unexpected_destination":
        connector["destination_state"] = "unresolved"
    elif case == "naive_timestamp":
        data["observed_at"] = "2026-11-04T09:00:00"
    elif case == "string_boolean":
        data["collection_complete"] = "true"
    elif case == "missing_reason":
        data["collection_complete"] = False
    elif case == "contradictory_reason":
        data["pending_reasons"] = ["actions_incomplete"]
    elif case == "duplicate_reason":
        data.update(
            collection_complete=False,
            pending_reasons=["actions_incomplete"] * 2,
        )
    elif case == "invalid_port":
        connector["destination"]["port"] = 65536
    elif case == "boolean_port":
        connector["destination"]["port"] = True
    elif case == "string_api_key_flag":
        connector["uses_api_key"] = "false"
    elif case == "nested_approval":
        connector["destination"]["approved"] = True
    elif case == "nested_raw_header":
        connector["headers"] = {"Authorization": "SENTINEL"}

    with pytest.raises(ValidationError):
        Observation.model_validate(data)
