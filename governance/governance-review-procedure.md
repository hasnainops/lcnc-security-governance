# LCNC Governance Review and Escalation Procedure

## Purpose

Define the operational procedure for reviewing, escalating, remediating, and reassessing low-code/no-code applications governed by the LCNC Security Governance platform.

## Scope

This procedure applies to applications that enter governance through:

- continuous discovery
- manual registration
- application change
- security reassessment
- policy reevaluation

## Governance Outcomes

The MVP uses four operational outcomes:

- AUTO_APPROVE
- BUSINESS_REVIEW
- SECURITY_REVIEW
- BLOCK

These outcomes are based on current governance and security evidence.

## 1. Discovery

The continuous discovery process identifies:

- known applications
- changed applications
- previously unknown applications

Unknown applications are treated as unregistered until validated.

Discovery evidence is stored in the governance inventory.

## 2. Metadata Validation

The platform evaluates whether required application metadata is available.

Examples include:

- owner
- business purpose
- data classification
- integration metadata
- behavioral telemetry

If required evidence is missing:

- analysis may remain pending
- controls may remain not assessed
- missing evidence must not be treated as passed

## 3. Automated Security Analysis

Where sufficient evidence is available, the platform performs:

- ML anomaly analysis
- AI-assisted classification
- citizen application security scanning
- risk assessment

These results contribute evidence but do not independently override mandatory policy.

## 4. Mandatory Policy Evaluation

OPA evaluates application facts against governance policy.

OPA may return:

- ALLOW
- DENY

A DENY indicates that mandatory policy conditions are not satisfied.

The application must not be treated as approved solely because its numerical risk score is low.

## 5. Governance Outcome Determination

The governance workflow combines available evidence into an operational outcome.

### AUTO_APPROVE

May be used where:

- mandatory policy allows
- risk is acceptable
- required metadata is present
- no blocking security condition exists

### BUSINESS_REVIEW

Used when business context or ownership confirmation is required.

Examples:

- unclear business purpose
- ownership uncertainty
- moderate business-risk decision

### SECURITY_REVIEW

Used when elevated security attention is required.

Examples:

- high-risk application
- unapproved integration
- confidential or restricted data concerns
- unresolved high-severity findings
- classification uncertainty
- abnormal application behavior

### BLOCK

Used when mandatory controls prohibit continued operation or transfer.

Examples:

- OPA mandatory denial
- prohibited external transfer
- restricted-data exfiltration condition
- unresolved blocking security condition

## 6. Review Responsibilities

### Citizen Developer

Responsible for:

- supplying accurate application context
- addressing findings
- completing required remediation
- completing assigned training

### Business Owner

Responsible for:

- validating business purpose
- confirming ownership
- evaluating business need
- supporting remediation decisions

### Security / GRC Reviewer

Responsible for:

- elevated-risk review
- security exception analysis
- high-sensitivity data review
- remediation validation
- approval or rejection where security review is required

### Platform Administrator

Responsible for:

- platform availability
- connector configuration
- discovery operation
- technical support

## 7. Escalation Triggers

An application should be escalated when one or more of the following occurs:

- OPA returns DENY
- risk becomes high or critical
- scanner produces high or critical findings
- an unapproved external integration exists
- restricted data is identified
- DLP detects higher sensitivity than declared
- classification remains uncertain
- owner is missing
- governance evidence becomes stale
- repeated authorization denial occurs
- repeated blocked transfer attempts occur
- required telemetry is unavailable for an extended period

## 8. Business Review Procedure

For BUSINESS_REVIEW:

1. Confirm accountable owner.
2. Confirm business purpose.
3. Validate application necessity.
4. Review integration requirements.
5. Review data classification.
6. Document the resulting decision.
7. Return unresolved security concerns to Security / GRC.

Possible outcomes:

- return for remediation
- escalate to SECURITY_REVIEW
- approve where policy allows

## 9. Security Review Procedure

For SECURITY_REVIEW:

1. Review current application inventory.
2. Review authoritative classification.
3. Review ML anomaly evidence.
4. Review ML classification recommendation.
5. Review scanner findings.
6. Review risk score and contributing factors.
7. Review OPA policy decision.
8. Review integration trust.
9. Review DLP and transfer history where relevant.
10. Review dynamic compliance status.
11. Determine remediation requirements.
12. Record the review outcome.

Possible outcomes:

- approve
- require remediation
- maintain review state
- block
- request documented exception review

## 10. Block Procedure

When an application or action is blocked:

1. Record the reason.
2. Preserve supporting evidence.
3. Identify the responsible owner.
4. Provide remediation guidance.
5. Prevent the blocked action where technically enforced.
6. Reassess after remediation.

A BLOCK must not be silently converted into approval.

## 11. Remediation

Typical remediation actions include:

- assign owner
- correct classification
- remove unapproved integration
- replace HTTP with HTTPS
- remove embedded credentials
- reduce external exposure
- resolve scanner findings
- complete required security review
- update stale application metadata

Remediation should target the specific failed control.

## 12. Reassessment

After material remediation, affected assessments should be rerun.

The reassessment path may include:

- discovery refresh
- ML anomaly analysis
- classification analysis
- security scan
- risk assessment
- OPA evaluation
- governance workflow
- dynamic compliance

Previous historical evidence remains retained.

## 13. Stale Evidence

Material application changes may make previous evidence stale.

Examples:

- classification change
- owner change
- integration change
- behavioral telemetry change
- major application modification

Stale evidence must not be represented as a current approval.

## 14. Exception Handling

A policy exception requires:

- documented business justification
- identified risk
- accountable approver
- defined scope
- defined duration where applicable
- compensating controls
- review date

The current MVP does not implement a full production exception-management workflow.

Exceptions must not be created by altering or bypassing mandatory policy without documented authorization.

## 15. Evidence Requirements

Review evidence may include:

- application metadata
- discovery status
- anomaly assessment
- classification assessment
- scanner findings
- risk assessment
- OPA decision
- access decisions
- transfer events
- compliance assessment
- remediation status
- training completion

## 16. Dynamic Compliance Use

Dynamic compliance should be used to identify current gaps.

Control states are:

- pass
- fail
- not assessed

A failed or not-assessed control should remain visible until supporting evidence changes.

## 17. Citizen Developer Feedback

Following review, the developer should receive:

- identified control gaps
- remediation guidance
- targeted training recommendations
- current security score
- current achievement status

Training completion does not replace unresolved mandatory remediation.

## 18. Review Closure

A review may be closed when:

- mandatory policy conditions are satisfied
- required remediation is completed
- material findings are addressed
- responsible reviewers have completed required actions
- current evidence supports the final governance outcome

Historical evidence remains available after closure.

## 19. Monitoring After Approval

Approval is not permanent trust.

Applications remain subject to:

- continuous discovery
- application change detection
- security reassessment
- policy reevaluation
- compliance reevaluation

A later material change may trigger a new review.

## Current MVP Boundary

The MVP demonstrates:

- automated discovery
- evidence-based review
- automated policy decisions
- business/security escalation states
- remediation guidance
- reassessment
- historical evidence retention

The MVP does not provide:

- enterprise ticketing integration
- formal SLA management
- production exception workflow
- enterprise approval signatures
- legal-record retention controls

## Framework Alignment

This procedure aligns conceptually with governance, risk treatment, secure-development, access-control and continual-review themes from:

- ISO/IEC 27001:2022
- ISO/IEC 27002:2022
- OWASP ASVS 5.0.0

These references demonstrate control alignment only and do not claim certification or full framework conformance.
