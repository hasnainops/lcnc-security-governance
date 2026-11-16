from datetime import timedelta
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from lo1_classification_support import declaration, model_result, modules, sources


@pytest.fixture
def service(monkeypatch):
    return modules(monkeypatch)


@pytest.mark.parametrize("change", [
    {"attested": False}, {"attested": "true"}, {"subject_id": "pretend-owner"},
    {"owner_email": "pretend@example.test"}, {"data_classification": "public"},
    {"data_fields": []}, {"field_scope": "no_data_fields"},
    {"business_purpose": "unknown purpose"},
    {"data_fields": [{"name": "amount", "description": "Amount"}, {"name": "AMOUNT", "description": "Duplicate"}]},
])
def test_declaration_cannot_assert_identity_authority_or_inconsistent_schema(service, change):
    with pytest.raises(ValidationError):
        service.owner_context.OwnerContextRequest.model_validate({**declaration(), **change})


def test_none_declared_is_explicit_and_not_fabricated_observation(service):
    app, context, row, now = sources()
    context["payload"].update(field_scope="no_data_fields", data_fields=[])
    built = service.classification_inputs.build_classification_inputs(app, context, row, now)
    assert "owner_declaration_conflicts_with_observed_fields" in built.review_reasons
    assert built.provenance["declared_fields"] == []
    assert built.provenance["observed_widget_fields"] == ["amount"]
    assert built.payload["data_fields"] == "amount"


def test_new_poll_identity_does_not_change_semantic_key(service):
    app, context, row, now = sources()
    first = service.classification_inputs.build_classification_inputs(app, context, row, now)
    row["id"] = uuid4()
    row["observed_at"] += timedelta(seconds=5)
    row["payload"]["observed_at"] = row["observed_at"].isoformat()
    second = service.classification_inputs.build_classification_inputs(app, context, row, now + timedelta(seconds=5))
    assert first.semantic_hash == second.semantic_hash
    assert first.provenance["observation_id"] != second.provenance["observation_id"]


@pytest.mark.parametrize("seconds,reason", [(181, "appsmith_observation_stale"), (-31, "observation_timestamp_in_future")])
def test_expired_or_future_observation_is_pending(service, seconds, reason):
    app, context, row, now = sources()
    with pytest.raises(service.classification_inputs.InputsPending) as error:
        service.classification_inputs.build_classification_inputs(app, context, row, now + timedelta(seconds=seconds))
    assert error.value.reasons == [reason]


def test_legacy_owner_fields_cannot_replace_authenticated_declaration(service):
    app, context, row, now = sources()
    app.update(business_purpose="Fake purpose", data_fields="fake", owner_email="fake@example.test")
    with pytest.raises(service.classification_inputs.InputsPending) as error:
        service.classification_inputs.build_classification_inputs(app, None, row, now)
    assert error.value.reasons == ["owner_attestation_required"]
    built = service.classification_inputs.build_classification_inputs(app, context, row, now)
    assert built.payload["business_purpose"] == context["payload"]["business_purpose"]
    assert "fake" not in built.payload["data_fields"]


def test_partial_dynamic_evidence_remains_reviewable(service):
    app, context, row, now = sources()
    row["payload"].update(collection_complete=False, pending_reasons=["connector_identity_unresolved"],
                          observed_actions=[{"action_id": "action-1", "destination_state": "unresolved"}])
    row["payload"]["data_field_evidence"]["dynamic_bindings_detected"] = 1
    built = service.classification_inputs.build_classification_inputs(app, context, row, now)
    assert set(built.review_reasons) >= {"connector_collection_partial", "integration_destinations_unresolved",
                                       "dynamic_field_bindings_require_owner_review"}
    assert "action_destinations_without_connector_identity" in built.review_reasons


@pytest.mark.parametrize("change", [
    {"authority": "authoritative"}, {"confidence": float("nan")}, {"review_required": "false"},
    {"model_sha256": "not-a-hash"}, {"suggested_classification": "restricted"},
    {"class_probabilities": {"internal": 0.8}},
    {"class_probabilities": {"public": float("nan"), "internal": .8, "confidential": .1, "restricted": .1}},
    {"unexpected": "not-allowed"},
])
def test_model_response_requires_consistent_advisory_evidence(service, change):
    with pytest.raises(ValidationError):
        service.automatic_classification.ModelResult.model_validate(model_result(**change))


def test_route_does_not_accept_owner_identity_in_payload(service, monkeypatch):
    router = service.owner_context_routes
    monkeypatch.setattr(router, "save_owner_context", lambda *args: pytest.fail("Invalid payload reached persistence"))
    app = FastAPI()
    app.include_router(router.router)
    response = TestClient(app).post(f"/applications/{uuid4()}/owner-context", json={**declaration(), "subject_id": "forged"})
    assert response.status_code == 422


def test_route_commits_declaration_before_attempting_ml(service, monkeypatch):
    router = service.owner_context_routes
    calls = []
    monkeypatch.setattr(router, "save_owner_context", lambda *args: calls.append("save") or {"action": "saved"})
    monkeypatch.setattr(router, "classify_if_needed", lambda *args: calls.append("classify") or {"action": "pending"})
    app = FastAPI()
    app.include_router(router.router)
    response = TestClient(app).post(f"/applications/{uuid4()}/owner-context", json=declaration())
    assert response.status_code == 200
    assert calls == ["save", "classify"]
    assert response.json()["declaration"]["action"] == "saved"
