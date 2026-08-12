import os
from pathlib import Path

import joblib


DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "classification_v1.joblib"
)

MODEL_PATH = Path(
    os.getenv(
        "CLASSIFICATION_MODEL_PATH",
        str(DEFAULT_MODEL_PATH),
    )
)

artifact = joblib.load(MODEL_PATH)

pipeline = artifact["pipeline"]
classification_model_version = artifact["model_version"]

REVIEW_THRESHOLD = 0.60


def classify_application(payload):
    combined_text = " ".join(
        [
            payload["application_name"],
            payload["business_purpose"],
            payload["data_fields"],
            payload["connector_metadata"],
        ]
    )

    prediction = pipeline.predict(
        [combined_text]
    )[0]

    probabilities = pipeline.predict_proba(
        [combined_text]
    )[0]

    classes = pipeline.classes_

    class_probabilities = {
        label: round(float(probability), 4)
        for label, probability in zip(
            classes,
            probabilities,
        )
    }

    confidence = float(
        max(probabilities)
    )

    return {
        "suggested_classification": prediction,
        "confidence": round(confidence, 4),
        "review_required": (
            confidence < REVIEW_THRESHOLD
        ),
        "review_threshold": REVIEW_THRESHOLD,
        "model_version": (
            classification_model_version
        ),
        "class_probabilities": (
            class_probabilities
        ),
        "authority": "advisory",
    }
