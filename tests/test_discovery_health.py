import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "discovery"))

import discovery_health as health

spec = importlib.util.spec_from_file_location(
    "discovery_health_worker_tests",
    ROOT / "discovery/appsmith_discovery.py",
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


@pytest.mark.parametrize("value,now,expected", [
    ("100", 100, True),
    ("100", 280, True),
    ("100", 281, False),
    ("100", 99, False),
    ("nan", 100, False),
    ("inf", 100, False),
    ("invalid", 100, False),
    ("", 100, False),
])
def test_freshness_and_invalid_evidence(tmp_path, value, now, expected):
    path = tmp_path / "status"
    path.write_text(value)
    assert health.is_healthy(path, now=now) is expected


def test_missing_evidence_is_unhealthy(tmp_path):
    assert not health.is_healthy(tmp_path / "absent", now=100)


def test_record_and_clear(tmp_path, monkeypatch):
    path = tmp_path / "status"
    monkeypatch.setattr(health.time, "monotonic", lambda: 100)
    health.record_success(path)
    assert health.is_healthy(path, now=101)
    health.clear_success(path)
    assert not health.is_healthy(path, now=101)
    health.clear_success(path)


@pytest.mark.parametrize("fails", [False, True])
def test_worker_startup_and_cycle_result(tmp_path, monkeypatch, fails):
    path = tmp_path / "status"
    path.write_text("100")
    events = []

    def clear():
        events.append("clear")
        health.clear_success(path)

    def cycle():
        events.append("cycle")
        assert not path.exists(), "Startup must remove old evidence"
        if fails:
            raise RuntimeError("Simulated cycle failure")

    def record():
        events.append("record")
        health.record_success(path)

    def stop(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "clear_success", clear)
    monkeypatch.setattr(worker, "record_success", record)
    monkeypatch.setattr(worker, "run_discovery_cycle", cycle)
    monkeypatch.setattr(worker.time, "sleep", stop)

    with pytest.raises(KeyboardInterrupt):
        worker.main()

    assert events == (
        ["clear", "cycle", "clear"] if fails
        else ["clear", "cycle", "record"]
    )
    assert path.exists() is (not fails)


def test_failed_cycle_clears_previous_success(tmp_path, monkeypatch):
    path = tmp_path / "status"
    cycles = []

    def cycle():
        cycles.append(1)
        if len(cycles) == 2:
            assert path.exists()
            raise RuntimeError("Simulated cycle failure")

    def sleep(_):
        if len(cycles) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(worker, "clear_success",
                        lambda: health.clear_success(path))
    monkeypatch.setattr(worker, "record_success",
                        lambda: health.record_success(path))
    monkeypatch.setattr(worker, "run_discovery_cycle", cycle)
    monkeypatch.setattr(worker.time, "sleep", sleep)

    with pytest.raises(KeyboardInterrupt):
        worker.main()

    assert len(cycles) == 2
    assert not path.exists()
