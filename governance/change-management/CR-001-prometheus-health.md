# CR-001: Prometheus readiness health

## Change
Added a Docker health check against the local /-/ready endpoint.
The probe runs every 30 seconds with a five-second wget timeout,
seven-second Docker timeout, three retries and 60-second startup grace.
Only Prometheus was recreated; its named data volume was retained.

## Verification — 2026-10-22 UTC
- Compose configuration and Git whitespace validation passed.
- Docker reported Prometheus healthy.
- Readiness endpoint returned Prometheus Server is Ready.
- Current portal observation reported Prometheus running and healthy.
- Platform totals: 17 Docker-healthy; three checks not configured.
- All five active scrape targets were up:
  Governance API A, Governance API B, Integration Gateway, OPA and Prometheus.

## Limits
Readiness does not establish scrape-target health.
Target health was verified separately at the time of inspection.
Neither check establishes complete business-workflow functionality.
