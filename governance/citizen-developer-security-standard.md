# LCNC Citizen Developer Secure Development Standard

## Purpose

Define minimum secure-development expectations for citizen developers building low-code/no-code applications while preserving development speed and governance visibility.

## Scope

This standard applies to citizen-developed applications connected to the LCNC Security Governance platform.

Appsmith is the reference LCNC platform for the MVP.

## Core Requirements

Citizen-developed applications must:

- have an accountable owner
- have a documented business purpose
- identify the data they process
- maintain an authoritative data classification
- use approved integrations where possible
- avoid embedded credentials
- avoid unnecessary external connectivity
- remediate security findings
- participate in governance review when required

## Application Ownership

Every governed application should have an accountable owner responsible for:

- application purpose
- business context
- remediation coordination
- responding to governance requests

Applications without an owner must not be treated as fully governed.

## Data Handling

Applications may handle:

- public
- internal
- confidential
- restricted

Unknown classification must not be treated as public.

Restricted-data applications require stronger controls and review.

## Secure Integrations

Citizen developers should:

- use approved connectors
- remove unused connectors
- minimize external integrations
- use HTTPS
- avoid unapproved external destinations
- document required external dependencies

## Credential and Secret Handling

Credentials must not be embedded directly in application code, configuration, or source repositories.

Developers should:

- use approved environment or secret mechanisms
- avoid hard-coded passwords
- avoid hard-coded API keys
- avoid committing runtime `.env` files
- rotate exposed credentials

The MVP Security Scanner checks for possible embedded-secret conditions.

CI also performs repository secret scanning.

## Security Scanner Findings

Citizen applications may be evaluated for:

- unregistered application
- missing owner
- unknown classification
- unapproved external integration
- API-key usage
- insecure HTTP integration
- possible embedded secret
- sensitive data combined with external connectivity

High-severity findings should be remediated before approval where required.

## AI-Assisted Security Analysis

The platform may use AI / ML for:

- anomaly detection
- classification recommendations

AI output is advisory.

It must not be treated as final approval.

Mandatory decisions remain controlled by deterministic policy and accountable reviewers.

## DLP and Data Transfer

Sensitive outbound data should use governed transfer paths where applicable.

The Integration Gateway can block:

- unapproved external destinations
- external HTTP transfers
- restricted external transfers
- external transfers when classification is unknown

Only the minimum required data should be transferred.

## Least Privilege

Applications and users should receive only the permissions required for their role.

Application ownership does not automatically provide:

- approval rights
- restricted-data export rights
- privileged administration
- exception authority

OPA access policy enforces the MVP authorization rules.

## Security Reassessment

Material changes may invalidate previous evidence.

Examples:

- new integrations
- changed data fields
- changed classification
- changed ownership
- increased external exposure

The application may require:

- new ML analysis
- new security scan
- risk reassessment
- policy reassessment
- governance review

## Targeted Training

Training recommendations are generated from actual control gaps.

Examples include:

- secure integration practices
- data classification
- secure LCNC development
- DLP and safe sharing
- least privilege
- governance workflow

## Security Score and Gamification

The MVP uses an evidence-based security score.

Badges include:

- Gold
- Silver
- Bronze
- Needs Attention

This is a project-specific gamification mechanism and not an external security certification.

## Training Completion

Training completion may be tracked by:

- application
- subject
- training module

Achievement states include:

- training_pending
- security_progress
- secure_builder

Training completion does not override unresolved mandatory controls.

## DevSecOps Expectations

Project changes are validated through controls including:

- Python tests
- ML tests
- scanner tests
- DLP and gateway tests
- OPA policy tests
- Trivy scanning
- secret scanning
- dependency monitoring

Security failures should be remediated rather than bypassed.

## Prohibited Practices

Citizen developers must not intentionally:

- conceal applications from governance
- falsify application metadata
- disable mandatory security controls
- embed production secrets in source code
- bypass required OPA decisions
- bypass DLP enforcement for sensitive transfers
- represent AI output as formal approval
- treat missing evidence as a passed control

## Escalation Conditions

Security or governance review should occur when:

- restricted data is involved
- external destination approval is unclear
- a high or critical finding remains unresolved
- OPA denies a required action
- classification is uncertain
- governance evidence is stale
- a policy exception is required

## Roles

### Citizen Developer

Responsible for secure implementation and remediation.

### Business Owner

Responsible for validating application purpose and business need.

### Security / GRC Reviewer

Responsible for elevated-risk review and security exceptions.

### Platform Administrator

Responsible for platform operation and approved connectivity.

## Current MVP Boundary

The MVP demonstrates:

- automated discovery
- AI-assisted analysis
- security scanning
- governance controls
- targeted guidance
- training recommendations
- completion tracking
- gamification

It does not provide a full enterprise learning-management system.

## Framework Alignment

This standard aligns conceptually with secure-development, access-control, information-protection and awareness themes from:

- ISO/IEC 27001:2022
- ISO/IEC 27002:2022
- OWASP ASVS 5.0.0

These references demonstrate control intent only and do not claim certification or full framework conformance.
