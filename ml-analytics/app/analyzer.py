import os
from pathlib import Path

import joblib
import pandas as pd


DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "isolation_forest_v1.joblib"
)

MODEL_PATH = Path(
    os.getenv(
        "ML_MODEL_PATH",
        str(DEFAULT_MODEL_PATH),
    )
)

artifact = joblib.load(MODEL_PATH)

model = artifact["model"]
features = artifact["features"]
model_version = artifact["model_version"]


def build_context_signals(payload):
    signals = []

    if payload["owner_known"] == 0:
        signals.append("accountable owner is not known")

    if payload["business_purpose_known"] == 0:
        signals.append("business purpose is not documented")

    if payload["internet_exposed"] == 1:
        signals.append("application is internet exposed")

    if payload["unapproved_integration_count"] > 0:
        signals.append(
            "one or more external integrations are unapproved"
        )

    if payload["uses_api_key"] == 1:
        signals.append("API-key credential usage detected")

    if payload["external_domain_count"] >= 2:
        signals.append(
            "multiple external destination domains detected"
        )

    if payload["changes_last_24h"] >= 3:
        signals.append(
            "elevated application change activity detected"
        )

    return signals


def analyze_application(payload):
    row = {
        feature: payload[feature]
        for feature in features
    }

    frame = pd.DataFrame(
        [row],
        columns=features,
    )

    prediction = int(
        model.predict(frame)[0]
    )

    decision_score = float(
        model.decision_function(frame)[0]
    )

    return {
        "anomalous": prediction == -1,
        "raw_decision_score": round(
            decision_score,
            6,
        ),
        "model_version": model_version,
        "features_evaluated": features,
        "context_signals": build_context_signals(
            payload
        ),
    }
