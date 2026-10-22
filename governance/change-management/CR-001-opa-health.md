# CR-001: OPA native HTTP health check

## Change
Added an exec-form Docker health check using the existing OPA binary.
The probe requests the local /health endpoint through http.send.
The query requires true = (response.status_code == 200).
No shell, additional package or image change was required.
Request timeout is three seconds; evaluation timeout is five seconds.

## Verification — 2026-10-22 UTC
- Successful HTTP 200 comparison exited zero.
- Deliberately incorrect status comparison exited one.
- Compose configuration validation and git diff checks passed.
- Only OPA was recreated.
- Docker reported OPA healthy.
- Host request to /health returned HTTP 200.
- Current portal observation reported all 20 services running and healthy.
- No Docker health checks remained unconfigured.

## Limits
This checks OPA HTTP health, not policy decision correctness.
Docker health and functional workflow evidence remain separate.
Complete workflow acceptance remains pending.
