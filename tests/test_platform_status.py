"""Failure and disclosure boundaries for the host-observation/API contract."""

import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("platform_status_tests")
package.__path__ = [str(ROOT / "governance-api/app")]
sys.modules[package.__name__] = package
status = importlib.import_module("platform_status_tests.platform_status")
route = importlib.import_module("platform_status_tests.status_routes")
spec = importlib.util.spec_from_file_location("exam_collector_tests", ROOT / "scripts/collect-platform-status.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
NOW = datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)
IMAGE = "sha256:" + "a" * 64


def record(service="governance-api-a", **changes):
    return {"service": service, "project": "lcnc-security-governance", "oneoff": "False",
            "state": "running", "health": "healthy", "image_id": IMAGE, **changes}


def snapshot(records=None, when=NOW):
    if records is None:
        records = [record(name) for name in status.SERVICES]
    return status.build_snapshot(records, when.isoformat())


def read(tmp_path, data):
    path = tmp_path / "status.json"
    path.write_text(json.dumps(data))
    return status.read_platform_status(path, NOW)


def test_healthy_and_not_configured_are_distinct(tmp_path):
    records = [record(name, health=None if name == "opa" else "healthy") for name in status.SERVICES]
    result = read(tmp_path, snapshot(records))
    assert result["observation_status"] == "current"
    assert result["summary"] == {"expected_services": 20, "running": 20,
                                  "docker_healthy": 19, "health_not_configured": 1,
                                  "missing": 0, "multiple": 0}
    assert all(s["functional_check"]["status"] == "not_configured" for s in result["services"])


def test_missing_duplicate_and_stopped_are_not_healthy(tmp_path):
    data = snapshot([record(), record(), record("opa", state="exited")])
    result = read(tmp_path, data)
    by_name = {s["service"]: s for s in result["services"]}
    assert result["summary"]["missing"] == 18
    assert by_name["governance-api-a"]["container_state"] == "multiple"
    assert by_name["governance-api-a"]["container_count"] == 2
    assert by_name["governance-api-a"]["docker_health"] == "unknown"
    assert result["summary"]["docker_healthy"] == 0
    assert by_name["opa"]["container_state"] == "exited"


@pytest.mark.parametrize("age,expected", [(30,"current"), (31,"stale"), (3600,"stale"), (-1,"unavailable")])
def test_freshness_boundaries(tmp_path, age, expected):
    result = read(tmp_path, snapshot(when=NOW - timedelta(seconds=age)))
    assert result["observation_status"] == expected
    assert all(s["observation_status"] == expected for s in result["services"])
    if expected != "current":
        assert result["summary"]["running"] is None
        assert result["summary"]["docker_healthy"] is None


def test_missing_file_is_unavailable_not_empty_platform(tmp_path):
    result = status.read_platform_status(tmp_path / "absent.json", NOW)
    assert result["reason"] == "snapshot_missing"
    assert len(result["services"]) == 20
    assert all(s["container_state"] == "unknown" for s in result["services"])
    assert result["summary"]["missing"] is None


@pytest.mark.parametrize("payload", [b"not json", b"[1]", b"\xff", b"x" * (128 * 1024 + 1)])
def test_bad_or_oversized_file_never_raises_or_exposes_bytes(tmp_path, payload):
    path = tmp_path / "status.json"
    path.write_bytes(payload)
    result = status.read_platform_status(path, NOW)
    assert result["observation_status"] == "unavailable"
    assert result["reason"] == "snapshot_invalid"


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema_version=True),
    lambda d: d.update(observed_at="2026-10-19T08:00:00"),
    lambda d: d["services"].pop(),
    lambda d: d["services"].__setitem__(1, d["services"][0]),
    lambda d: d["services"][0].update(container_state="running", container_count=0),
    lambda d: d["services"][0].update(image_ids=[{"secret":"must-not-leak"}]),
    lambda d: d["services"][0].update(docker_health="password=must-not-leak"),
    lambda d: d["services"][0].update(observed_at="2099-01-01T00:00:00Z"),
])
def test_invalid_contract_fails_as_unavailable(tmp_path, mutation):
    data = snapshot()
    mutation(data)
    result = read(tmp_path, data)
    assert result["observation_status"] == "unavailable"
    assert "must-not-leak" not in json.dumps(result)


def test_extra_fields_are_discarded_by_both_boundaries(tmp_path):
    data = snapshot([record(Env=["TOKEN=must-not-leak"], Log="must-not-leak")])
    assert "must-not-leak" not in json.dumps(data)
    data["Env"] = ["TOKEN=must-not-leak"]
    data["services"][0]["logs"] = "must-not-leak"
    data["services"][0]["functional_check"] = {"status":"healthy"}
    result = read(tmp_path, data)
    assert "must-not-leak" not in json.dumps(result)
    assert all(s["functional_check"]["status"] == "not_configured" for s in result["services"])


def docker_runner(records=None, ids=None):
    records = [record()] if records is None else records
    ids = ["b" * 64] * len(records) if ids is None else ids
    commands = []

    def run(args):
        commands.append(args)
        if args[-2:] == ["config", "--services"]:
            return "\n".join(status.SERVICES)
        if "ps" in args:
            return "\n".join(ids)
        return "\n".join(json.dumps(r) for r in records)

    return run, commands


def test_collector_scopes_project_and_uses_only_formatted_inspection():
    run, commands = docker_runner()
    result = collector.collect(run)
    assert result["collection_status"] == "ok"
    assert "--project-directory" in commands[0]
    assert "--orphans=false" in commands[1]
    assert commands[2][:3] == ["docker", "inspect", "--type=container"]
    assert "--format" in commands[2]
    assert ".Config.Env" not in collector.INSPECT_FORMAT
    assert ".State.Health.Log" not in collector.INSPECT_FORMAT


