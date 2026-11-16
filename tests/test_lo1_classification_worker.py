import importlib.util
from pathlib import Path
from unittest.mock import Mock

import httpx

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lo1_classification_worker", ROOT / "discovery/appsmith_discovery.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_old_inventory_snapshot_does_not_skip_fresh_api_assessment(monkeypatch):
    response = httpx.Response(200, request=httpx.Request("POST", "http://test/"),
                             json={"action": "pending", "ml_classification_status": "pending", "pending_reasons": ["owner_attestation_required"]})
    post = Mock(return_value=response)
    monkeypatch.setattr(worker.httpx, "post", post)
    worker.trigger_classification({"id": "test-id", "name": "Test app", "ml_classification_status": "assessed"})
    assert post.call_args.args[0].endswith("/applications/test-id/ml-classify-if-needed")
    assert "json" not in post.call_args.kwargs  # API assembles facts, not stale worker data.


def test_inventory_retry_covers_appsmith_and_keeps_unrelated_platforms_separate(monkeypatch):
    monkeypatch.setattr(worker, "get_inventory", lambda: {
        "a": {"id": "a", "platform": "appsmith"}, "b": {"id": "b", "platform": "other"}})
    called = []
    monkeypatch.setattr(worker, "trigger_classification", lambda application: called.append(application["id"]))
    worker.reconcile_inventory_classifications()
    assert called == ["a"]


def test_ml_failure_does_not_escape_into_discovery_cycle(monkeypatch, capsys):
    monkeypatch.setattr(worker.httpx, "post", Mock(side_effect=httpx.ConnectError("secret sentinel")))
    worker.trigger_classification({"id": "a", "name": "Test app"})
    assert "secret sentinel" not in capsys.readouterr().err
