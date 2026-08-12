# LCNC Data Classification and DLP Standard

## Purpose

Define how data handled by citizen-developed LCNC applications is classified, inspected, and protected from inappropriate external transfer.

## Scope

This standard applies to:

- LCNC application metadata
- application data fields
- connector metadata
- external integrations
- outbound data transfers
- DLP inspection evidence

## Data Classification Levels

The MVP uses four classifications:

### Public

Information approved for public disclosure.

### Internal

Information intended for internal organizational use.

### Confidential

Sensitive business or personal information requiring controlled access and handling.

### Restricted

Highly sensitive information requiring the strongest controls.

Examples may include:

- payment-card data
- government identifiers
- privileged credentials
- highly sensitive financial information

## Authoritative Classification

Every governed application should have an authoritative stored classification.

The authoritative classification is used by:

- risk assessment
- OPA policy
- access control
- DLP / transfer enforcement
- dynamic compliance

Missing classification must not be treated as public.

## AI-Assisted Classification

The MVP uses:

- TF-IDF
- Logistic Regression
- model version `classification-v1`

Inputs may include:

- application name
- business purpose
- data-field metadata
- connector metadata

Outputs include:

- suggested classification
- confidence
- review-required state

AI output is advisory.

It does not automatically replace the authoritative classification.

## Classification Review

Human review should occur when:

- AI confidence is below the configured threshold
- restricted data may be present
- application purpose changes
- data fields materially change
- external connectors change
- business context conflicts with the model suggestion

## DLP Inspection

The DLP Engine inspects outbound content and schema indicators.

Current MVP detections include:

- email addresses
- phone numbers
- payment-card numbers
- SSN patterns
- confidential field-name patterns
- restricted field-name patterns

## DLP Evidence Minimization

Raw sensitive values must not be stored in audit evidence.

Persisted DLP evidence should contain only safe metadata such as:

- detected data type
- finding count
- highest sensitivity
- engine version
- transfer decision

## Effective Sensitivity

The Integration Gateway determines effective sensitivity using the stronger of:

- authoritative declared classification
- DLP-detected sensitivity

Example:

Declared:

- confidential

DLP detects:

- restricted

Effective sensitivity:

- restricted

This prevents a lower declared classification from weakening DLP enforcement.

## External Transfer Controls

Outbound transfer evaluation considers:

- authoritative classification
- DLP-detected sensitivity
- destination trust
- transport security

Destination trust levels include:

- internal
- approved external
- unapproved external

## Mandatory Blocks

The current MVP blocks examples including:

- unknown classification to an external destination
- transfer to an unapproved external destination
- unencrypted HTTP transfer to an external destination
- restricted data transfer to an external destination

## Fail-Closed DLP Behavior

If the DLP Engine is unavailable:

- the Integration Gateway must not bypass inspection
- the transfer is blocked

If DLP inspection fails:

- the transfer must not be treated as approved

## Transfer Audit Evidence

The platform may persist:

- application ID
- destination scheme
- destination host
- destination trust
- authoritative classification
- effective sensitivity
- allow/block decision
- reasons
- DLP finding count
- detected data types
- engine version
- evaluation timestamp

Raw transfer content is excluded from the audit record.

## Data Minimization

Citizen applications should process and transfer only the minimum data necessary for the approved business purpose.

Developers should:

- avoid unnecessary sensitive fields
- remove unused connectors
- avoid unnecessary external destinations
- limit exported data
- prefer approved integrations

## Unknown Data

Unknown classification is not equivalent to public classification.

When classification cannot be established:

- the application remains not fully assessed
- sensitive external transfer should not be permitted by default
- governance review may be required

## Roles and Responsibilities

### Citizen Developer

Responsible for:

- accurately describing handled data
- identifying business purpose
- using approved destinations
- responding to DLP/security findings

### Business Owner

Responsible for:

- validating business need
- confirming application purpose
- supporting classification decisions

### Security / GRC Reviewer

Responsible for:

- reviewing high-sensitivity classifications
- reviewing restricted-data use
- evaluating transfer exceptions
- confirming remediation

## Current MVP Boundary

The MVP demonstrates:

- metadata-assisted classification
- AI classification suggestions
- deterministic DLP detection
- application-layer transfer enforcement
- safe audit evidence

The MVP does not claim:

- enterprise-wide network DLP
- endpoint DLP
- CASB coverage
- discovery of every sensitive-data source
- forced routing of every enterprise network path through the gateway

## Framework Alignment

This standard aligns conceptually with data-classification, information-protection, access-control and secure-transfer themes from:

- ISO/IEC 27001:2022
- ISO/IEC 27002:2022
- OWASP ASVS 5.0.0

These references demonstrate control intent only and do not claim certification or full framework conformance.
