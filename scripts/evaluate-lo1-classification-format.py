#!/usr/bin/env python3
"""Compare attribution formatting on the existing synthetic challenge dataset.

This is a compatibility diagnostic, not a production accuracy evaluation. It
does not create inventory, change training data, retrain, or overwrite metrics.
"""
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "governance-api"))
from app.classification_inputs import build_classification_inputs

spec = importlib.util.spec_from_file_location("lo1_format_classifier", ROOT / "ml-analytics/app/classifier.py")
classifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(classifier)
dataset = ROOT / "ml-analytics/training/classification/classification_challenge_set.csv"
rows = list(csv.DictReader(dataset.open()))
results = []
for row in rows:
    original = {key: row[key] for key in ("application_name", "business_purpose", "data_fields", "connector_metadata")}
    # Explicit synthetic declarations and sanitized action observations. These
    # fixtures never enter inventory and never masquerade as live evidence.
    app_id, context_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    names = original["data_fields"].split()
    application = {"id": app_id, "external_id": "format-fixture", "name": original["application_name"],
                   "platform": "appsmith", "owner_context_id": context_id}
    context = {"id": context_id, "application_id": app_id, "subject_id": "synthetic-fixture",
               "declared_at": now, "payload": {"business_purpose": original["business_purpose"],
               "field_scope": "declared_schema", "attested": True,
               "data_fields": [{"name": name, "description": name.replace("_", " ")} for name in names]}}
    observation = {"id": uuid4(), "application_id": app_id, "observed_at": now, "payload": {
        "contract_version": "appsmith-observation-v1", "source": "appsmith", "external_id": "format-fixture",
        "collector_version": "synthetic-fixture", "observed_at": now.isoformat(),
        "collection_complete": False, "pending_reasons": ["connector_identity_unresolved"],
        "connectors": [], "observed_actions": [{"action_id": "fixture-action", "destination_state": "observed",
                                                 "destination": {"scheme": "https", "host": "fixture.example.test"}}],
        "page_ids": ["fixture-page"], "data_field_evidence": {
            "scope": "appsmith_widget_dsl", "coverage": "partial", "field_identifiers": names,
            "pages_expected": 1, "pages_inspected": 1, "widgets_inspected": len(names), "dynamic_bindings_detected": 0}}}
    built = build_classification_inputs(application, context, observation, now)
    old, new = classifier.classify_application(original), classifier.classify_application(built.payload)
    results.append({"expected": row["expected_classification"], "before": old["suggested_classification"],
                    "after": new["suggested_classification"], "confidence": new["confidence"],
                    "model_review_required": new["review_required"],
                    "review_required": new["review_required"] or bool(built.review_reasons)})
report = {
    "scope": "Synthetic owner-schema/action-host compatibility; not production accuracy or live Appsmith evidence",
    "model_sha256": classifier.classification_model_sha256,
    "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
    "samples": len(results),
    "original_correct": sum(item["before"] == item["expected"] for item in results),
    "attributed_correct": sum(item["after"] == item["expected"] for item in results),
    "changed_predictions": sum(item["before"] != item["after"] for item in results),
    "review_required": sum(item["review_required"] for item in results),
    "incorrect_without_model_review": sum(item["after"] != item["expected"] and not item["model_review_required"] for item in results),
    "incorrect_without_review": sum(item["after"] != item["expected"] and not item["review_required"] for item in results),
}
print(json.dumps(report, indent=2))
if report["incorrect_without_review"] or report["incorrect_without_model_review"]:
    sys.exit("Compatibility failure: an incorrect synthetic prediction escaped the review gate.")
