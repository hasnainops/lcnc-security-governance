import importlib.util
from pathlib import Path
import pytest
from pydantic import ValidationError

spec = importlib.util.spec_from_file_location('snapshot_test_model', Path(__file__).resolve().parents[1]/'app/snapshot_analyzer.py')
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


def test_empty_configuration_runs_real_model_without_history():
    payload = dict.fromkeys(snapshot.artifact['features'], 0)
    result = snapshot.analyze_snapshot(snapshot.SnapshotFeatures(**payload).model_dump())
    assert type(result['anomalous']) is bool
    assert result['analysis_type'] == 'configuration-snapshot'
    assert result['authority'] == 'advisory'
    assert 'changes_last_24h' not in result['features_evaluated']
    assert len(result['model_sha256']) == 64
    assert result == snapshot.analyze_snapshot(payload)


@pytest.mark.parametrize('bad', [None, -1, True, '0', 1.5])
def test_model_rejects_unknown_or_coerced_counts(bad):
    payload = dict.fromkeys(snapshot.artifact['features'], 0)
    payload['connector_count'] = bad
    with pytest.raises(ValidationError):
        snapshot.SnapshotFeatures(**payload)


def test_model_rejects_history_feature():
    payload = dict.fromkeys(snapshot.artifact['features'], 0)
    with pytest.raises(ValidationError):
        snapshot.SnapshotFeatures(**payload, changes_last_24h=0)
