import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

DATASET_PATH = BASE_DIR / "synthetic_lcnc_applications.csv"

MODEL_PATH = (
    PROJECT_DIR
    / "models"
    / "isolation_forest_v1.joblib"
)

METRICS_PATH = (
    PROJECT_DIR
    / "models"
    / "isolation_forest_v1_metrics.json"
)

MODEL_VERSION = "isolation-forest-v1"
CONTAMINATION = 0.01
RANDOM_STATE = 42


FEATURES = [
    "owner_known",
    "business_purpose_known",
    "internet_exposed",
    "external_integration_count",
    "unapproved_integration_count",
    "uses_api_key",
    "connector_count",
    "external_domain_count",
    "changes_last_24h",
]


def main():
    data = pd.read_csv(DATASET_PATH)

    normal = data[
        data["expected_anomaly"] == 0
    ]

    anomaly = data[
        data["expected_anomaly"] == 1
    ]

    normal_train, normal_temp = train_test_split(
        normal,
        test_size=0.30,
        random_state=RANDOM_STATE,
    )

    normal_validation, normal_test = train_test_split(
        normal_temp,
        test_size=0.50,
        random_state=RANDOM_STATE,
    )

    _, anomaly_test = train_test_split(
        anomaly,
        test_size=0.50,
        random_state=RANDOM_STATE,
    )

    final_training = pd.concat(
        [
            normal_train,
            normal_validation,
        ],
        ignore_index=True,
    )

    test = pd.concat(
        [
            normal_test,
            anomaly_test,
        ],
        ignore_index=True,
    )

    model = IsolationForest(
        n_estimators=200,
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
    )

    model.fit(
        final_training[FEATURES]
    )

    predictions = model.predict(
        test[FEATURES]
    )

    predicted_anomaly = (
        predictions == -1
    ).astype(int)

    expected = test["expected_anomaly"]

    precision = precision_score(
        expected,
        predicted_anomaly,
        zero_division=0,
    )

    recall = recall_score(
        expected,
        predicted_anomaly,
        zero_division=0,
    )

    f1 = f1_score(
        expected,
        predicted_anomaly,
        zero_division=0,
    )

    accuracy = accuracy_score(
        expected,
        predicted_anomaly,
    )

    matrix = confusion_matrix(
        expected,
        predicted_anomaly,
    ).tolist()

    false_positives = (
        (predicted_anomaly == 1)
        & (expected.to_numpy() == 0)
    ).sum()

    normal_test_count = (
        expected == 0
    ).sum()

    false_positive_rate = (
        false_positives
        / normal_test_count
    )

    metrics = {
        "model_version": MODEL_VERSION,
        "algorithm": "IsolationForest",
        "n_estimators": 200,
        "contamination": CONTAMINATION,
        "random_state": RANDOM_STATE,
        "training_rows": int(
            len(final_training)
        ),
        "test_rows": int(
            len(test)
        ),
        "normal_test_rows": int(
            (expected == 0).sum()
        ),
        "anomaly_test_rows": int(
            (expected == 1).sum()
        ),
        "features": FEATURES,
        "precision": round(
            float(precision),
            4,
        ),
        "recall": round(
            float(recall),
            4,
        ),
        "f1": round(
            float(f1),
            4,
        ),
        "accuracy": round(
            float(accuracy),
            4,
        ),
        "false_positive_rate": round(
            float(false_positive_rate),
            4,
        ),
        "confusion_matrix": matrix,
        "synthetic_training_data": True,
        "production_accuracy_claim": False,
    }

    MODEL_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "model_version": MODEL_VERSION,
            "contamination": CONTAMINATION,
        },
        MODEL_PATH,
    )

    METRICS_PATH.write_text(
        json.dumps(
            metrics,
            indent=2,
        )
        + "\n"
    )

    print(
        json.dumps(
            metrics,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
