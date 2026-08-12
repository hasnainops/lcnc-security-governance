import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parents[1]

MODEL_PATH = (
    PROJECT_DIR
    / "models"
    / "classification_v1.joblib"
)

DATA_PATH = (
    BASE_DIR
    / "classification_challenge_set.csv"
)

METRICS_PATH = (
    PROJECT_DIR
    / "models"
    / "classification_v1_challenge_metrics.json"
)

LABELS = [
    "public",
    "internal",
    "confidential",
    "restricted",
]


def combine_text(row):
    return " ".join(
        [
            str(row["application_name"]),
            str(row["business_purpose"]),
            str(row["data_fields"]),
            str(row["connector_metadata"]),
        ]
    )


def main():
    artifact = joblib.load(MODEL_PATH)
    pipeline = artifact["pipeline"]

    data = pd.read_csv(DATA_PATH)

    data["combined_text"] = data.apply(
        combine_text,
        axis=1,
    )

    predictions = pipeline.predict(
        data["combined_text"]
    )

    probabilities = pipeline.predict_proba(
        data["combined_text"]
    )

    confidence = probabilities.max(axis=1)

    data["predicted"] = predictions
    data["confidence"] = confidence.round(4)
    data["correct"] = (
        data["expected_classification"]
        == data["predicted"]
    )

    accuracy = accuracy_score(
        data["expected_classification"],
        predictions,
    )

    macro_f1 = f1_score(
        data["expected_classification"],
        predictions,
        average="macro",
    )

    matrix = confusion_matrix(
        data["expected_classification"],
        predictions,
        labels=LABELS,
    ).tolist()

    report = classification_report(
        data["expected_classification"],
        predictions,
        labels=LABELS,
        output_dict=True,
        zero_division=0,
    )

    metrics = {
        "model_version": artifact["model_version"],
        "evaluation_type": "independent_synthetic_challenge_set",
        "rows": int(len(data)),
        "accuracy": round(float(accuracy), 4),
        "macro_f1": round(float(macro_f1), 4),
        "confusion_matrix": matrix,
        "classification_report": report,
        "synthetic_evaluation_data": True,
        "production_accuracy_claim": False,
    }

    METRICS_PATH.write_text(
        json.dumps(metrics, indent=2) + "\n"
    )

    print(json.dumps(metrics, indent=2))

    print()
    print("Per-application results")
    print("-----------------------")

    print(
        data[
            [
                "application_name",
                "expected_classification",
                "predicted",
                "confidence",
                "correct",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
