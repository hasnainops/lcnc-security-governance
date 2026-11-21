"""Real PostgreSQL orchestration tests; external services return explicit fixtures."""
import ast
import importlib
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import httpx
import pytest
from fastapi import Header, HTTPException
from fastapi.encoders import jsonable_encoder
from test_lo1_classification_postgres import database_connection as isolated_database_connection, scenario

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def database_connection(isolated_database_connection):
    # Roles are cluster-wide. Remove only the role this isolated module created.
    with isolated_database_connection() as db:
        existed = db.execute("SELECT 1 FROM pg_roles WHERE rolname='lcnc_governance_review_access'").fetchone()
    yield isolated_database_connection
    if not existed:
        with isolated_database_connection() as db:
            present = db.execute("SELECT 1 FROM pg_roles WHERE rolname='lcnc_governance_review_access'").fetchone()
            if present:
                db.execute('DROP OWNED BY lcnc_governance_review_access')
                db.execute('DROP ROLE lcnc_governance_review_access')


def authenticated_decision(ns, approval_id, payload):
    return ns['record_decision'](
        approval_id,
        payload,
        authorization='Bearer lo3-test-reviewer',
    )


def prepare(scenario, monkeypatch):
    services, connect, app_id, _, _, observe, *_ = scenario
    package = services.automatic_classification.__package__
    monkeypatch.setitem(sys.modules, package + '.metrics', MagicMock())
    module = importlib.import_module(package + '.automatic_governance')
    monkeypatch.setattr(module, 'get_connection', connect)
    with connect() as connection:
        connection.autocommit = True
        for name in ('003_risk_assessments.sql', '004_policy_decisions.sql',
                     '005_governance_workflow.sql', '014_governance_approvals.sql',
                     '024_automatic_governance_handoff.sql', '025_governance_review_lock.sql',
                     '027_lo2_verified_reviewer_authority.sql'):

            # The isolated PostgreSQL schema is reused across scenarios.
            # Migration 027 is not intended to execute repeatedly.
            if name == '027_lo2_verified_reviewer_authority.sql':

                database = connection.execute(
                    "SELECT current_database() AS name"
                ).fetchone()

                assert database['name'].startswith(
                    'lcnc_lo1_test_'
                ), "Refusing migration outside dedicated test database"

                existing = connection.execute(
                    '''
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_attribute
                        WHERE attrelid = 'approval_requests'::regclass
                          AND attname = 'verified_reviewer_policy'
                          AND NOT attisdropped
                    ) AS present
                    '''
                ).fetchone()

                if existing['present']:
                    continue

            connection.execute((ROOT / 'database/migrations' / name).read_text())
        connection.execute("""UPDATE applications SET ml_classification_status='assessed',
            ml_classification_review_required=TRUE, ml_anomaly_status='assessed',
            ml_anomalous=FALSE, security_scan_status='scanned', security_scan_passed=TRUE,
            risk_status='stale' WHERE id=%s""", (app_id,))
    observe()
    state = {'allow': True, 'outage': False, 'routes': 0}
    def post(url, **kwargs):
        if state['outage']:
            raise httpx.ConnectError('fixture outage')
        if url.endswith('/assess'):
            body = state.get('risk', {'score': 30, 'level': 'medium', 'model_version': 'test-risk', 'factors': []})
        else:
            body = {'result': {'allow': state['allow'], 'action': 'allow' if state['allow'] else 'deny',
                              'reasons': [] if state['allow'] else ['fixture mandatory block']}}
        return httpx.Response(200, json=body, request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(module, 'assign_required_training', lambda _: {'status': 'checked'})
    # Execute the actual approval-service route function against the same database.
    source = (ROOT / 'governance-automation/app/main.py').read_text()
    tree = ast.parse(source)
    names = {'route_settings', 'insert_event', 'route_application', 'record_decision', 'escalate_overdue', 'executive_summary'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for n in nodes:
        n.decorator_list = []
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from psycopg.types.json import Jsonb
    # Exercise the actual reviewer validator.
    # Only the external Vault lookup is replaced by a test fixture.
    from importlib.util import spec_from_file_location, module_from_spec
    from io import BytesIO
    import json

    reviewer_path = ROOT / 'governance-automation/app/reviewer_identity.py'

    spec = spec_from_file_location(
        '_lo3_test_reviewer_identity', reviewer_path
    )

    reviewer = module_from_spec(spec)
    spec.loader.exec_module(reviewer)

    class FixtureVaultClient:

        def open(self, request, timeout=3):

            assert request.full_url.endswith(
                '/v1/auth/token/lookup-self'
            )

            headers = {
                key.lower(): value
                for key, value in request.header_items()
            }

            token = headers.get('x-vault-token')

            if token == 'lo3-test-reviewer':
                policies = ['lcnc-security-reviewer']

            elif token == 'lo3-test-senior-reviewer':
                policies = ['lcnc-senior-security-reviewer']

            elif token == 'lo3-test-unprivileged':
                policies = ['default']

            else:
                raise reviewer.HTTPError(
                    request.full_url, 403,
                    'Fixture credential refused',
                    None, None,
                )

            return BytesIO(json.dumps({
                'data': {
                    'policies': policies,
                    'entity_id': (
                        '00000000-0000-4000-8000-000000000031'
                    ),
                }
            }).encode())

    monkeypatch.setattr(
        reviewer,
        'build_opener',
        lambda *args: FixtureVaultClient(),
    )

    ns = {'UUID': UUID, 'uuid4': uuid4, 'datetime': datetime, 'timedelta': timedelta,
          'timezone': timezone, 'Jsonb': Jsonb, 'get_connection': connect,
          'HTTPException': HTTPException, 'HumanDecision': object,
          'Header': Header,
          'jsonable_encoder': jsonable_encoder,
          'ReviewerAccessError': reviewer.ReviewerAccessError,
          'verified_reviewer': reviewer.verified_reviewer,
          'reviewer_policy_for_role': reviewer.reviewer_policy_for_role,
          'get_training_gate': lambda *a: {'approval_ready': True}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual approval service>', 'exec'), ns)
    def route(_):
        state['routes'] += 1
        if state.get('routing_down'):
            return {'status': 'routing_error'}
        return {'status': 'routed', 'approval': ns['route_application'](app_id)}
    monkeypatch.setattr(module, 'route_governance_approval', route)
    def rows(table):
        with connect() as c:
            return c.execute(f'SELECT * FROM {table} WHERE application_id=%s ORDER BY created_at', (app_id,)).fetchall()
    return module, connect, app_id, state, rows, ns


@contextmanager
def approval_runtime(connect, *, allow_lock=True):
    """Use the service's restricted DB grants, rather than the fixture owner."""
    from uuid import uuid4
    from psycopg import sql
    role = sql.Identifier('lo1_approval_' + uuid4().hex)
    with connect() as db:
        db.execute(sql.SQL('CREATE ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOLOGIN').format(role))
        db.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
        db.execute(sql.SQL('GRANT SELECT ON applications, governance_decisions, risk_assessments TO {}').format(role))
        db.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE ON approval_requests TO {}').format(role))
        db.execute(sql.SQL('GRANT INSERT ON approval_events TO {}').format(role))
        if allow_lock:
            db.execute(sql.SQL('GRANT lcnc_governance_review_access TO {} WITH INHERIT TRUE, SET FALSE').format(role))
    @contextmanager
    def workload_connection():
        with connect() as db:
            # SET ROLE survives the service's explicit commit, just like a real
            # login. The connection is closed before the role is dropped.
            db.execute(sql.SQL('SET ROLE {}').format(role))
            yield db
    try:
        yield workload_connection
    finally:
        with connect() as db:
            db.execute(sql.SQL('DROP OWNED BY {}').format(role))
            db.execute(sql.SQL('DROP ROLE {}').format(role))


def test_restricted_role_routes_and_reviews_without_application_write_access(scenario, monkeypatch):
    from psycopg.errors import InsufficientPrivilege
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    with approval_runtime(c) as workload:
        ns['get_connection'] = workload
        for query in (
            'SELECT id FROM applications WHERE id=%s FOR UPDATE',
            "UPDATE applications SET data_classification='public' WHERE id=%s",
            "UPDATE governance_decisions SET outcome='ALLOW' WHERE application_id=%s",
            'SELECT payload FROM discovery_observations WHERE application_id=%s',
        ):
            with pytest.raises(InsufficientPrivilege):
                with workload() as db:
                    db.execute(query, (app,))
        first = m.evaluate_governance_if_needed(app)
        assert first['approval_automation']['status'] == 'routed'
        approval = rows('approval_requests')[0]
        assert approval['required_role'] == 'Security/GRC Reviewer'
        authenticated_decision(ns, approval['id'], types.SimpleNamespace(
            decision='request_changes', actor='test-reviewer', reason='test'))
        again = m.evaluate_governance_if_needed(app)
        assert again['decision_id'] == first['decision_id']
        assert len(rows('approval_requests')) == 1
        assert rows('approval_requests')[0]['status'] == 'changes_requested'


def test_permission_repair_retries_persisted_decision_without_duplicates(scenario, monkeypatch):
    from psycopg.errors import InsufficientPrivilege
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    def delivery(_):
        try:
            return {'status': 'routed', 'approval': ns['route_application'](app)}
        except InsufficientPrivilege:
            return {'status': 'routing_error'}
    monkeypatch.setattr(m, 'route_governance_approval', delivery)
    with approval_runtime(c, allow_lock=False) as workload:
        ns['get_connection'] = workload
        first = m.evaluate_governance_if_needed(app)
        assert first['approval_automation']['status'] == 'routing_error'
        assert len(rows('governance_decisions')) == 1
        assert not rows('approval_requests')
    with approval_runtime(c) as workload:
        ns['get_connection'] = workload
        repaired = m.evaluate_governance_if_needed(app)
        assert repaired['action'] == 'reused'
        assert repaired['decision_id'] == first['decision_id']
        assert repaired['approval_automation']['status'] == 'routed'
        m.evaluate_governance_if_needed(app)
        assert len(rows('governance_decisions')) == len(rows('approval_requests')) == 1


def test_restricted_role_concurrent_routing_creates_one_request(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    with approval_runtime(c) as workload:
        ns['get_connection'] = workload
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(m.evaluate_governance_if_needed, [app, app]))
        assert all(result['approval_automation']['status'] == 'routed' for result in results)
        assert len(rows('governance_decisions')) == len(rows('approval_requests')) == 1


def test_restricted_role_human_review_rejects_expired_evidence(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    with approval_runtime(c) as workload:
        ns['get_connection'] = workload
        m.evaluate_governance_if_needed(app)
        approval = rows('approval_requests')[0]
        with c() as db:
            db.execute("UPDATE discovery_observations SET observed_at=NOW()-INTERVAL '10 minutes' WHERE application_id=%s", (app,))
        with pytest.raises(HTTPException) as error:
            authenticated_decision(ns, approval['id'], types.SimpleNamespace(
                decision='request_changes', actor='test-reviewer', reason='test'))
        assert error.value.status_code == 409
        assert 'Fresh discovery' in error.value.detail
        assert rows('approval_requests')[0]['status'] == 'pending'


def test_review_lock_is_not_executable_by_ungranted_role(scenario, monkeypatch):
    from psycopg.errors import InsufficientPrivilege
    _, c, app, *_ = prepare(scenario, monkeypatch)
    with approval_runtime(c, allow_lock=False) as workload:
        with pytest.raises(InsufficientPrivilege):
            with workload() as db:
                db.execute('SELECT public.lock_application_for_review(%s)', (app,))


def test_restricted_review_lock_conflicts_with_application_updates(scenario, monkeypatch):
    from psycopg.errors import LockNotAvailable
    _, c, app, *_ = prepare(scenario, monkeypatch)
    with approval_runtime(c) as workload:
        with workload() as locked:
            locked.execute('SELECT public.lock_application_for_review(%s)', (app,))
            with pytest.raises(LockNotAvailable):
                with c() as writer:
                    writer.execute("SET LOCAL lock_timeout='150ms'")
                    writer.execute('UPDATE applications SET updated_at=NOW() WHERE id=%s', (app,))
        # Committing the review releases its lock for normal application writes.
        with c() as writer:
            writer.execute("SET LOCAL lock_timeout='150ms'")
            writer.execute('UPDATE applications SET updated_at=NOW() WHERE id=%s', (app,))


def test_new_grants_do_not_prevent_dynamic_user_cleanup(scenario, monkeypatch):
    from uuid import uuid4
    from psycopg import sql
    _, c, app, *_ = prepare(scenario, monkeypatch)
    name = 'lo1_cleanup_' + uuid4().hex
    role = sql.Identifier(name)
    with c() as db:
        db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(role))
        db.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
        db.execute(sql.SQL('GRANT SELECT ON applications TO {}').format(role))
        db.execute(sql.SQL('GRANT lcnc_governance_review_access TO {} WITH INHERIT TRUE, SET FALSE').format(role))
        # The new access is inherited, so the default table/schema cleanup and
        # DROP ROLE need no new function/column revocation commands.
        db.execute(sql.SQL('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {}').format(role))
        db.execute(sql.SQL('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {}').format(role))
        db.execute(sql.SQL('REVOKE USAGE ON SCHEMA public FROM {}').format(role))
        db.execute(sql.SQL('DROP ROLE {}').format(role))
        assert not db.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (name,)).fetchone()


def test_routing_grants_preserve_vault_limits_and_existing_privileges():
    import runpy
    script = ROOT / 'scripts/configure-governance-routing-grants.py'
    updated = runpy.run_path(str(script))['updated_role']
    original = {'db_name': 'lcnc-postgres', 'creation_statements': [
        'CREATE ROLE "{{name}}" WITH LOGIN;', 'GRANT SELECT ON applications TO "{{name}}";'],
        'default_ttl': 900, 'max_ttl': 3600, 'credential_type': 'password',
        'credential_config': {}, 'revocation_statements': ['custom revocation'],
        'renew_statements': [], 'rollback_statements': []}
    result = updated(original)
    assert result['creation_statements'][:2] == original['creation_statements']
    assert len(original['creation_statements']) == 2
    assert len(result['creation_statements']) == 3
    assert all(result[k] == v for k, v in original.items() if k != 'creation_statements')
    assert updated(result) == result
    with pytest.raises(RuntimeError):
        updated({**original, 'future_setting': 'preserve me'})


def test_discovery_pipeline_calls_handoff_last(monkeypatch):
    tree = ast.parse((ROOT/'discovery/appsmith_discovery.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='run_ai_pipeline')
    calls = []
    ns = {name: (lambda app, name=name: calls.append(name)) for name in (
        'trigger_anomaly_analysis', 'trigger_classification', 'trigger_security_scan',
        'trigger_compliance_assessment', 'trigger_governance')}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<pipeline>', 'exec'), ns)
    ns['run_ai_pipeline']({'id': 'test'})
    assert calls[-1] == 'trigger_governance' and len(calls) == 5


def test_review_handoff_and_unchanged_poll_preserves_human_decision(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    first = m.evaluate_governance_if_needed(app)
    assert first['governance']['outcome'] == 'SECURITY_REVIEW'
    approval = rows('approval_requests')[0]
    assert approval['required_role'] == 'Security/GRC Reviewer'
    authenticated_decision(ns, approval['id'], types.SimpleNamespace(decision='request_changes', actor='test-reviewer', reason='test'))
    second = m.evaluate_governance_if_needed(app)
    assert second['action'] == 'reused' and second['decision_id'] == first['decision_id']
    assert len(rows('governance_decisions')) == len(rows('approval_requests')) == 1
    assert rows('approval_requests')[0]['status'] == 'changes_requested'


def test_policy_change_blocks_and_cannot_be_overridden(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    m.evaluate_governance_if_needed(app)
    state['allow'] = False
    result = m.evaluate_governance_if_needed(app)
    assert result['governance']['outcome'] == 'BLOCK'
    approvals = rows('approval_requests')
    assert approvals[0]['status'] == 'superseded'
    with pytest.raises(HTTPException) as error:
        authenticated_decision(ns, approvals[-1]['id'], types.SimpleNamespace(decision='approve', actor='test', reason='test'))
    assert error.value.status_code == 409


def test_routing_outage_retries_same_decision(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    state['routing_down'] = True
    first = m.evaluate_governance_if_needed(app)
    assert not rows('approval_requests')
    state['routing_down'] = False
    second = m.evaluate_governance_if_needed(app)
    assert second['decision_id'] == first['decision_id']
    assert len(rows('approval_requests')) == len(rows('governance_decisions')) == 1


def test_concurrent_replicas_create_one_decision_and_request(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(m.evaluate_governance_if_needed, [app, app]))
    assert {x['action'] for x in results} == {'evaluated', 'reused'}
    assert len(rows('approval_requests')) == len(rows('governance_decisions')) == 1


def test_opa_outage_rolls_back_and_does_not_route(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    # Risk succeeds; OPA alone fails.
    original = httpx.post
    def fail_policy(url, **kw):
        if '/v1/data/' in url:
            raise httpx.ConnectError('fixture')
        return original(url, **kw)
    monkeypatch.setattr(httpx, 'post', fail_policy)
    with pytest.raises(HTTPException): m.evaluate_governance_if_needed(app)
    assert not rows('governance_decisions') and state['routes'] == 0
    with c() as db:
        assert db.execute('SELECT count(*) AS n FROM risk_assessments WHERE application_id=%s', (app,)).fetchone()['n'] == 0


def test_stale_source_prevents_new_routing_and_human_decision(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    m.evaluate_governance_if_needed(app)
    approval = rows('approval_requests')[0]
    with c() as db:
        db.execute("UPDATE discovery_observations SET observed_at=NOW()-INTERVAL '10 minutes' WHERE application_id=%s", (app,))
    result = m.evaluate_governance_if_needed(app)
    assert result['action'] == 'pending' and state['routes'] == 1
    with pytest.raises(HTTPException) as error:
        authenticated_decision(ns, approval['id'], types.SimpleNamespace(decision='approve', actor='test', reason='test'))
    assert error.value.status_code == 409


def test_classification_flag_routes_review_even_with_known_classification(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    with c() as db:
        db.execute("UPDATE applications SET data_classification='internal' WHERE id=%s", (app,))
    result = m.evaluate_governance_if_needed(app)
    assert result['governance']['outcome'] == 'SECURITY_REVIEW'
    assert any('Advisory classification' in r for r in result['governance']['reasons'])


def test_changed_classification_supersedes_old_review(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    m.evaluate_governance_if_needed(app)
    with c() as db:
        db.execute("UPDATE applications SET data_classification='internal', ml_classification_review_required=FALSE WHERE id=%s", (app,))
    result = m.evaluate_governance_if_needed(app)
    assert result['action'] == 'evaluated'
    assert result['governance']['outcome'] == 'BUSINESS_REVIEW'
    assert rows('approval_requests')[0]['status'] == 'superseded'


def test_missing_scan_requires_security_review(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    with c() as db:
        db.execute("UPDATE applications SET data_classification='internal', ml_classification_review_required=FALSE, security_scan_passed=NULL WHERE id=%s", (app,))
    result = m.evaluate_governance_if_needed(app)
    assert result['governance']['outcome'] == 'SECURITY_REVIEW'
    assert any('Security scanning' in r for r in result['governance']['reasons'])


def test_training_gate_still_blocks_approval(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    m.evaluate_governance_if_needed(app)
    ns['get_training_gate'] = lambda *a: {'approval_ready': False, 'required_incomplete_count': 1,
                                         'blocking_assignments': [{'module_id': 'test'}]}
    ns['jsonable_encoder'] = lambda x: x
    with pytest.raises(HTTPException) as error:
        authenticated_decision(ns, rows('approval_requests')[0]['id'], types.SimpleNamespace(decision='approve', actor='test', reason='test'))
    assert error.value.status_code == 409
    assert rows('approval_requests')[0]['human_decision'] is None


def test_training_outage_prevents_routing_and_retries(scenario, monkeypatch):
    m, c, app, state, rows, ns = prepare(scenario, monkeypatch)
    def unavailable(_): raise RuntimeError('fixture')
    monkeypatch.setattr(m, 'assign_required_training', unavailable)
    first = m.evaluate_governance_if_needed(app)
    assert first['approval_automation']['status'] == 'pending'
    assert not rows('approval_requests')
    monkeypatch.setattr(m, 'assign_required_training', lambda _: {'status': 'checked'})
    result = m.evaluate_governance_if_needed(app)
    assert result['decision_id'] == first['decision_id'] and len(rows('approval_requests')) == 1



def test_authenticated_reviewer_boundary(scenario, monkeypatch):

    m, c, app, state, rows, ns = prepare(
        scenario, monkeypatch
    )

    result = m.evaluate_governance_if_needed(app)

    assert result['governance']['outcome'] == 'SECURITY_REVIEW'

    approval = rows('approval_requests')[0]

    payload = types.SimpleNamespace(
        decision='request_changes',
        actor='untrusted-client-supplied-actor',
        reason='Controlled integration test',
    )

    for credential, expected_status in (
        (None, 401),
        ('Bearer lo3-test-unprivileged', 403),
    ):

        with pytest.raises(HTTPException) as error:

            ns['record_decision'](
                approval['id'],
                payload,
                authorization=credential,
            )

        assert error.value.status_code == expected_status

        unchanged = rows('approval_requests')[0]

        assert unchanged['status'] == 'pending'
        assert unchanged['human_decision'] is None
        assert unchanged['verified_reviewer_policy'] is None

    authenticated_decision(ns, approval['id'], payload)

    saved = rows('approval_requests')[0]

    assert saved['status'] == 'changes_requested'

    assert saved['decided_by'] == (
        'vault:00000000-0000-4000-8000-000000000031'
    )

    assert saved['verified_reviewer_policy'] == (
        'lcnc-security-reviewer'
    )



def prepare_lo3_risk_scenario(connect, app, state, score, level):

    state['risk'] = {
        'score': score,
        'level': level,
        'model_version': 'test-risk',
        'factors': [],
    }

    with connect() as db:

        assert db.execute(
            'SELECT current_database() AS name'
        ).fetchone()['name'].startswith('lcnc_lo1_test_')

        db.execute(
            '''
            UPDATE applications
            SET data_classification='internal',
                ml_classification_status='assessed',
                ml_classification_review_required=FALSE,
                ml_anomaly_status='assessed',
                ml_anomalous=FALSE,
                security_scan_status='scanned',
                security_scan_passed=TRUE,
                risk_status='stale'
            WHERE id=%s
            ''',
            (app,),
        )

        db.execute(
            '''
            UPDATE discovery_observations
            SET payload=jsonb_set(
                payload,
                '{collection_complete}',
                'true'::jsonb
            )
            WHERE application_id=%s
              AND source='appsmith'
            ''',
            (app,),
        )


def test_lo3_automatic_low_risk_approval(scenario, monkeypatch):

    m, c, app, state, rows, ns = prepare(
        scenario, monkeypatch
    )

    prepare_lo3_risk_scenario(c, app, state, 0, 'low')

    result = m.evaluate_governance_if_needed(app)

    assert result['governance']['outcome'] == 'AUTO_APPROVE'
    assert result['governance']['status'] == 'completed'
    assert result['approval_automation']['status'] == 'routed'

    approval = rows('approval_requests')[0]

    assert approval['governance_outcome'] == 'AUTO_APPROVE'
    assert approval['route_type'] == 'human_confirmation'
    assert approval['required_role'] == 'Business Application Owner'

    again = m.evaluate_governance_if_needed(app)

    assert again['decision_id'] == result['decision_id']
    assert len(rows('governance_decisions')) == 1
    assert len(rows('approval_requests')) == 1


def test_lo3_high_risk_sla_escalation(scenario, monkeypatch):

    m, c, app, state, rows, ns = prepare(
        scenario, monkeypatch
    )

    prepare_lo3_risk_scenario(c, app, state, 60, 'high')

    result = m.evaluate_governance_if_needed(app)

    assert result['governance']['outcome'] == 'SECURITY_REVIEW'
    assert result['governance']['status'] == 'pending_review'
    assert 'High risk' in ' '.join(
        result['governance']['reasons']
    )

    approval = rows('approval_requests')[0]

    assert approval['required_role'] == 'Security/GRC Reviewer'
    assert approval['route_type'] == 'security_review'
    assert approval['status'] == 'pending'
    assert approval['escalation_level'] == 0

    sla_seconds = (
        approval['due_at'] - approval['created_at']
    ).total_seconds()

    assert abs(sla_seconds - 8 * 3600) < 10

    ns['escalate_overdue']()

    assert rows('approval_requests')[0]['status'] == 'pending'

    # Simulate SLA expiry exclusively in the isolated test DB.
    with c() as db:

        db.execute(
            '''
            UPDATE approval_requests
            SET due_at=created_at
            WHERE id=%s
            ''',
            (approval['id'],),
        )

    with approval_runtime(c) as restricted_connection:

        ns['get_connection'] = restricted_connection

        ns['escalate_overdue']()
        ns['escalate_overdue']()

        escalated = rows('approval_requests')[0]

        assert escalated['status'] == 'escalated'
        assert escalated['required_role'] == (
            'Senior Security/GRC Reviewer'
        )
        assert escalated['escalation_level'] == 1
        assert escalated['escalated_at'] is not None

        payload = types.SimpleNamespace(
            decision='request_changes',
            actor='untrusted-client-actor',
            reason='High-risk application requires remediation',
        )

        # Ordinary reviewers must not decide senior requests.
        with pytest.raises(HTTPException) as error:

            ns['record_decision'](
                approval['id'],
                payload,
                authorization='Bearer lo3-test-reviewer',
            )

        assert error.value.status_code == 403

        unchanged = rows('approval_requests')[0]

        assert unchanged['status'] == 'escalated'
        assert unchanged['human_decision'] is None

        ns['record_decision'](
            approval['id'],
            payload,
            authorization='Bearer lo3-test-senior-reviewer',
        )

        saved = rows('approval_requests')[0]

        assert saved['status'] == 'changes_requested'
        assert saved['verified_reviewer_policy'] == (
            'lcnc-senior-security-reviewer'
        )

    with c() as db:

        events = db.execute(
            '''
            SELECT event_type, details
            FROM approval_events
            WHERE approval_request_id=%s
              AND event_type='approval_escalated'
            ''',
            (approval['id'],),
        ).fetchall()

    assert len(events) == 1

    assert events[0]['details']['previous_role'] == (
        'Security/GRC Reviewer'
    )

    assert events[0]['details']['escalated_role'] == (
        'Senior Security/GRC Reviewer'
    )



def test_lo3_executive_summary(scenario, monkeypatch):

    m, c, app, state, rows, ns = prepare(
        scenario, monkeypatch
    )

    prepare_lo3_risk_scenario(c, app, state, 60, 'high')

    def summary():

        with approval_runtime(c) as restricted_connection:
            original = ns['get_connection']
            ns['get_connection'] = restricted_connection

            try:
                return ns['executive_summary']()
            finally:
                ns['get_connection'] = original

    before = summary()

    m.evaluate_governance_if_needed(app)

    assessed = summary()

    assert assessed['inventory_total'] == before['inventory_total']

    assert assessed['risk_status'].get('assessed', 0) == (
        before['risk_status'].get('assessed', 0) + 1
    )

    assert assessed['risk_levels'].get('high', 0) == (
        before['risk_levels'].get('high', 0) + 1
    )

    assert assessed['approval_total'] == before['approval_total'] + 1

    assert assessed['approval_status'].get('pending', 0) == (
        before['approval_status'].get('pending', 0) + 1
    )

    assert sum(assessed['risk_status'].values()) == (
        assessed['inventory_total']
    )

    assert sum(assessed['risk_levels'].values()) == (
        assessed['risk_status']['assessed']
    )

    assert sum(assessed['governance_status'].values()) == (
        assessed['inventory_total']
    )

    assert sum(assessed['governance_outcomes'].values()) == (
        assessed['inventory_total']
    )

    assert sum(assessed['approval_status'].values()) == (
        assessed['approval_total']
    )

    approval = rows('approval_requests')[0]

    with c() as db:

        db.execute(
            """
            UPDATE approval_requests
            SET due_at=created_at
            WHERE id=%s
            """,
            (approval['id'],),
        )

    overdue = summary()

    assert overdue['pending_overdue'] >= 1

    ns['escalate_overdue']()

    escalated = summary()

    assert escalated['approval_total'] == assessed['approval_total']

    assert escalated['approval_status'].get('escalated', 0) >= (
        assessed['approval_status'].get('escalated', 0) + 1
    )

    assert rows('approval_requests')[0]['status'] == 'escalated'

    with c() as db:

        db.execute(
            """
            UPDATE applications
            SET risk_status='stale',
                governance_status='stale'
            WHERE id=%s
            """,
            (app,),
        )

    stale = summary()

    # Historical high score must not remain in assessed risk totals.

    assert stale['risk_levels'].get('high', 0) == (
        assessed['risk_levels'].get('high', 0) - 1
    )

    assert stale['risk_status'].get('stale', 0) == (
        assessed['risk_status'].get('stale', 0) + 1
    )

    assert stale['governance_status'].get('stale', 0) == (
        assessed['governance_status'].get('stale', 0) + 1
    )

    assert stale['governance_outcomes'].get('not_current', 0) == (
        assessed['governance_outcomes'].get('not_current', 0) + 1
    )

    assert stale['approval_total'] == assessed['approval_total']
