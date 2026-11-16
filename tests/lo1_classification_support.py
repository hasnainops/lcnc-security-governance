"""Isolated service imports and explicit synthetic fixtures for LO1 tests."""
import importlib
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


def modules(monkeypatch):
    name = "_lo1_owner_test_" + uuid4().hex
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / "governance-api/app")]
    monkeypatch.setitem(sys.modules, name, package)
    loaded = {}
    for part in ("owner_context", "classification_inputs", "automatic_classification", "owner_context_routes", "discovery_presence"):
        loaded[part] = importlib.import_module(name + "." + part)
    return types.SimpleNamespace(**loaded)


def declaration():
    return {"business_purpose": "Manage employee purchase requests and approvals",
            "field_scope": "declared_schema",
            "data_fields": [{"name": "amount", "description": "Requested purchase amount"}],
            "attested": True}


def observation(external_id="app-test", observed_at=None):
    now = observed_at or datetime.now(timezone.utc)
    return {"contract_version": "appsmith-observation-v1", "source": "appsmith",
            "external_id": external_id, "collector_version": "test-collector-v1",
            "observed_at": now.isoformat(), "collection_complete": True,
            "pending_reasons": [], "page_ids": ["page-1"], "connectors": [],
            "observed_actions": [], "data_field_evidence": {
                "scope": "appsmith_widget_dsl", "coverage": "partial",
                "field_identifiers": ["amount"], "pages_expected": 1,
                "pages_inspected": 1, "widgets_inspected": 1, "dynamic_bindings_detected": 0}}


def sources():
    now = datetime.now(timezone.utc)
    app = {"id": uuid4(), "external_id": "app-test", "name": "Purchase requests",
           "platform": "appsmith", "owner_context_id": uuid4()}
    context = {"id": app["owner_context_id"], "application_id": app["id"],
               "subject_id": "test-owner", "declared_at": now, "payload": declaration()}
    row = {"id": uuid4(), "application_id": app["id"], "observed_at": now,
           "payload": observation(observed_at=now)}
    return app, context, row, now


def model_result(**changes):
    result = {"analysis_type": "data-sensitivity-classification",
              "suggested_classification": "internal", "confidence": 0.8,
              "review_required": False, "review_threshold": 0.6,
              "model_version": "synthetic-test-v1", "model_sha256": "a" * 64,
              "class_probabilities": {"public": 0.1, "internal": 0.8,
                                      "confidential": 0.05, "restricted": 0.05},
              "authority": "advisory"}
    result.update(changes)
    return result


def mock_ml(monkeypatch, service, during=None, result=None):
    calls = []
    def health(url, **kwargs):
        return httpx.Response(200, json={"classification_model_version": "synthetic-test-v1",
                                        "classification_model_sha256": "a" * 64,
                                        "classification_review_threshold": 0.6},
                              request=httpx.Request("GET", url))
    def classify(url, **kwargs):
        calls.append(kwargs["json"])
        if during:
            during()
        return httpx.Response(200, json=result or model_result(), request=httpx.Request("POST", url))
    monkeypatch.setattr(service.httpx, "get", health)
    monkeypatch.setattr(service.httpx, "post", classify)
    return calls
