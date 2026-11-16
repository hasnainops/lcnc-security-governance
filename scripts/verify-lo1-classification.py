#!/usr/bin/env python3
"""Read-only, sanitized LO1 checkpoint. No assessment, approval or data writes."""
import argparse
from datetime import datetime, timezone
import json
from urllib.request import ProxyHandler, build_opener
from uuid import UUID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application-id", type=UUID)
    args = parser.parse_args()
    client = build_opener(ProxyHandler({}))
    def read(path):
        with client.open("http://127.0.0.1:8000" + path, timeout=15) as response:
            return json.load(response)
    inventory = read("/applications")
    if not isinstance(inventory, list):
        raise ValueError("Invalid inventory response")
    report = {"scope": "LO1 runtime checkpoint; not an acceptance verdict",
              "retrieved_at": datetime.now(timezone.utc).isoformat(),
              "inventory": [{key: app.get(key) for key in ("id", "external_id", "name", "platform", "registration_status")}
                            for app in inventory]}
    if args.application_id:
        app_id = str(args.application_id)
        application = next(app for app in inventory if app["id"] == app_id)
        state = read(f"/applications/{app_id}/classification-state")
        history = read(f"/applications/{app_id}/history")
        report["application"] = {key: application.get(key) for key in (
            "id", "external_id", "first_discovered_at", "last_seen_at", "registration_status",
            "shadow_it_candidate", "risk_status", "risk_score", "risk_level", "ml_anomaly_status")}
        # Subject identifiers, raw classifier inputs, emails and credential data
        # are deliberately excluded from the portable evidence summary.
        report["classification"] = {key: state.get(key) for key in (
            "ml_classification_status", "suggested_classification", "confidence", "review_required",
            "model_version", "classified_at", "authoritative_classification", "pending_reasons")}
        provenance = state.get("provenance") or {}
        report["classification_revalidation"] = {
            key: provenance.get(key) for key in (
                "reused_assessment_id", "inference_observation_id", "revalidated_at",
                "observation_id", "observed_at",
            )
        }
        report["classification_history_count"] = len(history["classification_assessments"])
        report["recent_assessments"] = [{
            **{key: record.get(key) for key in ("id", "input_sha256", "classified_at", "suggested_classification", "authority")},
            "evidence": {key: (record.get("source_evidence") or {}).get(key) for key in (
                "owner_context_id", "owner_declared_at", "observation_id", "observed_at",
                "collector_version", "model_sha256", "review_reasons")},
        } for record in history["classification_assessments"][:5]]
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("STOP: read-only verification failed; exception type=" + type(exc).__name__)
        raise SystemExit(1)
