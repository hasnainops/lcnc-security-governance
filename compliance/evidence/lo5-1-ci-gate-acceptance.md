# LO5.1 — Automated CI Security-Gate Acceptance

## Scope

Learning objective:
Deploy automated security testing integration with
platform deployment pipelines.

This record covers repository-level CI security-gate
enforcement, using a synthetic non-secret violation.

Deployment enforcement is assessed separately.

## Test environment

Repository: hasnainops/lcnc-security-governance
Pull request: https://github.com/hasnainops/lcnc-security-governance/pull/86
Test branch: audit/lo5-1-ci-gate-proof
Target branch: main

The pull request was created as a draft and must not
be merged.

## Negative acceptance test — PASS

Commit:
8ede7ca2d1825ddef3ddf139025fd41aa637d6fa

Test fixture:
lo5-1-fixture/.env

Synthetic content:
LO5_1_SYNTHETIC_ONLY=1

The fixture contained no actual credentials.

Workflow:
.github/workflows/devsecops-security.yml

Security control:
Ensure runtime .env is not committed

Observed result: FAILURE

GitHub Actions run:
https://github.com/hasnainops/lcnc-security-governance/actions/runs/45021988737

The Repository Security Scan job rejected the tracked
runtime .env fixture.

## Positive acceptance test — PASS

Corrective commit:
fcc64c10fc85730b2f904614471e3e91bea7c29d

Correction:
Removed the synthetic tracked .env fixture.

Observed result: SUCCESS

GitHub Actions run:
https://github.com/hasnainops/lcnc-security-governance/actions/runs/45022288718

The same security control returned success.

Additional successful checks:
- Python Security Tests
- OPA Policy Tests
- Security Validation
- SonarCloud Code Analysis
- OWASP ZAP Baseline

Security Validation run:
https://github.com/hasnainops/lcnc-security-governance/actions/runs/45022288722

OWASP ZAP run:
https://github.com/hasnainops/lcnc-security-governance/actions/runs/45022288820

## Conclusion

PASS — Repository-level CI security-gate fail/pass
enforcement verified using two linked revisions.

The negative test demonstrated security-check failure.
The corrected revision demonstrated recovery.

## Image vulnerability gate — negative acceptance

Workflow:
`.github/workflows/objective15-remediation.yml`

Failed deployment-request run:
https://github.com/hasnainops/lcnc-security-governance/actions/runs/45022980372

Source revision:
`fcc64c10fc85730b2f904614471e3e91bea7c29d`

Observed:
- Python security scanner tests: PASS
- OPA policy tests: PASS
- Container build: PASS
- Pre-deployment Trivy gate: FAIL
- Validated image preservation: SKIPPED
- Approved deployment: SKIPPED

This was a workflow_dispatch execution with deploy=true.

The failed validation job prevented the dependent
deployment job from running.

## Vulnerability discovery and diagnosis

Diagnostic-retention change:
`6c4174c1ea664e45efac8919933179aac7423082`

Workflow run:
https://github.com/hasnainops/lcnc-security-governance/actions/runs/45024747226

The updated workflow retained the Trivy JSON report
despite the blocking security-gate failure.

Observed finding:
- Vulnerability: CVE-2026-85091
- Severity: HIGH
- Package: zlib1g
- Installed Debian version:
  1:1.3.dfsg+really1.3.1-1+b1
- Fixed version reported by Trivy:
  1:1.3.dfsg+really1.3.1-1+deb13u1
- Container OS: Debian 13.7
- Blocking HIGH/CRITICAL findings: 1

The CVE details originate from the retained
pre-deployment Trivy JSON report.

## Remediation and successful validation

Remediation commit:
`c1374d2b0c54793003b926511658c74c9b19efbd`

Change:
Added `zlib1g` to the Dockerfile's existing
Debian security-package upgrade command.

Successful validation run:
https://github.com/hasnainops/lcnc-security-governance/actions/runs/45025213924

Observed:
- Container build: PASS
- Pre-deployment Trivy gate: PASS
- Diagnostic artifact: RETAINED
- Validated container image artifact: RETAINED
- Blocking HIGH/CRITICAL findings: 0
- CVE-2026-85091 findings: 0

The report's normalized package version did not
include the complete Debian package revision.
The successful scan and absence of the original
CVE provide the verified remediation result.

## Approved deployment acceptance

Workflow run:
https://github.com/hasnainops/lcnc-security-governance/actions/runs/45025760057

Source commit:
`c1374d2b0c54793003b926511658c74c9b19efbd`

Environment:
`security-remediation`

The deployment job was observed waiting behind
the environment's required-reviewer protection.
It subsequently completed successfully.

Validation job result: PASS
Approved deployment job result: PASS
Container deployment result: PASS
Runtime health verification: PASS
Post-deployment Trivy scan: PASS
Final evidence artifact upload: PASS

Validated container image:

`sha256:2170134851a82c924212978374eb7610aae9aca1d05113f906f674d04d2d50ac`

Deployed container image:

`sha256:2170134851a82c924212978374eb7610aae9aca1d05113f906f674d04d2d50ac`

Image identity: MATCH
Runtime health: healthy
Post-deployment HIGH/CRITICAL findings: 0
Post-deployment CVE-2026-85091 findings: 0

Completion timestamp:
2026-11-22T13:10:57Z

Final evidence artifact:

`objective15-remediation-evidence-c1374d2b0c54793003b926511658c74c9b19efbd`

## Acceptance boundary and limitations

The observed deployment ran on an isolated
GitHub-hosted CI runner.

It does not establish a persistent production
deployment or production security authorization.

Repository-level CI fail/pass enforcement and
image-level vulnerability gating were demonstrated.

A successful SonarCloud analysis was observed,
but mandatory SonarCloud quality-gate enforcement
through repository rules has not been independently
verified.

The OWASP ZAP baseline passed, but its existing
warning-tolerant configuration and limited endpoint
scope do not establish comprehensive DAST coverage.

Repository branch protection and required-check
enforcement remain separately unverified.

The approved deployment workflow exercised a
security-scanner image, not every platform workload.

The validated source commit was on the isolated
acceptance branch. The two verified security changes
were subsequently imported into the assurance branch;
the integrated assurance revision has not yet been
independently retested.

Temporary PR #86 was closed without merging.
The experimental acceptance history remains
separate from the assurance branch.

## Git integration and acceptance PR closure

Assurance branch:
`audit/learning-objective-assurance`

Verified integration commit:
`491b55983370cada27f9884cdeb235e87e7754f4`

Temporary acceptance PR:
https://github.com/hasnainops/lcnc-security-governance/pull/86

PR status: CLOSED — NOT MERGED
Closure date: 2026-11-22

The validated Dockerfile security fix, Trivy diagnostic
retention improvement, and supporting governance evidence
were committed and pushed to the assurance branch.

The experimental PR history was not merged into main.

The integration commit itself was not independently
subjected to the complete acceptance test suite.
This limitation remains documented.

## Overall assessment

LO5.1 technical acceptance: PASS within the
documented isolated CI/CD lab boundary.

The evidence demonstrates:
- Insecure CI change rejected
- Corrected CI change accepted
- Vulnerable image rejected
- Vulnerability remediated
- Patched image validated
- Reviewer-gated deployment completed
- Exact image identity verified
- Runtime health verified
- Post-deployment scan passed

Documentation reconciliation, assurance-branch
Git integration, and temporary PR closure are complete.

Overall LO5.1 project closure: COMPLETE within the
documented isolated CI/CD acceptance boundary.
