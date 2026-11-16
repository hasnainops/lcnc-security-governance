"""Real PostgreSQL and production ingestion; model HTTP replies are test fixtures.

These prove wiring and persisted state, not detection accuracy or live Appsmith
acceptance. The separate runtime checkpoint is required after deployment.
"""
import ast
import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from psycopg.types.json import Jsonb

from test_lo1_classification_postgres import database_connection, scenario
from test_lo1_snapshot_assessment import prepare
from lo1_classification_support import observation


def setup(scenario, monkeypatch):
    snapshot, connect, app_id, add, read, calls, identity = prepare(scenario, monkeypatch)
    package = snapshot.__package__
    policy = importlib.import_module(package + '.destination_policy')
    database = importlib.import_module(package + '.database')
    store = importlib.import_module(package + '.observation_store')
    contract = importlib.import_module(package + '.discovery_observation')
    monkeypatch.setattr(database, 'get_connection', connect)
    monkeypatch.setattr(store, 'get_connection', connect)
    monkeypatch.setenv('CONTROLLED_EGRESS_APPROVED_HOSTS', 'approved.example.test')
    monkeypatch.setenv('DISCOVERY_INTERNAL_CIDRS', '')
    answers = {'approved.example.test': ['8.8.8.8'], 'other.example.test': ['8.8.4.4']}
    monkeypatch.setattr(policy, 'resolve_hosts', lambda hosts: {h: answers.get(h, []) for h in hosts})
    source = Path(snapshot.__file__).with_name('main.py')
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == 'ingest_discovery_observation')
    node.decorator_list = []
    namespace = {'__package__': package, 'UUID': UUID,
                 'AppsmithObservation': contract.AppsmithObservation,
                 'persist_discovery_observation': store.persist_discovery_observation}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
    def send(host='other.example.test', *, complete=True, age=0):
        # Exercise saved-datasource extraction, then the real ingestion function.
        import appsmith_discovery as discovery
        datasources = [{'id': 'saved-api', 'datasourceConfiguration': {'url': 'https://' + host + '/?private=excluded'}}]
        references = [{'action_id': 'action-one', 'datasource_id': 'saved-api'}]
        reconciled = discovery.reconcile_action_datasources(datasources, references)
        payload = observation(read()['external_id'], datetime.now(timezone.utc) - timedelta(seconds=age))
        payload['connectors'] = discovery.build_verified_saved_connector_evidence(datasources, reconciled)
        if not complete:
            payload.update(collection_complete=False, pending_reasons=['actions_incomplete'])
        return namespace['ingest_discovery_observation'](app_id, contract.AppsmithObservation.model_validate(payload))
    return snapshot, connect, app_id, send, read, calls, answers, policy


def histories(connect, app_id):
    with connect() as db:
        return db.execute('SELECT * FROM ml_assessments WHERE application_id=%s ORDER BY assessed_at',
                          (app_id,)).fetchall()


def test_saved_connector_to_automatic_snapshot_and_unchanged_poll(scenario, monkeypatch):
    snapshot, connect, app_id, send, read, calls, answers, policy = setup(scenario, monkeypatch)
    first = send()
    assert first['feature_assembly']['initial_assessment']['action'] == 'assessed'
    assert calls == [{'external_integration_count': 1, 'unapproved_integration_count': 1,
                      'connector_count': 1, 'external_domain_count': 1}]
    current = read()
    assert current['ml_anomaly_status'] == 'assessed'
    assert current['shadow_it_candidate'] is True  # Explicit anomalous model fixture.
    assert current['changes_last_24h'] is None
    evidence = current['discovery_feature_evidence']
    assert evidence['source_observation_id'] == str(first['id'])
    assert evidence['connector_decisions'][0]['trust'] == 'unapproved_external'
    assert evidence['policy_sha256'] == policy.load_policy()['policy_sha256']
    saved = histories(connect, app_id)[0]['context_signals'][0]['snapshot_evidence']
    assert saved['destination_policy']['semantic_sha256'] == evidence['semantic_sha256']
    assert saved['temporal_history_evaluated'] is False
    second = send()
    assert second['feature_assembly']['initial_assessment']['action'] == 'unchanged'
    assert len(calls) == len(histories(connect, app_id)) == 1
    assert read()['discovery_feature_evidence']['source_observation_id'] == str(second['id'])
    assert saved['source_observation_id'] == str(first['id'])  # Immutable original inference source.


def test_approval_revocation_recomputes_and_rescores_same_configuration(scenario, monkeypatch):
    snapshot, connect, app_id, send, read, calls, answers, policy = setup(scenario, monkeypatch)
    send('approved.example.test')
    before = read()['discovery_feature_evidence']['policy_sha256']
    assert read()['unapproved_integration_count'] == 0
    monkeypatch.setenv('CONTROLLED_EGRESS_APPROVED_HOSTS', '')
    # Direct snapshot reassembly also sees the new policy, even before a new poll.
    assert snapshot.assess_snapshot_if_needed(app_id)['action'] == 'assessed'
    assert read()['unapproved_integration_count'] == 1
    assert read()['discovery_feature_evidence']['policy_sha256'] != before
    assert len(calls) == len(histories(connect, app_id)) == 2
    assert [r['features']['unapproved_integration_count'] for r in histories(connect, app_id)] == [0, 1]


def test_changed_destination_with_equal_counts_keeps_new_evidence(scenario, monkeypatch):
    snapshot, connect, app_id, send, read, calls, answers, policy = setup(scenario, monkeypatch)
    monkeypatch.setenv('CONTROLLED_EGRESS_APPROVED_HOSTS', '')
    send()
    first = read()['discovery_feature_evidence']
    result = send('approved.example.test')
    persisted = result['feature_assembly']['feature_persistence']
    assert persisted['feature_values_changed'] is False
    assert persisted['evidence_changed'] is True
    assert read()['discovery_feature_evidence']['semantic_sha256'] != first['semantic_sha256']
    assert len(histories(connect, app_id)) == 2


