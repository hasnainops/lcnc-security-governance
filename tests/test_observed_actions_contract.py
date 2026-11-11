
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "governance-api"))

from app.discovery_observation import AppsmithObservation
from app.observation_store import canonical_observation


BASE = {
    "contract_version": "appsmith-observation-v1",
    "source": "appsmith",
    "external_id": "app-123",
    "collector_version": "collector-v1",
    "observed_at": "2026-11-10T00:00:00Z",
    "collection_complete": True,
    "pending_reasons": [],
    "connectors": [],
}


def test_valid_action_observation():
    observation = AppsmithObservation.model_validate({
        **BASE,
        "observed_actions": [{
            "action_id": "action-1",
            "destination_state": "observed",
            "destination": {
                "scheme": "https",
                "host": "api.example.com",
            },
        }],
    })
    assert len(observation.observed_actions) == 1


def test_duplicate_action_ids_rejected():
    action = {
        "action_id": "action-1",
        "destination_state": "unresolved",
    }
    with pytest.raises(ValidationError):
        AppsmithObservation.model_validate({
            **BASE,
            "observed_actions": [action, action],
        })


def test_observed_destination_required():
    with pytest.raises(ValidationError):
        AppsmithObservation.model_validate({
            **BASE,
            "observed_actions": [{
                "action_id": "action-1",
                "destination_state": "observed",
            }],
        })


def test_canonical_action_order():
    actions = [
        {"action_id": "action-2", "destination_state": "unresolved"},
        {"action_id": "action-1", "destination_state": "unresolved"},
    ]

    first = AppsmithObservation.model_validate({
        **BASE,
        "observed_actions": actions,
    })
    second = AppsmithObservation.model_validate({
        **BASE,
        "observed_actions": list(reversed(actions)),
    })

    document1, hash1 = canonical_observation(first)
    document2, hash2 = canonical_observation(second)

    assert hash1 == hash2
    assert document1 == document2
    assert document1["observed_actions"][0]["action_id"] == "action-1"
