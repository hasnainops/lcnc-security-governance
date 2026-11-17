"""Connector identity, sanitized collection and server-owned trust semantics."""
import importlib
from copy import deepcopy
import json
import subprocess
from uuid import uuid4

import pytest

from lo1_classification_support import modules, observation


def stored_datasource(url='https://example.com/private?token=secret#fragment'):
    """Synthetic values in the datasource shape observed in live Appsmith."""
    return {
        'id': 'saved-one',
        'datasourceStorages': {'unused_env': {
            'id': 'storage-one', 'datasourceId': 'saved-one',
            'environmentId': 'unused_env',
            'datasourceConfiguration': {
                'url': url,
                'headers': [{'key': 'Authorization', 'value': 'secret'}],
                'authentication': {'password': 'secret'},
            },
            'isConfigured': True, 'isValid': True, 'invalids': [],
        }},
    }


def stored_connector(datasource):
    import appsmith_discovery as discovery
    sources = [datasource]
    references = [{'action_id': 'query-one', 'datasource_id': datasource['id']}]
    reconciliation = discovery.reconcile_action_datasources(sources, references)
    return discovery.build_verified_saved_connector_evidence(sources, reconciliation)[0]


def test_storage_layout_extracts_sanitized_saved_destination():
    datasource = stored_datasource()
    before = deepcopy(datasource)
    connector = stored_connector(datasource)
    assert connector == {
        'connector_id': 'saved-one', 'destination_state': 'observed',
        'uses_api_key': None,
        'destination': {'scheme': 'https', 'host': 'example.com'},
    }
    assert datasource == before
    assert 'secret' not in json.dumps(connector)
    assert 'private' not in json.dumps(connector)


@pytest.mark.parametrize('mutation', [
    'multiple_environments', 'empty_storages', 'list_storages', 'null_storages',
    'malformed_storage', 'wrong_datasource', 'missing_datasource',
    'missing_configuration', 'malformed_configuration', 'conflicting_legacy_url',
])
def test_storage_layout_ambiguous_or_invalid_destination_stays_unknown(mutation):
    datasource = stored_datasource()
    storage = datasource['datasourceStorages']['unused_env']
    if mutation == 'multiple_environments':
        datasource['datasourceStorages']['another_env'] = deepcopy(storage)
    elif mutation == 'empty_storages':
        datasource['datasourceStorages'] = {}
    elif mutation == 'list_storages':
        datasource['datasourceStorages'] = [storage]
    elif mutation == 'null_storages':
        datasource['datasourceStorages'] = None
    elif mutation == 'malformed_storage':
        datasource['datasourceStorages']['unused_env'] = 'not-an-object'
    elif mutation == 'wrong_datasource':
        storage['datasourceId'] = 'another-datasource'
    elif mutation == 'missing_datasource':
        storage.pop('datasourceId')
    elif mutation == 'missing_configuration':
        storage.pop('datasourceConfiguration')
    elif mutation == 'malformed_configuration':
        storage['datasourceConfiguration'] = []
    elif mutation == 'conflicting_legacy_url':
        datasource['datasourceConfiguration'] = {'url': 'https://different.example.com'}
    connector = stored_connector(datasource)
    assert connector['destination_state'] == 'unresolved'
    assert 'destination' not in connector


@pytest.mark.parametrize('url', [None, '', '{{dynamicUrl}}', 'https://{{host}}/',
                                'https://user:secret@example.com', 'https://example.com:0',
                                'postgres://database:5432'])
def test_storage_layout_unsafe_or_missing_url_stays_unknown(url):
    assert stored_connector(stored_datasource(url))['destination_state'] == 'unresolved'


def test_storage_layout_matching_legacy_url_is_supported():
    datasource = stored_datasource('https://example.com')
    datasource['datasourceConfiguration'] = {'url': 'https://example.com'}
    assert stored_connector(datasource)['destination']['host'] == 'example.com'


def test_storage_layout_supplies_current_features_without_temporal_history(policy, monkeypatch):
    monkeypatch.setattr(policy, 'resolve_hosts', lambda hosts: {h: ['8.8.8.8'] for h in hosts})
    contract = importlib.import_module(policy.__package__ + '.discovery_observation')
    payload = observation()
    payload['connectors'] = [stored_connector(stored_datasource())]
    result = policy.assemble_governed_features(contract.AppsmithObservation.model_validate(payload), uuid4())
    assert result['features'] == {
        'connector_count': 1, 'external_integration_count': 1,
        'unapproved_integration_count': 1, 'external_domain_count': 1,
        'changes_last_24h': None,
    }
    assert result['evidence']['pending_reasons'] == []


