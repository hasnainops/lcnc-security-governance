#!/usr/bin/env python3
"""Read-only connector-policy checkpoint. Does not run inference or approve apps."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
from uuid import UUID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application-id', type=UUID, required=True)
    parser.add_argument('--allow-empty', action='store_true', help='Smoke check only; not non-empty connector proof')
    parser.add_argument('--expect-connectors', type=int)
    parser.add_argument('--expect-unapproved', type=int)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    for expected in (args.expect_connectors, args.expect_unapproved):
        if expected is not None and expected < 0:
            parser.error('Expected counts must be nonnegative')
    client = build_opener(ProxyHandler({}))
    def get(path):
        with client.open('http://127.0.0.1:8000' + path, timeout=15) as response:
            return json.load(response)
    application_id = str(args.application_id)
    app = get('/applications/' + application_id)
    history = get('/applications/' + application_id + '/history')
    now = datetime.now(timezone.utc)
    problems = []
    def require(condition, message):
        if not condition:
            problems.append(message)
    def fresh(value):
        try:
            return now - timedelta(minutes=3) <= datetime.fromisoformat(value) <= now
        except (ValueError, TypeError):
            return False
    names = ('external_integration_count', 'unapproved_integration_count',
             'connector_count', 'external_domain_count')
    evidence = app.get('discovery_feature_evidence') or {}
    require(app.get('platform') == 'appsmith', 'Expected an Appsmith application')
    require(fresh(app.get('last_seen_at')), 'Discovery has not seen this app within three minutes')
    require(evidence.get('version') == 'connector-policy-v1', 'New connector policy evidence is missing')
    require(evidence.get('fresh') is True and fresh(evidence.get('observed_at')),
            'Feature evidence is not current')
    require(all(type(app.get(k)) is int and app[k] >= 0 for k in names),
            'One or more current-configuration counts remain unknown')
    require(args.allow_empty or (type(app.get('connector_count')) is int and app['connector_count'] > 0),
            'A non-empty app with a referenced saved datasource is required')
    if args.expect_connectors is not None:
        require(app.get('connector_count') == args.expect_connectors, 'Connector count differs from the expected count')
    if args.expect_unapproved is not None:
        require(app.get('unapproved_integration_count') == args.expect_unapproved, 'Unapproved-host count differs from expected')
    require(app.get('ml_anomaly_status') == 'assessed', 'Current anomaly assessment is not assessed')
    matching = None
    for record in history.get('ml_assessments', []):
        for signal in record.get('context_signals') or []:
            if not isinstance(signal, dict):
                continue
            snapshot = signal.get('snapshot_evidence') or {}
            proof = snapshot.get('destination_policy') or signal.get('discovery_feature_evidence') or {}
            if (proof.get('semantic_sha256') == evidence.get('semantic_sha256')
                and isinstance(proof.get('semantic_sha256'), str)
                and record.get('model_version') == app.get('ml_model_version')
                and record.get('anomalous') == app.get('ml_anomalous')
                and all((record.get('features') or {}).get(k) == app.get(k) for k in names)):
                matching = record
                break
        if matching:
            break
    require(matching is not None, 'No persisted ML assessment matches the current features and policy evidence')
    result = {'scope': 'Connector policy and automatic scoring checkpoint; not full LO1 acceptance',
        'checked_at': now.isoformat(), 'application_id': application_id,
        'mode': 'empty-app smoke check permitted' if args.allow_empty else 'non-empty connector check',
        'result': 'PASS' if not problems else 'ATTENTION_REQUIRED', 'problems': problems,
        'application': {k: app.get(k) for k in ('name', 'last_seen_at', 'registration_status',
            'ml_anomaly_status', 'ml_model_version', 'ml_anomalous', 'shadow_it_candidate',
            'risk_status', 'risk_score', *names, 'changes_last_24h')},
        'feature_evidence': evidence, 'matching_assessment': matching}
    encoded = json.dumps(result, indent=2) + '\n'
    print(encoded, end='')
    if args.output:
        args.output.write_text(encoded)
        print('Evidence saved:', args.output)
    return 1 if problems else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('STOP: connector checkpoint failed; type=' + type(exc).__name__)
        raise SystemExit(1)
