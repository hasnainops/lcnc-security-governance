"""Collector/route regression checks; database semantics have real SQL tests."""
import ast
from contextlib import nullcontext
import importlib.util
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from lo1_classification_support import ROOT, modules


@pytest.fixture
def worker():
    spec = importlib.util.spec_from_file_location(
        "_name_sync_worker_" + uuid4().hex, ROOT / "discovery/appsmith_discovery.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collector_sends_only_source_identity_and_current_name(worker, monkeypatch):
    requests = []
    def patch(url, **kwargs):
        requests.append((url, kwargs))
        return httpx.Response(200, json={"id": "inventory-id", "name": "Renamed app"},
                              request=httpx.Request("PATCH", url))
    monkeypatch.setattr(worker.httpx, "patch", patch)
    result = worker.mark_seen("inventory-id", {
        "id": "source-id", "name": "Renamed app", "isPublic": True,
        "password": "SENTINEL", "owner_email": "not-an-owner-attestation@example.test",
    })
    assert result["name"] == "Renamed app"
    assert requests[0][0].endswith("/applications/inventory-id/seen")
    assert requests[0][1]["json"] == {
        "source": "appsmith", "external_id": "source-id", "name": "Renamed app",
    }
    assert "SENTINEL" not in repr(requests)


def test_collector_legacy_call_preserves_no_body_contract(worker, monkeypatch):
    def patch(url, **kwargs):
        assert "json" not in kwargs
        return httpx.Response(200, json={"id": "inventory-id"}, request=httpx.Request("PATCH", url))
    monkeypatch.setattr(worker.httpx, "patch", patch)
    worker.mark_seen("inventory-id")


def test_scheduled_cycle_supplies_fresh_appsmith_name(worker, monkeypatch):
    source = {"id": "source-id", "name": "New source name"}
    called = []
    monkeypatch.setattr(worker.httpx, "Client", lambda **kwargs: nullcontext(object()))
    monkeypatch.setattr(worker, "login", lambda client: None)
    monkeypatch.setattr(worker, "get_workspaces", lambda client: [{"id": "workspace-id"}])
    monkeypatch.setattr(worker, "get_inventory", lambda: {"source-id": {"id": "inventory-id", "name": "Old name"}})
    monkeypatch.setattr(worker, "get_applications", lambda client, workspace: [source])
    monkeypatch.setattr(worker, "_get_workspace_datasources", lambda client, workspace: [])
    monkeypatch.setattr(worker, "mark_seen", lambda app_id, observed: called.append((app_id, observed)))
    worker.run_discovery_cycle()
    assert called == [("inventory-id", source)]


@pytest.fixture
def route(monkeypatch):
    service = modules(monkeypatch).discovery_presence
    # Exercise the actual route declaration without starting unrelated services.
    tree = ast.parse((ROOT / "governance-api/app/main.py").read_text())
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef)
                and item.name == "mark_application_seen")
    calls = []
    def persist(app_id, payload):
        calls.append((app_id, payload))
        return {"id": str(app_id)}
    app = FastAPI()
    namespace = {"app": app, "UUID": UUID, "AppsmithSeenRequest": service.AppsmithSeenRequest,
                 "persist_application_seen": persist}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "actual_seen_route", "exec"), namespace)
    return TestClient(app), calls, "/applications/11111111-2222-3333-4444-555555555555/seen"


def test_existing_seen_route_accepts_legacy_and_observed_requests(route):
    client, calls, path = route
    assert client.patch(path).status_code == 200
    assert calls[-1][1] is None
    assert client.patch(path, json={"source": "appsmith", "external_id": "source-id", "name": "Renamed"}).status_code == 200
    assert calls[-1][1].external_id == "source-id"
    assert calls[-1][1].name == "Renamed"


@pytest.mark.parametrize("change", [
    {"source": "other"}, {"external_id": ""}, {"external_id": "invalid/id"},
    {"name": ""}, {"name": "   "}, {"name": None}, {"name": 123}, {"name": "a\nb"},
    {"owner_email": "forged@example.test"}, {"data_classification": "public"},
    {"registration_status": "registered"}, {"shadow_it_candidate": False},
])
def test_seen_route_rejects_bad_metadata_and_governance_overrides(route, change):
    client, calls, path = route
    response = client.patch(path, json={"source": "appsmith", "external_id": "source-id", "name": "Renamed", **change})
    assert response.status_code == 422
    assert not calls
