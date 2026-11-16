"""Advisory configuration anomaly detection, independent of temporal history."""
import hashlib
from pathlib import Path
import joblib
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated

Count = Annotated[int, Field(strict=True, ge=0)]
class SnapshotFeatures(BaseModel):
    model_config = ConfigDict(extra='forbid')
    external_integration_count: Count
    unapproved_integration_count: Count
    connector_count: Count
    external_domain_count: Count

PATH = Path(__file__).resolve().parents[1] / 'models/configuration_snapshot_v1.joblib'
artifact = joblib.load(PATH)
MODEL_SHA256 = hashlib.sha256(PATH.read_bytes()).hexdigest()
MODEL_VERSION = artifact['model_version']


def analyze_snapshot(payload):
    frame = pd.DataFrame([payload], columns=artifact['features'])
    model = artifact['model']
    return {'analysis_type': 'configuration-snapshot', 'authority': 'advisory',
            'anomalous': bool(model.predict(frame)[0] == -1),
            'raw_decision_score': round(float(model.decision_function(frame)[0]), 6),
            'model_version': MODEL_VERSION, 'model_sha256': MODEL_SHA256,
            'features_evaluated': artifact['features'],
            'context_signals': ['Configuration-only assessment; temporal changes are not evaluated.']}
