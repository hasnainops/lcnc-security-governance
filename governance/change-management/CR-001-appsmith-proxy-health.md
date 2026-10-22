# CR-001: Appsmith proxy health

## Change
Added a Docker health check requiring HTTP 200 from the proxy's local
listener, which forwards to Appsmith.
The check runs every 30 seconds with bounded connection and request
timeouts, three retries and a 30-second startup grace.

## Verification — 2026-10-22 UTC
- Compose configuration and Git whitespace validation passed.
- Only appsmith-proxy was recreated.
- Docker reported the proxy healthy.
- Host browser entry on port 8080 returned HTTP 200.
- Current portal observation reported the proxy running and healthy.
- Platform totals: 16 Docker-healthy; four checks not configured.

## Limits
This establishes availability of the proxied page.
It does not verify login, application execution or complete workflows.