@pytest.fixture
def policy(monkeypatch):
    services = modules(monkeypatch)
    package = services.automatic_classification.__package__
    module = importlib.import_module(package + '.destination_policy')
    monkeypatch.setenv('CONTROLLED_EGRESS_APPROVED_HOSTS', 'approved.example.test')
    monkeypatch.setenv('DISCOVERY_INTERNAL_CIDRS', '')
    return module


def observed(policy, hosts, *, complete=True):
    contract = importlib.import_module(policy.__package__ + '.discovery_observation')
    payload = observation()
    payload['connectors'] = [
        {'connector_id': 'saved-' + str(i), 'destination_state': 'observed',
         'destination': {'scheme': 'https', 'host': host}}
        if host is not None else {'connector_id': 'saved-' + str(i), 'destination_state': 'unresolved'}
        for i, host in enumerate(hosts)]
    if not complete:
        payload.update(collection_complete=False, pending_reasons=['datasources_incomplete'])
    return contract.AppsmithObservation.model_validate(payload)


@pytest.mark.parametrize('host,addresses,boundary,expected', [
    ('approved.example.test', ['8.8.8.8'], '', 'approved_external'),
    ('other.example.test', ['8.8.8.8'], '', 'unapproved_external'),
    ('sub.approved.example.test', ['8.8.8.8'], '', 'unapproved_external'),
    ('approved.example.test', [], '', None),
    ('approved.example.test', ['10.20.0.3'], '', None),
    ('internal.example.test', ['10.20.0.3'], '10.20.0.0/24', 'internal'),
    ('internal.example.test', ['10.21.0.3'], '10.20.0.0/24', None),
    ('internal.example.test', ['10.20.0.3', '8.8.8.8'], '10.20.0.0/24', None),
    ('internal.example.test', ['fd00:1234::3'], 'fd00:1234::/64', 'internal'),
    ('other.example.test', ['2001:4860:4860::8888'], '', 'unapproved_external'),
    ('approved.example.test', ['127.0.0.1'], '10.20.0.0/24', None),
    ('approved.example.test', ['169.254.169.254'], '', None),
    ('approved.example.test', ['::1'], '', None),
    ('approved.example.test', ['::ffff:127.0.0.1'], '', None),
    ('approved.example.test', ['224.0.0.1'], '', None),
    ('internal.example.test', ['10.20.0.3'], '0.0.0.0/0', None),
    ('internal.example.test', ['10.20.0.3'], 'not-a-cidr', None),
])
def test_boundary_and_approval_are_independent(policy, monkeypatch, host, addresses, boundary, expected):
    monkeypatch.setenv('DISCOVERY_INTERNAL_CIDRS', boundary)
    monkeypatch.setattr(policy, 'resolve_hosts', lambda hosts: {host: addresses})
    result = policy.assemble_governed_features(observed(policy, [host]), uuid4())
    assert result['evidence']['connector_decisions'][0]['trust'] == expected
    assert result['features']['connector_count'] == 1
    assert result['features']['changes_last_24h'] is None
    assert result['features']['external_integration_count'] == (None if expected is None else int(expected != 'internal'))


def test_distinct_saved_connectors_and_distinct_hosts(policy, monkeypatch):
    monkeypatch.setattr(policy, 'resolve_hosts', lambda hosts: {h: ['8.8.8.8'] for h in hosts})
    data = observed(policy, ['approved.example.test', 'other.example.test', 'other.example.test'])
    result = policy.assemble_governed_features(data, uuid4())
    assert list(result['features'].values()) == [3, 2, 3, 2, None]


