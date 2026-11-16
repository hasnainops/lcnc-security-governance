import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lo1_classifier_test", ROOT / "app/classifier.py")
classifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(classifier)


def test_artifact_identity_matches_the_bytes_loaded():
    assert classifier.classification_model_sha256 == hashlib.sha256(classifier.MODEL_PATH.read_bytes()).hexdigest()


@pytest.mark.parametrize("label,confidence,required", [
    ("public", .9, False), ("internal", .9, False), ("internal", .5, True),
    ("confidential", .9, True), ("restricted", .9, True),
])
def test_advisory_human_review_contract(monkeypatch, label, confidence, required):
    class Pipeline:
        classes_ = ["public", "internal", "confidential", "restricted"]
        def predict(self, texts):
            return [label]
        def predict_proba(self, texts):
            return [[confidence if item == label else (1-confidence)/3 for item in self.classes_]]
    monkeypatch.setattr(classifier, "pipeline", Pipeline())
    result = classifier.classify_application(dict.fromkeys(
        ["application_name", "business_purpose", "data_fields", "connector_metadata"], "Test fixture"))
    assert result["review_required"] is required
    assert result["authority"] == "advisory"


def test_real_artifact_accepts_attributed_input_text():
    result = classifier.classify_application({
        "application_name": "Purchase requests",
        "business_purpose": "Manage employee purchase requests and approvals",
        "data_fields": "amount: Requested purchase amount",
        "connector_metadata": "Complete Appsmith collection observed no configured connectors or actions.",
    })
    assert result["suggested_classification"] in {"public", "internal", "confidential", "restricted"}
    assert 0 <= result["confidence"] <= 1
    assert abs(sum(result["class_probabilities"].values()) - 1) < .001
