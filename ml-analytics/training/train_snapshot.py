"""Train a separate current-configuration model; no historical input/imputation.

Evaluation uses the existing synthetic dataset and labels, not production claims.
"""
import hashlib
import json
from pathlib import Path
import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score, confusion_matrix

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ['external_integration_count', 'unapproved_integration_count',
            'connector_count', 'external_domain_count']


def train():
    dataset = ROOT / 'training/synthetic_lcnc_applications.csv'
    data = pd.read_csv(dataset)
    training, test = train_test_split(data, test_size=0.3, random_state=42,
                                    stratify=data.expected_anomaly)
    model = IsolationForest(n_estimators=200, contamination=0.01, random_state=42)
    model.fit(training.loc[training.expected_anomaly == 0, FEATURES])
    prediction = (model.predict(test[FEATURES]) == -1).astype(int)
    metrics = {'model_version': 'configuration-snapshot-v1', 'features': FEATURES,
               'dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
               'training_rows': int((training.expected_anomaly == 0).sum()),
               'test_rows': len(test), 'random_state': 42,
               'precision': float(precision_score(test.expected_anomaly, prediction, zero_division=0)),
               'recall': float(recall_score(test.expected_anomaly, prediction, zero_division=0)),
               'confusion_matrix': confusion_matrix(test.expected_anomaly, prediction).tolist(),
               'synthetic_training_data': True, 'production_accuracy_claim': False,
               'limitations': ['No temporal-change detection', 'No owner or exposure features',
                               'Labels inherited from the original synthetic dataset']}
    output = ROOT / 'models'; output.mkdir(exist_ok=True)
    joblib.dump({'model': model, 'features': FEATURES,
                 'model_version': metrics['model_version']}, output / 'configuration_snapshot_v1.joblib')
    (output / 'configuration_snapshot_v1_metrics.json').write_text(json.dumps(metrics, indent=2)+'\n')
    print(json.dumps(metrics, indent=2))

if __name__ == '__main__':
    train()