@pytest.mark.parametrize('setting', [None, 'https://wrong.example.test/path'])
def test_unavailable_approval_does_not_erase_known_external_counts(policy, monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv('CONTROLLED_EGRESS_APPROVED_HOSTS')
    else:
        monkeypatch.setenv('CONTROLLED_EGRESS_APPROVED_HOSTS', setting)
    monkeypatch.setattr(policy, 'resolve_hosts', lambda hosts: {h: ['8.8.8.8'] for h in hosts})
    result = policy.assemble_governed_features(observed(policy, ['other.example.test']), uuid4())
    assert list(result['features'].values()) == [1, None, 1, 1, None]
    assert result['evidence']['pending_reasons'] == ['approval_policy_unavailable']


def test_empty_policy_means_unapproved_and_unknown_is_not_zero(policy, monkeypatch):
    monkeypatch.setenv('CONTROLLED_EGRESS_APPROVED_HOSTS', '')
    monkeypatch.setattr(policy, 'resolve_hosts', lambda hosts: {h: ['8.8.8.8'] for h in hosts})
    result = policy.assemble_governed_features(observed(policy, ['other.example.test']), uuid4())
    assert result['features']['unapproved_integration_count'] == 1
    result = policy.assemble_governed_features(observed(policy, ['other.example.test', None]), uuid4())
    assert list(result['features'].values()) == [None, None, 2, None, None]
    assert result['evidence']['pending_reasons'] == ['destination_unresolved']
    result = policy.assemble_governed_features(observed(policy, []), uuid4())
    assert list(result['features'].values()) == [0, 0, 0, 0, None]


def test_partial_collection_does_not_resolve_or_count(policy, monkeypatch):
    def no_hosts(hosts):
        assert hosts == set()
        return {}
    monkeypatch.setattr(policy, 'resolve_hosts', no_hosts)
    result = policy.assemble_governed_features(observed(policy, ['other.example.test'], complete=False), uuid4())
    assert all(x is None for x in result['features'].values())


def test_policy_fingerprint_ignores_order_but_detects_revocation(policy, monkeypatch):
    monkeypatch.setenv('CONTROLLED_EGRESS_APPROVED_HOSTS', ' b.example.test, A.EXAMPLE.TEST. ')
    first = policy.load_policy()['policy_sha256']
    monkeypatch.setenv('CONTROLLED_EGRESS_APPROVED_HOSTS', 'a.example.test,b.example.test')
    assert policy.load_policy()['policy_sha256'] == first
    monkeypatch.setenv('CONTROLLED_EGRESS_APPROVED_HOSTS', 'a.example.test')
    assert policy.load_policy()['policy_sha256'] != first


def test_saved_datasource_extraction_uses_verified_identity_and_sanitizes():
    import appsmith_discovery as discovery
    datasources = [
        {'id': 'used', 'datasourceConfiguration': {'url': 'https://API.Example.Test:8443/private?q=secret#fragment',
                                                  'headers': [{'key': 'Authorization', 'value': 'secret'}]}},
        {'id': 'unused', 'datasourceConfiguration': {'url': 'https://unrelated.example.test'}},
    ]
    references = [{'action_id': 'one', 'datasource_id': 'used'},
                  {'action_id': 'two', 'datasource_id': 'used'}]
    reconciled = discovery.reconcile_action_datasources(datasources, references)
    connectors = discovery.build_verified_saved_connector_evidence(datasources, reconciled)
    assert connectors == [{'connector_id': 'used', 'destination_state': 'observed',
                            'uses_api_key': None, 'destination': {
                                'scheme': 'https', 'host': 'api.example.test', 'port': 8443}}]
    assert 'secret' not in json.dumps(connectors)
    assert 'unused' not in json.dumps(connectors)


@pytest.mark.parametrize('url', [None, '', '{{dynamicUrl}}', 'postgres://database:5432',
                                'https://user:password@example.test', 'https://{{host}}/',
                                'https://example.test:0/'])
def test_saved_unresolved_destination_stays_unknown(url):
    import appsmith_discovery as discovery
    datasources = [{'id': 'used', 'datasourceConfiguration': {'url': url}}]
    reconciled = discovery.reconcile_action_datasources(datasources, [{'action_id': 'one', 'datasource_id': 'used'}])
    result = discovery.build_verified_saved_connector_evidence(datasources, reconciled)
    assert result == [{'connector_id': 'used', 'destination_state': 'unresolved', 'uses_api_key': None}]


def test_dns_batch_is_bounded_and_preserves_completed_answers(policy, monkeypatch):
    def timeout(command, **kwargs):
        assert kwargs['timeout'] == 3
        assert len(json.loads(kwargs['input'])) == 64
        assert command[:2] == [policy.sys.executable, '-I']
        raise subprocess.TimeoutExpired(command, 3, output=b'["h0.example.test", ["8.8.8.8"]]\n')
    monkeypatch.setattr(policy.subprocess, 'run', timeout)
    result = policy.resolve_hosts(['h' + str(n) + '.example.test' for n in range(100)])
    assert result == {'h0.example.test': ['8.8.8.8']}


def test_real_dns_worker_supports_local_resolution_without_external_http(policy):
    result = policy.resolve_hosts(['localhost', '127.0.0.1'])
    assert result['127.0.0.1'] == ['127.0.0.1']
    assert result['localhost']
    assert policy._trust('localhost', result['localhost'], policy.load_policy())[0] is None


def test_collector_upgrade_is_not_counted_as_an_application_change(policy):
    from datetime import datetime, timedelta, timezone
    assembly = importlib.import_module(policy.__package__ + '.feature_assembly')
    base = observed(policy, [])
    end = datetime.now(timezone.utc)
    window = [base.model_copy(update={'observed_at': end-timedelta(minutes=1440-i),
                                     'collector_version': 'appsmith-discovery-v2'})
              for i in range(1441)]
    assert assembly.verified_changes_from_history(window, end) == 0
    window[0] = window[0].model_copy(update={'collector_version': 'appsmith-discovery-v1'})
    assert assembly.verified_changes_from_history(window, end) is None