def test_dns_failure_invalidates_previous_score_and_recovery_is_automatic(scenario, monkeypatch):
    snapshot, connect, app_id, send, read, calls, answers, policy = setup(scenario, monkeypatch)
    send()
    answers.clear()
    failure = send()
    assert failure['feature_assembly']['initial_assessment']['action'] == 'pending'
    current = read()
    assert current['connector_count'] == 1
    assert current['external_integration_count'] is None
    assert current['ml_anomaly_status'] == 'stale'
    assert current['ml_anomalous'] is current['risk_score'] is current['governance_outcome'] is None
    assert current['shadow_it_candidate'] is False
    assert len(calls) == 1
    answers['other.example.test'] = ['8.8.4.4']
    assert send()['feature_assembly']['initial_assessment']['action'] == 'assessed'
    assert len(calls) == 2


def test_collection_failure_and_delayed_old_observation_cannot_restore_score(scenario, monkeypatch):
    snapshot, connect, app_id, send, read, calls, answers, policy = setup(scenario, monkeypatch)
    send()
    send(complete=False)
    assert read()['connector_count'] is None
    assert send(age=60)['feature_assembly']['ml_execution']['action'] == 'superseded'
    assert read()['connector_count'] is None
    assert read()['ml_anomaly_status'] == 'stale'
    assert len(calls) == 1


def test_model_failure_keeps_inventory_and_features_then_retries(scenario, monkeypatch):
    snapshot, connect, app_id, send, read, calls, answers, policy = setup(scenario, monkeypatch)
    real_post = snapshot.httpx.post
    monkeypatch.setattr(snapshot.httpx, 'post', lambda url, **kwargs: httpx.Response(
        503, request=httpx.Request('POST', url)))
    assert send()['feature_assembly']['initial_assessment']['reason'] == 'snapshot_inference_unavailable'
    assert read()['connector_count'] == read()['unapproved_integration_count'] == 1
    assert histories(connect, app_id) == []
    monkeypatch.setattr(snapshot.httpx, 'post', real_post)
    assert send()['feature_assembly']['initial_assessment']['action'] == 'assessed'


def test_concurrent_unchanged_polls_create_one_assessment(scenario, monkeypatch):
    snapshot, connect, app_id, send, read, calls, answers, policy = setup(scenario, monkeypatch)
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda _: send(), range(2)))
    assert len(histories(connect, app_id)) == len(calls) == 1
    assert read()['connector_count'] == 1


def test_new_column_works_under_existing_table_update_grants(scenario, monkeypatch):
    from psycopg import sql
    from uuid import uuid4
    snapshot, connect, app_id, send, read, calls, answers, policy = setup(scenario, monkeypatch)
    role = 'connector_test_' + uuid4().hex
    with connect() as db:
        # No new table or SECURITY DEFINER function is needed by this patch.
        db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        try:
            db.execute(sql.SQL('GRANT SELECT, UPDATE ON applications TO {}').format(sql.Identifier(role)))
            db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
            db.execute('UPDATE applications SET discovery_feature_evidence=%s WHERE id=%s',
                       (Jsonb({'test': True}), app_id))
            assert db.execute('SELECT discovery_feature_evidence FROM applications WHERE id=%s',
                              (app_id,)).fetchone()['discovery_feature_evidence'] == {'test': True}
        finally:
            db.execute('RESET ROLE')
            db.execute(sql.SQL('REVOKE ALL ON applications FROM {}').format(sql.Identifier(role)))
            db.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


@pytest.mark.parametrize('change_during_inference', [False, True])
def test_temporal_scorer_keeps_policy_provenance_and_rejects_superseded_inputs(
        scenario, monkeypatch, change_during_inference):
    snapshot, connect, app_id, send, read, calls, answers, policy = setup(scenario, monkeypatch)
    send()
    ml = importlib.import_module(snapshot.__package__ + '.ml')
    monkeypatch.setattr(ml, 'get_connection', connect)
    # Explicit fixture for an already verified historical feature. This does not
    # claim that these tests collected a live 24-hour observation window.
    with connect() as db:
        db.execute("UPDATE applications SET changes_last_24h=0, ml_anomaly_status='stale' WHERE id=%s", (app_id,))
    def reply(url, **kwargs):
        assert url.endswith('/analyze')
        assert kwargs['json']['unapproved_integration_count'] == 1
        if change_during_inference:
            with connect() as db:
                db.execute('UPDATE applications SET unapproved_integration_count=NULL WHERE id=%s', (app_id,))
        return httpx.Response(200, json={'analysis_type': 'anomaly', 'anomalous': True,
            'raw_decision_score': -0.1, 'model_version': 'explicit-temporal-test-fixture',
            'context_signals': []}, request=httpx.Request('POST', url))
    monkeypatch.setattr(ml.httpx, 'post', reply)
    result = ml.analyze_ml_if_needed(app_id)
    if change_during_inference:
        assert result == {'action': 'pending', 'reason': 'fresh_unchanged_features_required'}
        assert len(histories(connect, app_id)) == 1
    else:
        assert result['action'] == 'assessed'
        latest = histories(connect, app_id)[-1]
        assert latest['features']['changes_last_24h'] == 0
        assert latest['context_signals'][0]['discovery_feature_evidence']['policy_sha256'] == policy.load_policy()['policy_sha256']
