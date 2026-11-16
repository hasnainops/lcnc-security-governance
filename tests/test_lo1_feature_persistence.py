"""Real PostgreSQL tests for partial features, chronological guards and recovery."""
import importlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from test_lo1_classification_postgres import database_connection, scenario
from lo1_classification_support import observation


def setup_case(scenario, monkeypatch):
    services, connect, app_id, *_ = scenario
    package = services.automatic_classification.__package__
    module = importlib.import_module(package + '.feature_persistence')
    assembly = importlib.import_module(package + '.feature_assembly')
    contract = importlib.import_module(package + '.discovery_observation')
    monkeypatch.setattr(module, 'get_connection', connect)
    def add(complete=True, age=0):
        obs_id = uuid4()
        with connect() as connection:
            app = connection.execute('SELECT * FROM applications WHERE id=%s', (app_id,)).fetchone()
            payload = observation(app['external_id'], datetime.now(timezone.utc)-timedelta(seconds=age))
            if not complete:
                payload.update(collection_complete=False, pending_reasons=['actions_incomplete'])
            connection.execute('''INSERT INTO discovery_observations
                (id,application_id,source,observed_at,payload,payload_sha256)
                VALUES (%s,%s,'appsmith',%s,%s,%s)''',
                (obs_id, app_id, payload['observed_at'], Jsonb(payload), uuid4().hex * 2))
        values = assembly.assemble_features(contract.AppsmithObservation.model_validate(payload))['features']
        return obs_id, values
    def read():
        with connect() as connection:
            return connection.execute('SELECT * FROM applications WHERE id=%s', (app_id,)).fetchone()
    return module, connect, app_id, add, read


def test_zero_counts_persist_without_history_and_unchanged_poll_is_idempotent(scenario, monkeypatch):
    module, connect, app_id, add, read = setup_case(scenario, monkeypatch)
    obs, values = add()
    result = module.persist_current_features(app_id, obs, values)
    assert result['changed'] is True
    row = read()
    assert [row[name] for name in module.FEATURE_NAMES] == [0, 0, 0, 0, None]
    assert result['missing_features'] == ['changes_last_24h']
    before = row['updated_at']
    obs, values = add()
    assert module.persist_current_features(app_id, obs, values)['changed'] is False
    assert read()['updated_at'] == before


def test_incomplete_collection_clears_counts_and_dependent_decisions_then_recovers(scenario, monkeypatch):
    module, connect, app_id, add, read = setup_case(scenario, monkeypatch)
    obs, values = add()
    module.persist_current_features(app_id, obs, values)
    with connect() as connection:
        connection.execute("""UPDATE applications SET ml_anomaly_status='assessed',
            ml_anomalous=TRUE, shadow_it_candidate=TRUE, risk_status='assessed',
            risk_score=70, risk_level='high', governance_status='assessed',
            governance_outcome='review' WHERE id=%s""", (app_id,))
    obs, values = add(complete=False)
    module.persist_current_features(app_id, obs, values)
    row = read()
    assert all(row[name] is None for name in module.FEATURE_NAMES)
    assert row['shadow_it_candidate'] is False
    assert row['ml_anomalous'] is None
    assert row['risk_score'] is None
    assert row['governance_outcome'] is None
    assert row['ml_anomaly_status'] == row['risk_status'] == row['governance_status'] == 'stale'
    obs, values = add()
    module.persist_current_features(app_id, obs, values)
    assert read()['connector_count'] == 0
    assert read()['changes_last_24h'] is None


def test_late_observation_cannot_overwrite_newer_partial_evidence(scenario, monkeypatch):
    module, connect, app_id, add, read = setup_case(scenario, monkeypatch)
    older, values = add(age=60)
    newest, partial = add(complete=False)
    module.persist_current_features(app_id, newest, partial)
    assert module.persist_current_features(app_id, older, values)['action'] == 'superseded'
    assert read()['connector_count'] is None


@pytest.mark.parametrize('age', [181, -60])
def test_stale_or_future_latest_observation_cannot_supply_current_features(scenario, monkeypatch, age):
    module, connect, app_id, add, read = setup_case(scenario, monkeypatch)
    obs, values = add(age=age)
    result = module.persist_current_features(app_id, obs, values)
    assert result['action'] == 'stale_observation'
    assert read()['connector_count'] is None


@pytest.mark.parametrize('bad', [-1, True, 1.5, '0'])
def test_invalid_values_rejected_before_database_access(scenario, monkeypatch, bad):
    module, connect, app_id, add, read = setup_case(scenario, monkeypatch)
    obs, values = add()
    values['connector_count'] = bad
    with pytest.raises(ValueError):
        module.persist_current_features(app_id, obs, values)
    assert read()['connector_count'] is None
