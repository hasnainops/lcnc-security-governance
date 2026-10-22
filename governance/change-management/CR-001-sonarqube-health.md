# CR-001: SonarQube readiness health

## Change
Added a Docker health check requiring a successful HTTP request to
/api/system/status and a response containing status UP.
The probe runs every 30 seconds with bounded connection and request
timeouts, three retries and a 180-second startup grace.
Only SonarQube was recreated; its three named volumes were retained.

## Verification — 2026-10-22 UTC
- Compose configuration and Git whitespace validation passed.
- Docker reported SonarQube healthy.
- Host request returned HTTP 200 and JSON status UP.
- Current portal observation reported SonarQube running and healthy.
- Platform totals: 19 Docker-healthy; one check not configured (OPA).

## Limits
The recurring probe matches the status field using grep.
The deployment verification parsed the response as JSON.
Server readiness does not establish scan completion or quality-gate success.
Complete workflow acceptance remains pending.