def test_empty_project_is_missing_not_docker_failure():
    run, commands = docker_runner([])
    data = collector.collect(run)
    assert data["collection_status"] == "ok"
    assert all(s["container_state"] == "missing" for s in data["services"])
    assert len(commands) == 2


@pytest.mark.parametrize("failure,reason", [
    (FileNotFoundError("must-not-leak"), "docker_unavailable"),
    (subprocess.CalledProcessError(1,"docker",stderr="must-not-leak"), "docker_unavailable"),
    (subprocess.TimeoutExpired("docker",5), "docker_timeout"),
    (ValueError("must-not-leak"), "invalid_docker_output"),
])
def test_docker_failures_replace_old_green_state(tmp_path, monkeypatch, failure, reason):
    monkeypatch.setattr(collector.contract, "utc_now", lambda: NOW)
    def run(_):
        raise failure
    data = collector.collect(run)
    assert data["reason"] == reason
    result = read(tmp_path, data)
    assert result["observation_status"] == "unavailable"
    assert result["reason"] == reason
    assert result["summary"]["docker_healthy"] is None
    assert "must-not-leak" not in json.dumps(result)


def test_catalog_drift_is_reported():
    data = collector.collect(lambda _: "\n".join(status.SERVICES) + "\nnew-service")
    assert data["reason"] == "catalog_mismatch"


def test_invalid_container_id_is_never_passed_to_inspect():
    run, commands = docker_runner(ids=["--some-option"])
    assert collector.collect(run)["reason"] == "invalid_docker_output"
    assert len(commands) == 2


def test_partial_inspection_is_unavailable():
    run, _ = docker_runner(records=[], ids=["a" * 64])
    assert collector.collect(run)["reason"] == "invalid_docker_output"


def test_oneoff_is_ignored_and_mixed_projects_rejected():
    data = snapshot([record(oneoff="True")])
    assert all(s["container_state"] == "missing" for s in data["services"])
    with pytest.raises(ValueError):
        snapshot([record(), record("opa", project="other-project")])


def test_snapshot_replacement_is_readable_by_both_api_readers(tmp_path):
    path = tmp_path / "observations/status.json"
    collector.write_snapshot(snapshot(), path)
    assert path.stat().st_mode & 0o777 == 0o644
    assert path.parent.stat().st_mode & 0o777 == 0o755
    first = status.read_platform_status(path, NOW)
    collector.write_snapshot(snapshot([record(state="exited")]), path)
    a = status.read_platform_status(path, NOW)
    b = status.read_platform_status(path, NOW)
    assert first["summary"]["running"] == 20
    assert a == b
    assert a["summary"]["running"] == 0
    assert not list(path.parent.glob(".status-*"))


def test_http_route_returns_no_store_and_safe_unavailable_result(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "read_platform_status", lambda: status.read_platform_status(tmp_path / "absent", NOW))
    app = FastAPI()
    app.include_router(route.router)
    with TestClient(app) as client:
        response = client.get("/status/platform")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["observation_status"] == "unavailable"
        assert len(response.json()["services"]) == 20


def test_compose_catalog_and_readonly_mounts_match():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert set(compose["services"]) == set(status.SERVICES)
    for name in ("governance-api-a", "governance-api-b"):
        volumes = compose["services"][name]["volumes"]
        assert "./.runtime-observability:/run/observability:ro" in volumes
        assert not any("docker.sock" in str(v) for v in volumes)


@pytest.mark.parametrize("failed", [False, True])
def test_one_shot_exit_code_and_safe_output(tmp_path, monkeypatch, capsys, failed):
    data = status.collection_failure("docker_unavailable", NOW.isoformat()) if failed else snapshot()
    monkeypatch.setattr(sys, "argv", ["collect-platform-status.py", "--once"])
    monkeypatch.setattr(collector, "collect", lambda: data)
    original_write = collector.write_snapshot
    path = tmp_path / "status.json"
    monkeypatch.setattr(collector, "write_snapshot", lambda data: original_write(data, path))
    assert collector.main() == int(failed)
    assert json.loads(path.read_text()) == data
    assert "collection=" in capsys.readouterr().out


def test_continuous_mode_stops_on_interrupt(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["collect-platform-status.py"])
    monkeypatch.setattr(collector, "collect", snapshot)
    monkeypatch.setattr(collector, "write_snapshot", lambda _: None)
    def interrupt(_):
        raise KeyboardInterrupt
    monkeypatch.setattr(collector.time, "sleep", interrupt)
    assert collector.main() == 0
    assert "Collector stopped" in capsys.readouterr().out


def test_write_failure_exits_without_disclosing_os_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["collect-platform-status.py", "--once"])
    monkeypatch.setattr(collector, "collect", snapshot)
    def fail(_):
        raise OSError("must-not-leak")
    monkeypatch.setattr(collector, "write_snapshot", fail)
    assert collector.main() == 1
    assert "must-not-leak" not in capsys.readouterr().out


def test_failed_atomic_replace_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    collector.write_snapshot(snapshot(), path)
    previous = path.read_bytes()
    def fail(*_):
        raise OSError("replacement failed")
    monkeypatch.setattr(collector.os, "replace", fail)
    with pytest.raises(OSError):
        collector.write_snapshot(snapshot([]), path)
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob(".status-*"))


def test_command_bounds_runtime_and_discards_stderr(monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="ok")
    monkeypatch.setattr(collector.subprocess, "run", run)
    assert collector.command(["docker", "compose", "ps"]) == "ok"
    assert calls[0][1]["timeout"] == 5
    assert calls[0][1]["stderr"] == subprocess.DEVNULL
    assert calls[0][1]["check"] is True
    assert calls[0][1]["cwd"] == ROOT
