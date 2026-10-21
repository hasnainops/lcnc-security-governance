import importlib.util
import io
from pathlib import Path
from unittest.mock import patch

import pytest

source = Path(__file__).resolve().parents[1] / "governance-api/app/platform_status.py"
spec = importlib.util.spec_from_file_location("snapshot_retry", source)
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


def test_transient_open_failure_recovers():
    with patch.object(Path, "is_file", return_value=True), \
         patch.object(Path, "is_symlink", return_value=False), \
         patch.object(Path, "open", side_effect=[
             FileNotFoundError(), io.BytesIO(b'{"recovered": true}')
         ]) as opened, \
         patch.object(status.time, "sleep") as sleep:
        assert status.load_snapshot("/test.json") == {"recovered": True}
    assert opened.call_count == 2
    sleep.assert_called_once_with(0.05)


def test_persistent_absence_remains_unavailable():
    with patch.object(Path, "is_file", return_value=True), \
         patch.object(Path, "is_symlink", return_value=False), \
         patch.object(Path, "open", side_effect=FileNotFoundError()) as opened, \
         patch.object(status.time, "sleep") as sleep:
        result = status.read_platform_status("/test.json")
    assert opened.call_count == 3
    assert sleep.call_count == 2
    assert result["reason"] == "snapshot_missing"
    assert result["observation_status"] == "unavailable"
    assert result["summary"]["running"] is None


def test_failed_preliminary_check_recovers():
    with patch.object(Path, "is_file", side_effect=[False, True]), \
         patch.object(Path, "is_symlink", return_value=False), \
         patch.object(Path, "open", return_value=io.BytesIO(b"{}")), \
         patch.object(status.time, "sleep") as sleep:
        assert status.load_snapshot("/test.json") == {}
    sleep.assert_called_once_with(0.05)


@pytest.mark.parametrize(
    "failure, reason",
    [
        (PermissionError(), "snapshot_unreadable"),
        (ValueError("invalid JSON"), "snapshot_invalid"),
    ],
)
def test_other_errors_are_not_retried(failure, reason):
    with patch.object(Path, "is_file", return_value=True), \
         patch.object(Path, "is_symlink", return_value=False), \
         patch.object(Path, "open", side_effect=failure) as opened, \
         patch.object(status.time, "sleep") as sleep:
        result = status.read_platform_status("/test.json")
    opened.assert_called_once()
    sleep.assert_not_called()
    assert result["reason"] == reason
    assert result["summary"]["running"] is None
