#!/usr/bin/env python3
"""Update only the API replicas of an already installed Appsmith publish guard."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import shlex
import sys


spec = importlib.util.spec_from_file_location(
    "publish_guard_rollout", Path(__file__).with_name("rollout-lo2-publish-guard.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
GUARDED_COMMAND = ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
UNCHANGED = ("appsmith", "appsmith-proxy", "governance-api", "opa")


def validate_envelope(status, body):
    meta = body.get("responseMeta") if isinstance(body, dict) else None
    error = meta.get("error") if isinstance(meta, dict) else None
    if (status != 403 or not isinstance(body, dict) or body.get("allowed") is not False
            or body.get("scope") != base.VERSION or not body.get("reasons")
            or not isinstance(meta, dict) or meta.get("status") != 403
            or meta.get("success") is not False or not isinstance(error, dict)
            or error.get("code") != "LCNC-PUBLISH-DENIED"
            or not isinstance(error.get("message"), str) or not error["message"]):
        raise RuntimeError("Expected HTTP 403 with an Appsmith-compatible governance denial")


def main():
    base.run("docker", "compose", "config", "--quiet", capture=True)
    before = {s: base.runtime(s) for s in (*UNCHANGED, *base.APIS)}
    if before["appsmith-proxy"]["command"] != GUARDED_COMMAND:
        raise RuntimeError("An installed publish guard is required; no services changed")
    active_config = base.run("docker", "compose", "exec", "-T", "appsmith-proxy",
                           "cat", "/etc/caddy/Caddyfile", capture=True)
    if active_config.strip() != (base.ROOT / "appsmith/publish-guard.Caddyfile").read_text().strip():
        raise RuntimeError("Proxy configuration differs from the installed guard; no services changed")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    git_dir = Path(base.run("git", "rev-parse", "--absolute-git-dir", capture=True))
    evidence = git_dir / ("cr002-lo2-publish-response-" + stamp)
    evidence.mkdir(mode=0o700)
    (evidence / "runtime-before.json").write_text(json.dumps(before, indent=2) + "\n")
    rollback = {"services": {}}
    for service in base.APIS:
        tag = f"lcnc-lo2-response-rollback-{service}:{stamp.lower()}"
        base.run("docker", "image", "tag", before[service]["image_id"], tag)
        rollback["services"][service] = {"image": tag}
    rollback_path = evidence / "rollback.compose.json"
    rollback_path.write_text(json.dumps(rollback, indent=2) + "\n")
    restore = ["docker", "compose", "-f", str(base.ROOT / "docker-compose.yml"),
               "-f", str(rollback_path), "up", "-d", "--no-deps", "--no-build",
               "--pull", "never", "--force-recreate", "--wait", "--wait-timeout", "240", *base.APIS]
    (evidence / "rollback-command.txt").write_text(shlex.join(restore) + "\n")
    print("Rollback command (API replicas only):", shlex.join(restore), flush=True)
    changed = False
    try:
        base.run("docker", "compose", "build", *base.APIS, timeout=900)
        probes = {}
        for service in base.APIS:
            changed = True
            base.run("docker", "compose", "up", "-d", "--no-deps", "--no-build", "--pull", "never",
                     "--force-recreate", "--wait", "--wait-timeout", "240", service)
            probe = base.probe_replica(service)
            validate_envelope(probe["status"], probe["body"])
            probes[service] = probe
            (evidence / "replica-denials.json").write_text(json.dumps(probes, indent=2) + "\n")
            print("PASS:", service, "returned a formatted, persisted HTTP 403 denial.", flush=True)
        # An absent app tests proxy response forwarding without publishing the LO1 app.
        status, headers, body = base.http(
            "http://127.0.0.1:8080/api/v1/applications/publish/000000000000000000000000", "POST")
        validate_envelope(status, body)
        if body["reasons"] != ["unique_discovered_application_required"]:
            raise RuntimeError("Unexpected proxy probe result")
        after = {s: base.runtime(s) for s in before}
        for service in UNCHANGED:
            if after[service] != before[service]:
                raise RuntimeError("A service outside the API update changed: " + service)
        report = {"scope": "Publish response compatibility update; browser retest still required",
                  "captured_at": datetime.now(timezone.utc).isoformat(),
                  "replica_probes_create_denial_receipts": True,
                  "proxy_probe_status": status, "proxy_probe": body, "runtime_after": after}
        (evidence / "installation.json").write_text(json.dumps(report, indent=2) + "\n")
    except Exception:
        if changed:
            print("Update failed; restoring the previous guarded API images.", flush=True)
            try:
                base.run(*restore)
            except Exception:
                print("Automatic rollback incomplete. Run:", shlex.join(restore), flush=True)
        raise
    print("PASS: proxy returned formatted denial; Appsmith, both proxies and OPA were unchanged.")
    print("Evidence saved:", evidence)
    print("Replica checks created evaluation receipts; they are not browser Deploy evidence.")
    print("Next: reopen the editor and test native Deploy once. LO2 remains partial.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("STOP: response update incomplete; exception_type=" + type(exc).__name__)
        sys.exit(1)
