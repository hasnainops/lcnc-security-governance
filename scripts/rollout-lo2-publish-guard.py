#!/usr/bin/env python3
"""Install the scoped manual-publish guard, retaining the running image versions.

Run from the project checkout after applying the patch and passing pytest.
No application, registration, classification, credential or approval is edited.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import shlex
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
TARGET = "6afabf4265d61d1e1b332ac1"
VERSION = "appsmith-publish-preflight-v1"
APIS = ("governance-api-a", "governance-api-b")
DIRECT = ["caddy", "reverse-proxy", "--from", ":80", "--to", "http://appsmith:80"]
CLIENT = build_opener(ProxyHandler({}))


def run(*args, capture=False, content=None, timeout=300):
    result = subprocess.run(args, cwd=ROOT, input=content, text=True,
                            capture_output=capture, timeout=timeout, check=True)
    return result.stdout.strip() if capture else None


def inspect(container, field):
    return json.loads(run("docker", "inspect", "--format", "{{json " + field + "}}",
                          container, capture=True, timeout=30))


def runtime(service):
    container = run("docker", "compose", "ps", "-q", service, capture=True, timeout=30)
    if not container or "\n" in container:
        raise RuntimeError("Expected one running container for " + service)
    return {"service": service, "container": container,
            "image_id": inspect(container, ".Image"),
            "command": inspect(container, ".Config.Cmd"),
            "ports": inspect(container, ".HostConfig.PortBindings"),
            "networks": sorted(inspect(container, ".NetworkSettings.Networks"))}


def http(url, method="GET", headers=None):
    try:
        response = CLIENT.open(Request(url, data=b"" if method == "POST" else None,
                                       headers=headers or {}, method=method), timeout=30)
    except HTTPError as error:
        response = error
    with response:
        body = response.read(65536)
        return response.status, dict(response.headers), json.loads(body) if body else None


def probe_replica(service):
    # This only evaluates the preflight endpoint. It never sends a publish to Appsmith.
    program = '''import json, urllib.request, urllib.error
r=urllib.request.Request("http://127.0.0.1:8000/internal/appsmith/publish-preflight",
 headers={"X-LCNC-Original-Method":"POST", "X-LCNC-Original-Uri":
 "/api/v1/applications/publish/6afabf4265d61d1e1b332ac1"})
try:
 response=urllib.request.urlopen(r,timeout=30)
except urllib.error.HTTPError as exc:
 response=exc
with response:
 body=response.read(65536)
 print(json.dumps({"status":response.status,"body":json.loads(body) if body else None}))
'''
    result = json.loads(run("docker", "compose", "exec", "-T", service, "python", "-",
                            content=program, capture=True, timeout=45))
    body = result.get("body") or {}
    if (result["status"] != 403 or body.get("scope") != VERSION
            or body.get("allowed") is not False or not body.get("decision_id")
            or "registration_status_requires_registered" not in body.get("reasons", [])):
        raise RuntimeError("Expected a persisted policy denial from " + service)
    return result


def main():
    run("docker", "compose", "config", "--quiet", capture=True)
    before = {s: runtime(s) for s in ("appsmith", "appsmith-proxy", "opa", *APIS)}
    labels = inspect(before["appsmith"]["container"], ".Config.Labels") or {}
    if labels.get("org.opencontainers.image.revision") != "d847cf495020767bfe53f4ead37a24513a51d7d4":
        raise RuntimeError("Appsmith revision differs from the verified publish route")
    if before["appsmith"]["ports"]:
        raise RuntimeError("Appsmith has directly published ports; review the boundary first")
    if (len(before["appsmith"]["networks"]) != 1
            or not before["appsmith"]["networks"][0].endswith("_appsmith_restricted")):
        raise RuntimeError("Unexpected Appsmith network boundary")
    if before["appsmith-proxy"]["command"] != DIRECT:
        raise RuntimeError("Proxy is not the recorded baseline; do not overwrite an existing guard")
    expected_proxy = "sha256:6b08c1b9858ca9a7d99c1da13c3695081e0e604c6cf214ca26a7ce0e2c4fd9b4"
    if before["appsmith-proxy"]["image_id"] != expected_proxy:
        raise RuntimeError("Proxy image differs from the supplied baseline")
    run("docker", "compose", "exec", "-T", "opa", "/opa", "test", "/policies", "-v")
    run("docker", "compose", "exec", "-T", "appsmith-proxy", "caddy", "validate",
        "--config", "/dev/stdin", "--adapter", "caddyfile",
        content=(ROOT / "appsmith/publish-guard.Caddyfile").read_text())

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    git_dir = Path(run("git", "rev-parse", "--absolute-git-dir", capture=True))
    evidence = git_dir / ("cr002-lo2-publish-guard-" + stamp)
    evidence.mkdir(mode=0o700)
    (evidence / "runtime-before.json").write_text(json.dumps(before, indent=2) + "\n")
    rollback = {"services": {}}
    for service in (*APIS, "appsmith-proxy"):
        tag = f"lcnc-lo2-rollback-{service}:{stamp.lower()}"
        run("docker", "image", "tag", before[service]["image_id"], tag)
        rollback["services"][service] = {"image": tag}
    rollback["services"]["appsmith-proxy"]["command"] = DIRECT
    rollback_path = evidence / "rollback.compose.json"
    rollback_path.write_text(json.dumps(rollback, indent=2) + "\n")
    restore = ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "-f", str(rollback_path),
               "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate",
               "--wait", "--wait-timeout", "240", *APIS, "appsmith-proxy"]
    (evidence / "rollback-command.txt").write_text(shlex.join(restore) + "\n")
    print("Rollback command:", shlex.join(restore), flush=True)
    changed = False
    try:
        run("docker", "compose", "build", *APIS, timeout=900)
        # Restart the EXISTING OPA container: do not recreate from a different tag.
        changed = True
        run("docker", "compose", "restart", "opa")
        probes = {}
        for service in APIS:
            run("docker", "compose", "up", "-d", "--no-deps", "--no-build", "--pull", "never",
                "--force-recreate", "--wait", "--wait-timeout", "240", service)
            probes[service] = probe_replica(service)
        (evidence / "replica-denials.json").write_text(json.dumps(probes, indent=2) + "\n")
        run("docker", "compose", "up", "-d", "--no-deps", "--no-build", "--pull", "never",
            "--force-recreate", "--wait", "--wait-timeout", "240", "appsmith-proxy")

        # A nonexistent native ID verifies routing without publishing the test app.
        status, headers, body = http("http://127.0.0.1:8080/api/v1/applications/publish/000000000000000000000000", "POST")
        if (status != 403 or not isinstance(body, dict) or body.get("scope") != VERSION
                or body.get("reasons") != ["unique_discovered_application_required"]):
            raise RuntimeError("Proxy did not return the expected guard denial")
        after = {s: runtime(s) for s in before}
        for service in ("appsmith", "opa", "appsmith-proxy"):
            if after[service]["image_id"] != before[service]["image_id"]:
                raise RuntimeError("An image version changed unexpectedly: " + service)
        report = {"scope": "Manual publish guard installation; not LO2 acceptance",
                  "captured_at": datetime.now(timezone.utc).isoformat(),
                  "proxy_probe_status": status, "proxy_probe": body, "runtime_after": after}
        (evidence / "installation.json").write_text(json.dumps(report, indent=2) + "\n")
    except Exception:
        if changed:
            print("Installation failed; restoring the previous API and direct proxy images.", flush=True)
            try:
                run(*restore)
            except Exception:
                print("Automatic rollback did not complete. Run:", shlex.join(restore), flush=True)
        raise
    print("PASS: both API replicas denied the review-pending LO1 probe.")
    print("PASS: the Appsmith proxy intercepted a publish request for a nonexistent application.")
    print("PASS: Appsmith, Caddy and OPA image IDs were preserved.")
    print("Evidence saved:", evidence)
    print("Next: authenticated native Deploy denial and remaining coverage tests. LO2 remains partial.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("STOP: publish guard installation incomplete; exception_type=" + type(exc).__name__)
        sys.exit(1)
