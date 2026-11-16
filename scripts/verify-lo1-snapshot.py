"""Read-only live checkpoint; never calls an assessment or writes inventory."""
import argparse
import json
from urllib.request import build_opener, ProxyHandler
from uuid import UUID

parser = argparse.ArgumentParser()
parser.add_argument('--application-id', type=UUID, required=True)
args = parser.parse_args()
client = build_opener(ProxyHandler({}))
def get(path):
    with client.open('http://127.0.0.1:8000' + path, timeout=15) as response:
        return json.load(response)

app = get('/applications/' + str(args.application_id))
history = get('/applications/' + str(args.application_id) + '/history')
records = [x for x in history.get('ml_assessments', [])
           if x.get('analysis_type') == 'configuration-snapshot']
print(json.dumps({'scope': 'Configuration snapshot checkpoint; not full LO1 acceptance',
    'application': {k: app.get(k) for k in ('id','last_seen_at','registration_status',
        'ml_anomaly_status','ml_model_version','ml_anomalous','shadow_it_candidate',
        'connector_count','external_integration_count','unapproved_integration_count',
        'external_domain_count','changes_last_24h','discovery_feature_evidence')},
    'snapshot_history_count': len(records),
    'recent_snapshots': records[:2]}, indent=2))
