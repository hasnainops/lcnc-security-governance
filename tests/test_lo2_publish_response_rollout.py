"""Verify response-fix rollout retains the proxy guard, including on failure."""
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("response_rollout",
    Path(__file__).resolve().parents[1] / "scripts/rollout-lo2-publish-response.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    events, failure = [], {"stage": None}
    body = {"allowed": False, "scope": repair.base.VERSION,
            "reasons": ["unique_discovered_application_required"],
            "responseMeta": {"status": 403, "success": False,
                             "error": {"code": "LCNC-PUBLISH-DENIED", "message": "Blocked"}}}
    def run(*args, **kwargs):
        events.append(args)
        if args[:3] == ("git", "rev-parse", "--absolute-git-dir"):
            return str(tmp_path)
        if "cat" in args:
            return (repair.base.ROOT / "appsmith/publish-guard.Caddyfile").read_text()
        if "build" in args and failure["stage"] == "build":
            raise RuntimeError("build failed")
    def service(name):
        return {"service": name, "container": name, "image_id": "image-" + name,
                "command": repair.GUARDED_COMMAND if failure["stage"] != "unguarded" else []}
    def probe(name):
        events.append(("probe", name))
        if failure["stage"] == "replica_b" and name == "governance-api-b":
            return {"status": 403, "body": {"allowed": False}}
        return {"status": 403, "body": body}
    monkeypatch.setattr(repair.base, "run", run)
    monkeypatch.setattr(repair.base, "runtime", service)
    monkeypatch.setattr(repair.base, "probe_replica", probe)
    monkeypatch.setattr(repair.base, "http", lambda *args: (403, {}, body))
    return events, failure, tmp_path


def test_updates_only_apis_and_verifies_first_before_second(runtime):
    events, _, path = runtime
    repair.main()
    updates = [e for e in events if "up" in e]
    assert [e[-1] for e in updates] == list(repair.base.APIS)
    assert events.index(("probe", "governance-api-a")) < events.index(updates[1])
    assert all("--no-deps" in e and "--no-build" in e for e in updates)
    assert any((p / "installation.json").exists() for p in path.iterdir())


@pytest.mark.parametrize("stage", ["unguarded", "build", "replica_b"])
def test_failure_never_restores_unguarded_proxy(runtime, stage):
    events, failure, _ = runtime
    failure["stage"] = stage
    with pytest.raises(RuntimeError):
        repair.main()
    updates = [e for e in events if "up" in e]
    assert not any("appsmith-proxy" in e or "opa" in e or "appsmith" in e for e in updates)
    if stage == "replica_b":
        assert "-f" in updates[-1]
        assert updates[-1][-2:] == repair.base.APIS
    else:
        assert not updates
