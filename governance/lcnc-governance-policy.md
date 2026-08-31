# LCNC Application Governance Policy

## Purpose

Define the minimum governance requirements for enterprise low-code/no-code applications managed by the LCNC Security Governance control plane.

## Scope

This policy applies to citizen-developed applications discovered on connected LCNC platforms.

Appsmith is the reference platform for the current MVP.

## Policy Principles

- Every discovered application must enter the governance inventory.
- Unknown applications must not be automatically trusted.
- Every governed application should have an accountable owner.
- Applications handling data must have an authoritative classification.
- External integrations must be identified and evaluated.
- Material application changes invalidate stale governance evidence.
- AI may assist analysis but may not independently authorize an application.
- Mandatory security policy is enforced through deterministic controls.
- Historical security and governance evidence must be retained.

## Required Governance States

Applications may result in:

- AUTO_APPROVE
- BUSINESS_REVIEW
- SECURITY_REVIEW
- BLOCK

The required outcome is determined from risk, policy, security and governance evidence.

## Shadow IT

Applications discovered outside the known governance inventory are treated as unregistered until validated.

Continuous discovery is used to identify new or changed applications.

Missing telemetry is recorded as unknown or pending rather than safe.

## AI Usage

AI capabilities include:

- anomaly detection
- classification recommendation

AI output is advisory.

Authoritative decisions remain governed through:

- stored application state
- deterministic risk assessment
- OPA policy
- security controls
- accountable human review

## Security Validation

Applications may be evaluated using:

- citizen-app security scanning
- risk assessment
- OPA governance policy
- OPA access policy
- DLP inspection
- Integration Gateway enforcement
- dynamic compliance controls

## Review and Escalation

Applications must be escalated when evidence indicates:

- critical or high risk
- unapproved external integrations
- restricted data exposure
- mandatory OPA denial
- stale governance evidence
- unresolved high-severity scanner findings

## Evidence Retention

The platform retains historical evidence including:

- risk assessments
- ML assessments
- scanner findings
- policy decisions
- governance decisions
- access decisions
- transfer decisions
- compliance assessments

## Roles

### Citizen Developer

Responsible for:

- providing accurate application context
- responding to security findings
- completing required remediation
- completing targeted training where required

### Business Owner

Responsible for:

- validating business purpose
- accepting business accountability
- supporting remediation

### Security / GRC Reviewer

Responsible for:

- reviewing elevated-risk applications
- evaluating exceptions
- confirming remediation
- approving or rejecting security-sensitive cases

### Platform Administrator

Responsible for:

- LCNC platform administration
- discovery connectivity
- operational support

## Exceptions

Exceptions to mandatory governance controls require documented review and accountable approval.

The current MVP does not implement a production exception-management system.

## Framework Alignment

This policy references security-governance themes from:

- ISO/IEC 27001:2022
- ISO/IEC 27002:2022
- OWASP ASVS 5.0.0

These mappings support control alignment only.

They do not represent certification or full framework conformance.
