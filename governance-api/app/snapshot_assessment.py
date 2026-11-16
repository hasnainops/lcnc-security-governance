"""Automatic current-configuration inference without a fabricated history feature."""
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from .database import get_connection
from .discovery_observation import AppsmithObservation
from .feature_assembly import FEATURE_NAMES
from .destination_policy import assemble_governed_features
from .feature_persistence import persist_current_features
from .ml import ML_ANALYTICS_URL

NAMES = FEATURE_NAMES[:-1]


def _request(method, path, **kwargs):
    response = method(ML_ANALYTICS_URL + path, timeout=10, **kwargs)
    response.raise_for_status()
    return response.json()


def assess_snapshot_if_needed(application_id):
    with get_connection() as connection:
        # Serialize source writes and concurrent API replicas while evaluating.
        app = connection.execute('SELECT * FROM applications WHERE id=%s FOR UPDATE',
                                 (application_id,)).fetchone()
        if app is None:
            raise HTTPException(404, 'Application not found')
        if app['changes_last_24h'] is not None:
            return {'action': 'full_history_available'}
        source = connection.execute('''SELECT * FROM discovery_observations
            WHERE application_id=%s AND source='appsmith'
            ORDER BY observed_at DESC, received_at DESC LIMIT 1''', (application_id,)).fetchone()
        now = datetime.now(timezone.utc)
        if source is None or not now-timedelta(minutes=3) <= source['observed_at'] <= now:
            return {'action': 'pending', 'reason': 'fresh_observation_required'}
        observation = AppsmithObservation.model_validate(source['payload'])
        assembled = assemble_governed_features(observation, source['id'],
            cached_evidence=app.get('discovery_feature_evidence'))
        values, feature_evidence = assembled['features'], assembled['evidence']
        persistence = persist_current_features(application_id, source['id'], values,
            evidence=feature_evidence, connection=connection)
        if persistence['action'] != 'persisted':
            return {'action': 'pending', 'reason': persistence['action']}
        if persistence['changed']:
            app['ml_anomaly_status'] = 'stale'
        if any(values[name] is None for name in NAMES):
            return {'action': 'pending', 'reason': 'complete_configuration_features_required',
                    'missing_features': [name for name in NAMES if values[name] is None],
                    'pending_reasons': feature_evidence['pending_reasons']}
        try:
            identity = _request(httpx.get, '/snapshot-model')
            if (not isinstance(identity.get('model_version'), str)
                or not isinstance(identity.get('model_sha256'), str)
                or len(identity['model_sha256']) != 64):
                raise ValueError('Invalid model identity')
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return {'action': 'pending', 'reason': 'snapshot_model_unavailable'}
        payload = {name: values[name] for name in NAMES}
        digest = hashlib.sha256(json.dumps({'features': payload, 'model': identity,
                                          'feature_evidence_sha256': feature_evidence['semantic_sha256']},
                                         sort_keys=True).encode()).hexdigest()
        previous = connection.execute('''SELECT * FROM ml_assessments
            WHERE application_id=%s AND analysis_type='configuration-snapshot'
            ORDER BY assessed_at DESC, id DESC LIMIT 1''', (application_id,)).fetchone()
        prior = None
        if previous and isinstance(previous['context_signals'], list):
            prior = next((x.get('snapshot_evidence') for x in previous['context_signals']
                          if isinstance(x, dict) and 'snapshot_evidence' in x), None)
        if (isinstance(prior, dict) and prior.get('input_sha256') == digest
            and previous['features'] == payload and app['ml_anomaly_status'] == 'assessed'
            and app['ml_model_version'] == identity['model_version']):
            return {'action': 'unchanged', 'assessment_id': str(previous['id']),
                    'assessment_scope': 'current_configuration'}
        try:
            result = _request(httpx.post, '/analyze-snapshot', json=payload)
            if (result.get('analysis_type') != 'configuration-snapshot'
                or result.get('authority') != 'advisory'
                or result.get('model_version') != identity['model_version']
                or result.get('model_sha256') != identity['model_sha256']
                or result.get('features_evaluated') != list(NAMES)
                or type(result.get('anomalous')) is not bool
                or type(result.get('raw_decision_score')) not in (float, int)
                or not math.isfinite(result['raw_decision_score'])):
                raise ValueError('Invalid snapshot inference')
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return {'action': 'pending', 'reason': 'snapshot_inference_unavailable'}
        # HTTP latency must not make an old snapshot current.
        if datetime.now(timezone.utc)-source['observed_at'] > timedelta(minutes=3):
            return {'action': 'pending', 'reason': 'fresh_observation_required'}
        assessment_id = uuid4()
        evidence = {'input_sha256': digest, 'model_sha256': identity['model_sha256'],
                    'source_observation_id': str(source['id']),
                    'observed_at': source['observed_at'].isoformat(),
                    'assessment_scope': 'current_configuration', 'temporal_history_evaluated': False,
                    'destination_policy': feature_evidence}
        connection.execute('''INSERT INTO ml_assessments
            (id,application_id,analysis_type,anomalous,decision_score,model_version,features,context_signals)
            VALUES (%s,%s,'configuration-snapshot',%s,%s,%s,%s,%s)''',
            (assessment_id, application_id, result['anomalous'], result['raw_decision_score'],
             result['model_version'], Jsonb(payload), Jsonb([{'snapshot_evidence': evidence}])))
        connection.execute('''UPDATE applications SET ml_anomaly_status='assessed',
            ml_anomalous=%s, ml_decision_score=%s, ml_model_version=%s, ml_assessed_at=NOW(),
            shadow_it_candidate=CASE WHEN LOWER(platform)='appsmith' THEN
                (%s AND registration_status='unregistered') ELSE shadow_it_candidate END,
            risk_status='stale', risk_score=NULL, risk_level=NULL, risk_model_version=NULL,
            risk_assessed_at=NULL, governance_status='stale', governance_outcome=NULL,
            governance_decided_at=NULL, updated_at=NOW() WHERE id=%s''',
            (result['anomalous'], result['raw_decision_score'], result['model_version'],
             result['anomalous'], application_id))
        return {'action': 'assessed', 'assessment_id': str(assessment_id), **evidence}
