"""Server-owned connector interpretation, separate from transfer enforcement.

Public addresses establish external destinations. Private addresses require an
explicit lab CIDR boundary; loopback, link-local and mixed answers remain unknown.
DNS uses a bounded child process, never an HTTP request to the observed target.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address, ip_network

from .discovery_observation import ObservedHttpDestination
from .feature_assembly import assemble_features, observation_fingerprint
from .integration import _approved_external_hosts

VERSION = "connector-policy-v1"
PRIVATE_RANGES = tuple(map(ip_network, ("10.0.0.0/8", "172.16.0.0/12",
                                       "192.168.0.0/16", "fc00::/7")))
DNS_TIMEOUT_SECONDS = 3
MAX_DNS_HOSTS = 64

# Each batch has an OS-process deadline, including resolver shutdown. A stalled
# getaddrinfo cannot leak an unbounded number of threads into the API process.
_DNS_SCRIPT = """
import json, socket, sys
from concurrent.futures import ThreadPoolExecutor
def lookup(host):
    try:
        return host, sorted({x[4][0] for x in socket.getaddrinfo(
            host, 443, type=socket.SOCK_STREAM)})
    except OSError:
        return host, []
with ThreadPoolExecutor(max_workers=8) as pool:
    for host, addresses in pool.map(lookup, json.load(sys.stdin)):
        print(json.dumps([host, addresses]), flush=True)
"""


def _sha(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def load_policy():
    # Same exact host approval source and normalization as controlled egress.
    # Missing configuration is different from an explicitly empty allowlist.
    raw_hosts = os.environ.get("CONTROLLED_EGRESS_APPROVED_HOSTS")
    raw_boundary = os.environ.get("DISCOVERY_INTERNAL_CIDRS", "")
    approved, networks = set(), []
    approval_ok = raw_hosts is not None
    boundary_ok = True
    try:
        approved = _approved_external_hosts()
        for host in approved:
            ObservedHttpDestination(scheme="https", host=host)
    except (ValueError, TypeError):
        approval_ok = False
        approved = set()
    try:
        networks = sorted({ip_network(value.strip(), strict=True)
                           for value in raw_boundary.split(",") if value.strip()}, key=str)
        if any(not any(net.version == allowed.version and net.subnet_of(allowed)
                       for allowed in PRIVATE_RANGES) for net in networks):
            raise ValueError("Boundary must be an explicit private lab subnet")
    except (ValueError, TypeError):
        boundary_ok = False
        networks = []
    document = {"version": VERSION, "approval_available": approval_ok,
                "approved_hosts": sorted(approved), "boundary_valid": boundary_ok,
                "internal_cidrs": [str(net) for net in networks]}
    return {**document, "policy_sha256": _sha(document), "networks": networks}


def resolve_hosts(hosts):
    """Return validated addresses for each host; failures retain unknown values."""
    result, names = {}, []
    for host in sorted(set(hosts)):
        try:
            result[host] = [ip_address(host).compressed]
        except ValueError:
            names.append(host)
    if not names:
        return result
    try:
        process = subprocess.run([sys.executable, "-I", "-c", _DNS_SCRIPT],
            input=json.dumps(names[:MAX_DNS_HOSTS]), capture_output=True, text=True,
            timeout=DNS_TIMEOUT_SECONDS, check=False)
        output = process.stdout
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
    except OSError:
        output = ""
    for line in output.splitlines():
        try:
            host, addresses = json.loads(line)
            if host not in names or not isinstance(addresses, list):
                continue
            result[host] = sorted({ip_address(value).compressed for value in addresses})
        except (ValueError, TypeError):
            continue
    return result


def _trust(host, addresses, policy):
    if not addresses:
        return None, "destination_resolution_unavailable"
    ips = [ip_address(value) for value in addresses]
    if any(ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified
           or ip.is_reserved or getattr(ip, "ipv4_mapped", None) for ip in ips):
        return None, "destination_outside_verified_boundary"
    if all(ip.is_global for ip in ips):
        if not policy["approval_available"]:
            return "external_unknown_approval", "approval_policy_unavailable"
        return ("approved_external" if host in policy["approved_hosts"]
                else "unapproved_external"), None
    if policy["boundary_valid"] and all(
            any(ip.version == net.version and ip in net for net in policy["networks"])
            for ip in ips):
        return "internal", None
    return None, ("internal_boundary_invalid" if not policy["boundary_valid"]
                  else "destination_outside_verified_boundary")


def assemble_governed_features(observation, observation_id, *,
                               verified_changes_24h=None, cached_evidence=None):
    policy = load_policy()
    now = datetime.now(timezone.utc)
    fingerprint = observation_fingerprint(observation)
    cached = cached_evidence if isinstance(cached_evidence, dict) else {}
    try:
        evaluated_at = datetime.fromisoformat(cached.get("evaluated_at", ""))
        reusable = (cached.get("source_observation_id") == str(observation_id)
                    and cached.get("policy_sha256") == policy["policy_sha256"]
                    and cached.get("observation_fingerprint") == fingerprint
                    and now - timedelta(minutes=3) <= evaluated_at <= now)
    except (ValueError, TypeError):
        reusable = False
    if reusable:
        decisions = cached["connector_decisions"]
    else:
        hosts = {c.destination.host for c in observation.connectors
                 if c.destination_state == "observed"} if observation.collection_complete else set()
        answers = resolve_hosts(hosts)
        decisions = []
        for connector in sorted(observation.connectors, key=lambda c: c.connector_id):
            host = connector.destination.host if connector.destination is not None else None
            addresses = answers.get(host, [])
            if not observation.collection_complete:
                trust, reason = None, "collection_incomplete"
            elif connector.destination_state != "observed":
                trust, reason = None, "destination_" + connector.destination_state
            else:
                trust, reason = _trust(host, addresses, policy)
            decisions.append({"connector_id": connector.connector_id, "host": host,
                              "resolved_addresses": addresses, "trust": trust, "reason": reason})
    trust = {d["connector_id"]: d["trust"] for d in decisions}
    result = assemble_features(observation, destination_trust=trust,
                               verified_changes_24h=verified_changes_24h)
    # Address rotation within the same trust boundary is not a semantic change.
    semantic = {"version": VERSION, "policy_sha256": policy["policy_sha256"],
                "observation_fingerprint": fingerprint,
                "decisions": [{k: d[k] for k in ("connector_id", "host", "trust", "reason")}
                              for d in decisions]}
    result["evidence"] = {"version": VERSION, "source_observation_id": str(observation_id),
        "observed_at": observation.observed_at.isoformat(), "observation_fingerprint": fingerprint,
        "evaluated_at": cached["evaluated_at"] if reusable else now.isoformat(),
        "policy_sha256": policy["policy_sha256"], "approval_policy_available": policy["approval_available"],
        "internal_boundary_valid": policy["boundary_valid"], "internal_cidrs": policy["internal_cidrs"],
        "semantic_sha256": _sha(semantic), "connector_decisions": decisions,
        "pending_reasons": sorted(set(observation.pending_reasons)
                                  | {d["reason"] for d in decisions if d["reason"]}),
        "scope": "observed_configuration_and_host_policy",
        "transfer_enforcement_evaluated": False}
    return result
