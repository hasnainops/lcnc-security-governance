# LCNC Access Control Standard

## Purpose

Define minimum access-control requirements for actions performed against governed low-code/no-code applications.

The standard is implemented in the MVP through OPA policy-as-code.

## Scope

This standard applies to governed application actions including:

- read
- modify
- review
- approve
- export

## Access Control Principles

- Access must follow least privilege.
- Role permissions must be evaluated before protected actions.
- Sensitive application state must influence authorization.
- Privileged actions require appropriate governance state.
- Restricted-data applications require stronger controls.
- Authorization decisions must be auditable.
- Missing authorization evidence must not be treated as approval.

## Policy Enforcement Point

OPA provides the mandatory access decision.

Policy package:

- `lcnc.access`

The Governance API submits authorization facts to OPA and persists the resulting decision.

## Supported Roles

### Viewer

Permitted:

- read

Not permitted:

- modify
- approve
- export
- privileged governance operations

### Developer

Permitted where policy allows:

- read
- modify
- export

Additional restrictions:

- restricted applications cannot be modified by developers
- restricted applications cannot be exported by developers
- privileged actions require a registered application

### Security Administrator

Permitted where policy allows:

- read
- review
- modify
- approve
- export

Security administrators remain subject to policy conditions.

## Sensitive Data Controls

Application classification is considered during authorization.

Classifications include:

- public
- internal
- confidential
- restricted

Restricted applications receive stronger authorization constraints.

A user's role alone does not automatically authorize every action.

## Registration Requirement

Privileged actions require the application to be registered.

Examples include:

- modify
- approve
- export

An unregistered or shadow application must not receive privileged authorization merely because the requesting role is powerful.

## Authorization Inputs

OPA may evaluate:

- requester role
- requested action
- application registration status
- application data classification

These underlying facts are evaluated directly.

The access decision does not rely solely on numerical risk score or AI output.

## Authorization Outputs

The policy returns evidence including:

- allow / deny
- role
- requested action
- reasons

The Governance API persists access decisions for audit history.

## Fail-Closed Behavior

If mandatory authorization cannot be obtained, the operation must not be treated as approved.

OPA failure must not result in fabricated access permission.

## Audit Requirements

Authorization evidence should include:

- application identifier
- requester role
- requested action
- decision
- reasons
- policy version
- evaluation timestamp

Historical access decisions must remain available for review.

## Access Review

Elevated or sensitive access should be reviewed when:

- application classification becomes restricted
- application registration state changes
- governance status becomes stale
- role or requested action changes materially
- repeated deny decisions occur

## Separation of Duties

The control model separates:

- citizen development
- business ownership
- security review
- platform administration

A citizen developer should not automatically become the approving authority for their own high-risk application.

## Current MVP Boundary

The MVP demonstrates policy-based authorization but does not implement:

- enterprise SSO
- identity-provider federation
- MFA
- production session management
- automated enterprise role provisioning
- privileged access management

These are production identity requirements.

## Framework Alignment

This standard aligns conceptually with access-control and least-privilege themes from:

- ISO/IEC 27001:2022
- ISO/IEC 27002:2022
- OWASP ASVS 5.0.0

The mapping demonstrates control intent only and does not claim certification or full conformance.
