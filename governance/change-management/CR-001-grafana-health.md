# CR-001: Grafana health check

## Change
Added a Docker health check requiring HTTP 200 from /api/health.
The probe runs every 30 seconds with bounded connection and request
timeouts, three retries and a 60-second startup grace.
Only Grafana was recreated; its data volume and provisioning mounts
were retained.

## Verification — 2026-10-22 UTC
- Compose configuration and Git whitespace validation passed.
- Docker reported Grafana healthy.
- Host request to port 3001 returned HTTP 200 and database status ok.
- Current portal observation reported Grafana running and healthy.
- Platform totals: 18 Docker-healthy; two checks not configured.

## Limits
The recurring Docker probe checks the HTTP status.
The database response field was verified separately during deployment.
Dashboard queries and Prometheus datasource connectivity were not tested
by this change. Complete workflow acceptance remains pending.
