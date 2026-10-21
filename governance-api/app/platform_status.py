"""Small, credential-free Docker observation contract shared with the host collector."""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path


SERVICES = (
    "governance-portal", "appsmith", "appsmith-proxy", "discovery",
    "enterprise-discovery", "governance-api", "governance-api-a",
    "governance-api-b", "risk-engine", "ml-analytics", "security-scanner",
    "opa", "governance-automation", "integration-gateway", "dlp-engine",
    "postgres", "vault", "prometheus", "grafana", "sonarqube",
)
DOCKER_STATES = {"created", "running", "paused", "restarting", "removing", "exited", "dead"}
HEALTH_STATES = {"healthy", "unhealthy", "starting", "not_configured", "unknown"}
COLLECTION_ERRORS = {"docker_unavailable", "docker_timeout", "invalid_docker_output", "catalog_mismatch"}
SNAPSHOT_PATH = Path("/run/observability/platform-status.json")
MAX_SNAPSHOT_BYTES = 128 * 1024
STALE_AFTER_SECONDS = 30
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Invalid observation time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Observation time requires a timezone")
    return parsed.astimezone(timezone.utc)


def unknown_services(observed_at=None):
    return [
        {"service": name, "container_count": None, "container_state": "unknown",
         "docker_health": "unknown", "image_ids": [], "observed_at": observed_at}
        for name in SERVICES
    ]


def collection_failure(reason, observed_at):
    if reason not in COLLECTION_ERRORS:
        raise ValueError("Invalid collection failure")
    return {"schema_version": 1, "observed_at": observed_at,
            "collection_status": "unavailable", "reason": reason,
            "services": unknown_services(observed_at)}


def validate_record(record):
    if record.get("service") not in SERVICES:
        raise ValueError("Unexpected service")
    if not isinstance(record.get("project"), str) or not record["project"]:
        raise ValueError("Missing project")
    if record.get("state") not in DOCKER_STATES:
        raise ValueError("Unknown Docker state")
    if record.get("health") not in (None, "", "healthy", "unhealthy", "starting"):
        raise ValueError("Unknown Docker health")
    image = record.get("image_id")
    if not isinstance(image, str) or not IMAGE_ID.fullmatch(image):
        raise ValueError("Invalid image ID")


def grouped_records(records):
    grouped = {name: [] for name in SERVICES}
    projects = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Invalid Docker record")
        if str(record.get("oneoff", "")).lower() == "true":
            continue
        validate_record(record)
        projects.add(record["project"])
        grouped[record["service"]].append(record)
    if len(projects) > 1:
        raise ValueError("Mixed Compose projects")
    return grouped


def build_snapshot(records, observed_at):
    """Reduce formatted inspection records; never forward raw Docker objects."""
    timestamp(observed_at)
    grouped = grouped_records(records)

    services = []
    for name, containers in grouped.items():
        count = len(containers)
        if count > 100:
            raise ValueError("Too many containers")
        state, health = "missing", "unknown"
        if count == 1:
            state = containers[0]["state"]
            health = containers[0].get("health") or "not_configured"
        elif count > 1:
            state = "multiple"
        services.append({
            "service": name, "container_count": count,
            "container_state": state, "docker_health": health,
            "image_ids": sorted({c["image_id"] for c in containers}),
            "observed_at": observed_at,
        })
    return {"schema_version": 1, "observed_at": observed_at,
            "collection_status": "ok", "reason": None, "services": services}


def validated_images(images, count):
    if not isinstance(images, list) or len(images) > count:
        raise ValueError("Invalid image list")
    if any(not isinstance(i, str) or not IMAGE_ID.fullmatch(i) for i in images):
        raise ValueError("Invalid image ID")
    if bool(images) != bool(count) or len(set(images)) != len(images):
        raise ValueError("Inconsistent image list")
    return images


