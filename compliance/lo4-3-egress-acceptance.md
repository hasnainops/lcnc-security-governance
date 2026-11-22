# LO4.3 — Data Exfiltration Monitoring and Prevention

## Acceptance status

PASS — Demonstrated within the MVP laboratory boundary.

Acceptance date: 2026-11-22 (UTC).

Learning objective: Configure data exfiltration monitoring and
prevention for citizen-developed integrations.

## Genuine Appsmith integration

- Application: Customer Data Export
- Platform: Appsmith
- Appsmith application ID: 6a798ffd18167479617361d4
- Governed application ID: 886550b7-f673-445c-a79b-e8d1a4cbfdfd
- Integration action: LO4_ControlledExport
- HTTP method: POST
- Controlled route: /applications/{application_id}/controlled-egress
- Destination host: webhook.site
- Transport: HTTPS
- Declared classification: confidential
- Test data: synthetic only
- Execution context: Appsmith editor

## Security controls

- Verified Vault caller identity.
- Server-side OPA access authorization.
- Application-, subject- and action-scoped JIT authorization.
- Application governance policy evaluation.
- Server-owned destination trust classification.
- DLP inspection and fail-closed enforcement.
- Restricted data prevention for approved external destinations.
- Validated DNS destination addresses and pinned socket connections.
- TLS hostname and certificate verification.
- Redirect and environment-proxy bypass prevention.
- Persisted transfer enforcement evidence.

## Live transfer acceptance evidence

| Transfer ID | Decision | Enforcement | Upstream HTTP |
|---|---|---|---|
| 55bdb5d8-af1f-43d8-a83c-675b5d4a05e3 | ALLOW | forwarded_upstream | 200 |
| 95288031-15ad-4dfe-be54-d3cd65eec38b | BLOCK | blocked_before_send | NULL |
| d6c75139-2d66-421b-b5ed-d30539f9b123 | BLOCK | blocked_before_send | NULL |

All three records were retrieved from integration_transfer_events.

### Permitted transfer

- Evaluated: 2026-11-22 08:29:15.113166 UTC
- Enforced: 2026-11-22 08:29:16.713640 UTC
- Destination trust: approved_external
- Policy reason: policy_requirements_satisfied
- DLP finding count: 0
- Upstream HTTP status: 200
- Receiver payload: LO4 synthetic ALLOW test
- Independently observed receiver requests: 1 POST
- Receiver request ID: 8a930510-acb1-4f99-bdf7-5c7a0c72e9e0

### Restricted transfer prevention

Two restricted transfer attempts were recorded at:

- 2026-11-22 08:30:41.146895 UTC
- 2026-11-22 08:30:42.872045 UTC

Both attempts produced:

- Decision: block
- Allowed: false
- Destination trust: approved_external
- Reason: restricted_data_external_transfer
- Enforcement outcome: blocked_before_send
- DLP sensitive data detected: true
- DLP finding count: 3
- Upstream HTTP status: NULL

Detected finding types:

- phone_number
- restricted_field_schema
- social_security_number

The independent HTTPS receiver contained exactly one request
after both blocked attempts. No blocked payload was received.

## Demonstrated network boundary

Appsmith was attached only to the internal appsmith_restricted
Docker network. Governance API backends and the Integration
Gateway remained on the backend network.

Observed TCP connectivity from the Appsmith container:

| Tested destination | Observed result |
|---|---|
| governance-api:8000 | CONNECTED |
| integration-gateway:8005 | UNREACHABLE |
| 1.1.1.1:443 | UNREACHABLE |

These results demonstrate the tested container routing boundary.
The gateway probe establishes unreachability of the tested
host and port, not proof of every possible gateway listener.

The lab does not establish universal enterprise-wide exfiltration
prevention, browser-side isolation, or protection against every
possible relay through dual-homed services.

## Connection lifecycle remediation

An initial acceptance attempt failed with HTTP 500 because
application policy evaluation reused a closed database connection.

The defect was corrected in governance-api/app/policy.py by
preserving the optional caller-managed connection and using
separate read and write connection variables.

Four focused regression tests passed.

Both corrected Governance API backends were rebuilt and verified
healthy before successful live acceptance.

## Authorization and cleanup evidence

- JIT grant ID: 8ae259e6-2b13-4695-8694-d5277eb88152
- Authenticated privilege request: HTTP 201
- Authorized reviewer approval: HTTP 200
- Grant status during execution: active
- Final grant status: revoked
- Temporary Vault tokens, accounts and identities: cleaned
- Original allowlist: example.com
- Original allowlist restored and verified on both API backends
- Existing application and acceptance audit records retained

## Supporting implementation and tests

- governance-api/app/main.py
- governance-api/app/integration.py
- governance-api/app/policy.py
- scripts/run-lo4-egress-prevention.py
- scripts/verify-lo4-egress-prevention.py
- tests/test_controlled_egress.py
- tests/test_controlled_egress_route.py
- tests/test_lo2_egress_receipts.py
- tests/test_lo4_dns_pinning.py
- tests/test_lo4_egress_authorization.py
- tests/test_lo4_pinned_tls_integration.py
- tests/test_lo4_policy_connection_lifecycle.py

## Evidence handling

No credentials, temporary tokens, complete receiver URLs,
restricted payload values or source IP addresses are included
in this evidence document.

External receiver evidence was independently inspected through
the Webhook.site interface during live acceptance.

## Conclusion

LO4.3 acceptance passed within the documented MVP lab boundary.

The genuine Appsmith integration delivered permitted synthetic
data to an approved HTTPS destination, while two restricted
transfer attempts were prevented before outbound execution.

Production-wide enforcement remains outside this lab assurance.
