# CR-001: Discovery cycle health

## Change
Discovery records a monotonic timestamp after a cycle returns successfully.
Startup and caught cycle failures clear the previous success marker.
The local health probe rejects missing, invalid, future or older-than-180-second
evidence. It performs no network requests and reads no credentials.

Docker runs the probe every 30 seconds, with a five-second timeout,
120-second startup grace and three consecutive failures before unhealthy.

## Verification — 2026-10-22 UTC
- Health and existing Appsmith workflow tests: 15 passed.
- Only the discovery service was rebuilt and recreated.
- Live health probe returned Discovery cycle recent.
- Docker reported the discovery container healthy.
- The 01:53:34 UTC cycle completed with three known applications.
- Portal observation was current and reported discovery running and healthy.
- Platform totals: 15 Docker-healthy; five health checks not configured.
- Previous image retained as:
  lcnc-discovery:before-cycle-health-fc17474

## Limits
This checks recent cycle completion, not complete ML or classification
success. Metadata gaps and internally handled errors require separate evidence.
Docker unhealthy status alone does not automatically restart the worker.
Full workflow acceptance remains pending.
