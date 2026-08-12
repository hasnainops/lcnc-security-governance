import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parents[1]

DATASET_PATH = (
    BASE_DIR
    / "synthetic_classification_dataset.csv"
)

MODEL_PATH = (
    PROJECT_DIR
    / "models"
    / "classification_v1.joblib"
)

METRICS_PATH = (
    PROJECT_DIR
    / "models"
    / "classification_v1_metrics.json"
)

MODEL_VERSION = "classification-v1"
RANDOM_STATE = 42


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
    data = pd.read_csv(DATASET_PATH)

    data["combined_text"] = data.apply(
        combine_text,
        axis=1,
    )

    train, test = train_test_split(
        data,
        test_size=0.25,
        random_state=RANDOM_STATE,
        stratify=data["expected_classification"],
    )

    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    lowercase=True,
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )

    pipeline.fit(
        train["combined_text"],
        train["expected_classification"],
    )

    predictions = pipeline.predict(
        test["combined_text"]
    )

    labels = [
        "public",
        "internal",
        "confidential",
        "restricted",
    ]

    accuracy = accuracy_score(
        test["expected_classification"],
        predictions,
    )

    macro_f1 = f1_score(
        test["expected_classification"],
        predictions,
        average="macro",
    )

    matrix = confusion_matrix(
        test["expected_classification"],
        predictions,
        labels=labels,
    ).tolist()

    report = classification_report(
        test["expected_classification"],
        predictions,
        labels=labels,
        output_dict=True,
        zero_division=0,
    )

    metrics = {
        "model_version": MODEL_VERSION,
        "algorithm": (
            "TF-IDF + LogisticRegression"
        ),
        "training_rows": int(len(train)),
        "test_rows": int(len(test)),
        "classes": labels,
        "accuracy": round(
            float(accuracy),
            4,
        ),
        "macro_f1": round(
            float(macro_f1),
            4,
        ),
        "confusion_matrix": matrix,
        "classification_report": report,
        "synthetic_training_data": True,
        "production_accuracy_claim": False,
        "authority": "advisory",
    }

    MODEL_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        {
            "pipeline": pipeline,
            "model_version": MODEL_VERSION,
            "classes": labels,
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