def validated_entry(entry, observed_at):
    count = entry.get("container_count")
    state = entry.get("container_state")
    health = entry.get("docker_health")
    if type(count) is not int or not 0 <= count <= 100:
        raise ValueError("Invalid container count")
    if state not in DOCKER_STATES | {"missing", "multiple"} or health not in HEALTH_STATES:
        raise ValueError("Invalid service state")
    if (count == 0 and state != "missing") or (count == 1 and state not in DOCKER_STATES):
        raise ValueError("Inconsistent container state")
    if count > 1 and state != "multiple":
        raise ValueError("Multiple containers require explicit status")
    if count != 1 and health != "unknown":
        raise ValueError("Ambiguous health")
    if entry.get("observed_at") != observed_at:
        raise ValueError("Inconsistent observation time")
    return {"service": entry["service"], "container_count": count,
            "container_state": state, "docker_health": health,
            "image_ids": validated_images(entry.get("image_ids"), count),
            "observed_at": observed_at}


def validated_services(snapshot):
    """Validate expected fields and discard all extra fields at the API boundary."""
    entries = snapshot.get("services")
    if not isinstance(entries, list) or len(entries) != len(SERVICES):
        raise ValueError("Incomplete service catalog")
    by_name = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("service") not in SERVICES:
            raise ValueError("Invalid entry")
        name = entry["service"]
        if name in by_name:
            raise ValueError("Duplicate service")
        by_name[name] = validated_entry(entry, snapshot["observed_at"])
    return [by_name[name] for name in SERVICES]


def load_snapshot(path):
    path = Path(path)
    for attempt in range(3):
        try:
            if not path.is_file() or path.is_symlink():
                raise FileNotFoundError
            with path.open("rb") as stream:
                payload = stream.read(MAX_SNAPSHOT_BYTES + 1)
        except FileNotFoundError:
            if attempt == 2:
                raise
            time.sleep(0.05)
            continue

        if len(payload) > MAX_SNAPSHOT_BYTES:
            raise ValueError("Oversized snapshot")
        return json.loads(payload)


def observation(snapshot, now):
    if not isinstance(snapshot, dict) or type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != 1:
        raise ValueError("Invalid schema")
    observed = timestamp(snapshot.get("observed_at"))
    age = (now - observed).total_seconds()
    if age < 0:
        return {"reason": "snapshot_from_future"}
    timing = {"observed_at": observed.isoformat(), "age_seconds": round(age, 3)}
    if snapshot.get("collection_status") == "unavailable" and snapshot.get("reason") in COLLECTION_ERRORS:
        return {**timing, "reason": snapshot["reason"]}
    if snapshot.get("collection_status") != "ok":
        raise ValueError("Invalid collection result")
    return {**timing, "services": validated_services(snapshot),
            "observation_status": "current" if age <= STALE_AFTER_SECONDS else "stale",
            "reason": None if age <= STALE_AFTER_SECONDS else "snapshot_stale"}


def read_platform_status(path=SNAPSHOT_PATH, now=None):
    now = now or utc_now()
    result = {"schema_version": 1, "source": "docker_compose",
              "served_at": now.isoformat(), "observed_at": None,
              "age_seconds": None, "stale_after_seconds": STALE_AFTER_SECONDS,
              "observation_status": "unavailable", "reason": "snapshot_missing",
              "services": unknown_services()}
    try:
        result.update(observation(load_snapshot(path), now))
    except FileNotFoundError:
        pass
    except OSError:
        result["reason"] = "snapshot_unreadable"
    except (ValueError, TypeError, KeyError, RecursionError):
        result["reason"] = "snapshot_invalid"

    current = result["observation_status"] == "current"
    for entry in result["services"]:
        entry["observation_status"] = result["observation_status"]
        entry["functional_check"] = {"status": "not_configured", "observed_at": None}
    result["summary"] = {
        "expected_services": len(SERVICES),
        "running": sum(s["container_state"] == "running" for s in result["services"]) if current else None,
        "docker_healthy": sum(s["container_state"] == "running" and s["docker_health"] == "healthy" for s in result["services"]) if current else None,
        "health_not_configured": sum(s["docker_health"] == "not_configured" for s in result["services"]) if current else None,
        "missing": sum(s["container_state"] == "missing" for s in result["services"]) if current else None,
        "multiple": sum(s["container_state"] == "multiple" for s in result["services"]) if current else None,
    }
    return result
