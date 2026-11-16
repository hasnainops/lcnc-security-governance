"""PostgreSQL integration: initial inference, retry, evidence and concurrency."""
import importlib
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from test_lo1_classification_postgres import database_connection, scenario
from test_lo1_feature_persistence import setup_case


def prepare(scenario, monkeypatch):
    persistence, connect, app_id, add, read = setup_case(scenario, monkeypatch)
    module = importlib.import_module(persistence.__package__ + '.snapshot_assessment')
    monkeypatch.setattr(module, 'get_connection', connect)
    with connect() as connection:
        connection.execute((__import__('pathlib').Path(__file__).resolve().parents[1] / 'database/migrations/006_ml_analytics.sql').read_text())
    calls = []
    identity = {'model_version': 'configuration-snapshot-v1', 'model_sha256': 'a'*64}
    def get(url, **kwargs):
        return httpx.Response(200, json=identity, request=httpx.Request('GET', url))
    def post(url, **kwargs):
        calls.append(kwargs['json'])
        return httpx.Response(200, json={**identity, 'analysis_type': 'configuration-snapshot',
            'authority': 'advisory', 'features_evaluated': list(module.NAMES),
            'anomalous': True, 'raw_decision_score': -0.1}, request=httpx.Request('POST', url))
    monkeypatch.setattr(module.httpx, 'get', get)
    monkeypatch.setattr(module.httpx, 'post', post)
    obs, values = add()
    persistence.persist_current_features(app_id, obs, values)
    return module, connect, app_id, add, read, calls, identity


def test_new_app_assessed_without_any_change_history(scenario, monkeypatch):
    module, connect, app_id, add, read, calls, identity = prepare(scenario, monkeypatch)
    result = module.assess_snapshot_if_needed(app_id)
    assert result['action'] == 'assessed'
    assert result['temporal_history_evaluated'] is False
    assert len(calls) == 1 and 'changes_last_24h' not in calls[0]
    assert read()['changes_last_24h'] is None
    assert read()['ml_anomaly_status'] == 'assessed'
    assert read()['shadow_it_candidate'] is True
    add()
    assert module.assess_snapshot_if_needed(app_id)['action'] == 'unchanged'
    assert len(calls) == 1
    with connect() as connection:
        rows = connection.execute('SELECT * FROM ml_assessments WHERE application_id=%s', (app_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]['context_signals'][0]['snapshot_evidence']['source_observation_id'] == result['source_observation_id']


def test_concurrent_replicas_create_one_assessment(scenario, monkeypatch):
    module, connect, app_id, add, read, calls, identity = prepare(scenario, monkeypatch)
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(module.assess_snapshot_if_needed, [app_id, app_id]))
    assert sorted(x['action'] for x in results) == ['assessed', 'unchanged']
    assert len(calls) == 1


def test_model_digest_change_reassesses(scenario, monkeypatch):
    module, connect, app_id, add, read, calls, identity = prepare(scenario, monkeypatch)
    module.assess_snapshot_if_needed(app_id)
    identity['model_sha256'] = 'b'*64
    assert module.assess_snapshot_if_needed(app_id)['action'] == 'assessed'
    assert len(calls) == 2


def test_incomplete_latest_evidence_blocks_inference(scenario, monkeypatch):
    module, connect, app_id, add, read, calls, identity = prepare(scenario, monkeypatch)
    add(complete=False)
    assert module.assess_snapshot_if_needed(app_id)['reason'] == 'complete_configuration_features_required'
    assert not calls


def test_bad_model_response_persists_nothing_then_retry_succeeds(scenario, monkeypatch):
    module, connect, app_id, add, read, calls, identity = prepare(scenario, monkeypatch)
    post = module.httpx.post
    monkeypatch.setattr(module.httpx, 'post', lambda url, **kw: httpx.Response(
        200, json={'anomalous': 'true'}, request=httpx.Request('POST', url)))
    assert module.assess_snapshot_if_needed(app_id)['action'] == 'pending'
    with connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM ml_assessments WHERE application_id=%s', (app_id,)).fetchone()['n'] == 0
    monkeypatch.setattr(module.httpx, 'post', post)
    assert module.assess_snapshot_if_needed(app_id)['action'] == 'assessed'


def test_real_ingestion_route_automatically_assesses_snapshot(scenario, monkeypatch):
    module, connect, app_id, add, read, calls, identity = prepare(scenario, monkeypatch)
    package = module.__package__
    database = importlib.import_module(package + '.database')
    store = importlib.import_module(package + '.observation_store')
    monkeypatch.setattr(database, 'get_connection', connect)
    monkeypatch.setattr(store, 'get_connection', connect)
    from lo1_classification_support import observation
    # Execute the production route body without registering global metrics twice.
    import ast
    from pathlib import Path
    from uuid import UUID
    contract = importlib.import_module(package + '.discovery_observation')
    assembly = importlib.import_module(package + '.feature_assembly')
    source = Path(module.__file__).with_name('main.py')
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == 'ingest_discovery_observation')
    node.decorator_list = []
    namespace = {'__package__': package, 'UUID': UUID,
                 'AppsmithObservation': contract.AppsmithObservation,
                 'persist_discovery_observation': store.persist_discovery_observation,
                 'assemble_features': assembly.assemble_features}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
    payload = contract.AppsmithObservation.model_validate(observation(read()['external_id']))
    result = namespace['ingest_discovery_observation'](app_id, payload)
    assert result['feature_assembly']['initial_assessment']['action'] == 'assessed'
    assert result['feature_assembly']['features']['changes_last_24h'] is None
    assert read()['ml_anomaly_status'] == 'assessed'


def test_temporal_assessment_is_not_downgraded_to_snapshot(scenario, monkeypatch):
    module, connect, app_id, add, read, calls, identity = prepare(scenario, monkeypatch)
    with connect() as connection:
        connection.execute('UPDATE applications SET changes_last_24h=2 WHERE id=%s', (app_id,))
    assert module.assess_snapshot_if_needed(app_id)['action'] == 'full_history_available'
    assert not calls
