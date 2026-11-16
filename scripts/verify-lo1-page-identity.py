#!/usr/bin/env python3
"""Match an Appsmith editor page to persisted observations, without data writes.

The lookup uses the existing local PostgreSQL operator through Docker Compose.
Only application IDs, names, times, observation totals and classification status
are returned. A dated evidence file is saved beside the supplied baseline.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from urllib.request import ProxyHandler, build_opener
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]


def identity_query(page_id):
    if not re.fullmatch(r"[0-9a-f]{24}", page_id):
        raise ValueError("Expected a 24-character Appsmith page ID")
    # page_id has been restricted to literal hexadecimal, never SQL syntax.
    return """BEGIN READ ONLY;
WITH matched AS (
    SELECT application_id, MIN(observed_at) AS first_page_observed_at,
           MAX(observed_at) AS latest_page_observed_at, COUNT(*) AS observation_count
    FROM public.discovery_observations
    WHERE source='appsmith' AND payload->'page_ids' ? '""" + page_id + """'
    GROUP BY application_id
), records AS (
    SELECT a.id, a.external_id, a.platform, a.name, a.registration_status,
           a.first_discovered_at, a.last_seen_at, a.shadow_it_candidate,
           a.ml_anomaly_status, a.risk_status, a.risk_score, a.risk_level,
           m.first_page_observed_at, m.latest_page_observed_at, m.observation_count
    FROM matched m JOIN public.applications a ON a.id=m.application_id
    WHERE a.platform='appsmith'
)
SELECT COALESCE(jsonb_agg(to_jsonb(records)), '[]'::jsonb) FROM records;
COMMIT;
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-id", required=True)
    parser.add_argument("--baseline", required=True, type=Path)
    args = parser.parse_args()
    baseline_path = args.baseline.expanduser().resolve()
    baseline = json.loads(baseline_path.read_text())
    query = identity_query(args.page_id)
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "sh", "-eu", "-c",
         'exec psql -X -q -A -t -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],
        cwd=ROOT, input=query, capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Read-only database lookup failed; raw details withheld")
    matches = json.loads(result.stdout)
    if not isinstance(matches, list) or len(matches) != 1:
        raise RuntimeError("Page identity lookup requires exactly one matching application")
    application = matches[0]
    app_id = str(UUID(application["id"]))
    previous_ids = {app["id"] for app in baseline["inventory"]}
    previous_sources = {(app["platform"], app["external_id"]) for app in baseline["inventory"]}
    client = build_opener(ProxyHandler({}))
    with client.open("http://127.0.0.1:8000/applications/" + app_id + "/classification-state", timeout=15) as response:
        state = json.load(response)
    captured = datetime.now(timezone.utc)
    report = {
        "scope": "Page-to-inventory identity verification; not full LO1 acceptance",
        "checked_at": captured.isoformat(), "page_id": args.page_id,
        "baseline_at": (baseline.get("baseline_at") or baseline.get("retrieved_at")),
        "already_in_baseline": app_id in previous_ids,
        "source_already_in_baseline": (application["platform"], application["external_id"]) in previous_sources,
        "application": application,
        "classification": {key: state.get(key) for key in (
            "ml_classification_status", "pending_reasons", "suggested_classification",
            "review_required", "authoritative_classification")},
    }
    evidence = baseline_path.parent / ("page-identity-" + captured.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with evidence.open("x") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(json.dumps(report, indent=2))
    print("PASS: editor page matched to persisted Appsmith observations.")
    if report["already_in_baseline"] or report["source_already_in_baseline"]:
        print("This app was already in the baseline; retain it for the workflow test.")
    print("Evidence saved:", evidence)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("STOP:", str(exc) if type(exc) is RuntimeError else type(exc).__name__)
        raise SystemExit(1)
