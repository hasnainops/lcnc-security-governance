"""Exercise rollout ordering/rollback without touching Docker or applications."""
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("publish_rollout",
    Path(__file__).resolve().parents[1] / "scripts/rollout-lo2-publish-guard.py")
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    events = []
    failure = {"stage": None}
    def run(*args, **kwargs):
        events.append(args)
        if args[:3] == ("git", "rev-parse", "--absolute-git-dir"):
            return str(tmp_path)
        if failure["stage"] == "policy_validation" and "/opa" in args:
            raise RuntimeError("policy test failed")
        if failure["stage"] == "build" and "build" in args:
            raise RuntimeError("build failed")
        return ""
    def service(name):
        return {"service": name, "container": name,
                "image_id": "sha256:6b08c1b9858ca9a7d99c1da13c3695081e0e604c6cf214ca26a7ce0e2c4fd9b4",
                "command": rollout.DIRECT, "ports": {}, "networks": ["test_appsmith_restricted"]}
    def probe(name):
        events.append(("probe", name))
        if failure["stage"] == "replica_b" and name == "governance-api-b":
            raise RuntimeError("replica failed")
        return {"status": 403, "body": {"allowed": False}}
    monkeypatch.setattr(rollout, "run", run)
    monkeypatch.setattr(rollout, "runtime", service)
    monkeypatch.setattr(rollout, "probe_replica", probe)
    monkeypatch.setattr(rollout, "inspect", lambda *args: {
        "org.opencontainers.image.revision": "d847cf495020767bfe53f4ead37a24513a51d7d4"})
    monkeypatch.setattr(rollout, "http", lambda *args: (403, {}, {
        "scope": rollout.VERSION, "reasons": ["unique_discovered_application_required"]}))
    return events, failure, tmp_path


def test_proxy_switch_only_after_both_replica_checks(runtime):
    events, _, path = runtime
    rollout.main()
    switch = next(i for i, e in enumerate(events) if "up" in e and e[-1] == "appsmith-proxy")
    assert events.index(("probe", "governance-api-a")) < switch
    assert events.index(("probe", "governance-api-b")) < switch
    assert not any("up" in e and ("appsmith" in e or "opa" in e) for e in events)
    assert any((p / "installation.json").exists() for p in path.iterdir())


@pytest.mark.parametrize("stage", ["policy_validation", "build", "replica_b"])
def test_failures_do_not_activate_guard_and_restore_if_services_changed(runtime, stage):
    events, failure, _ = runtime
    failure["stage"] = stage
    with pytest.raises(RuntimeError):
        rollout.main()
    switches = [e for e in events if "up" in e and e[-1] == "appsmith-proxy"]
    if stage == "replica_b":
        assert len(switches) == 1
        assert "-f" in switches[0]  # Only the saved rollback, never guard activation.
    else:
        assert not switches
