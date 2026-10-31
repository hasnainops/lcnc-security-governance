import importlib
import sys
import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

root = Path(__file__).resolve().parents[1]
package = types.ModuleType("functional_route_tests")
package.__path__ = [str(root / "governance-api/app")]
sys.modules[package.__name__] = package
route = importlib.import_module("functional_route_tests.status_routes")


def test_functional_route_returns_probe_evidence(monkeypatch):
    evidence = {
        "schema_version": 1,
        "source": "internal_http_probes",
        "served_at": "2026-10-21T09:30:00+00:00",
        "stale_after_seconds": 30,
        "checks": [{
            "service": "governance-api-a",
            "check": "inventory_read",
            "status": "failed",
            "observed_at": "2026-10-21T09:30:00+00:00",
            "duration_ms": 12,
            "http_status": 500,
            "application_count": None,
            "reason": "http_error",
        }],
    }

    async def collect():
        return evidence

    monkeypatch.setattr(route, "collect_functional_status", collect)
    app = FastAPI()
    app.include_router(route.router)

    with TestClient(app) as client:
        response = client.get("/status/functional")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == evidence
    assert response.json()["checks"][0]["status"] == "failed"
