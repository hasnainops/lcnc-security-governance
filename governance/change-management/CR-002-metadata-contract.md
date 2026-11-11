# CR-002 — Discovery Metadata Contract

Status: implementation contract draft.
Source baseline: 52f56ff439781552331f4a7c2119b2e8ae9aee58.

## Existing approval authority

The Governance API owns external-host approval through
CONTROLLED_EGRESS_APPROVED_HOSTS.

governance-api/app/integration.py derives destination trust server-side.
TransferEvaluationRequest forbids additional caller-supplied fields.
The gateway receives the derived trust classification.

Discovery assessment must reuse this approval source. It must not
maintain a separate list that could disagree with transfer enforcement.

This is host-level egress approval. It does not establish business
approval of an entire application or authorize every transfer.

An empty configured allowlist means no external hosts are approved.
Failure to obtain policy information is an unavailable-policy state,
not an empty allowlist.

## Observation and enforcement boundaries

An observed destination is evidence of application configuration,
not evidence that a transfer occurred.

HTTP transport does not establish whether a destination is external.
A private, loopback or unresolved address must not automatically be
labelled an approved internal integration.

Internal classification requires an explicit lab network boundary.
That boundary remains to be configured and validated.

The existing controlled-egress rejection of non-public destinations
remains applicable. Discovery observation must not weaken it.

Approved-host membership does not override DLP, unknown-classification,
restricted-data or insecure-transport rules.

## Feature definitions and availability

| Field | Definition and evidence requirement |
|---|---|
| connector_count | Distinct connectors used by the application, based on stable connector identities and complete collection. Action count is not a substitute. |
| external_integration_count | Distinct observed connectors with confirmed external destinations. Unresolved connections that could affect the total prevent a complete value. |
| unapproved_integration_count | External connectors whose destination hosts lack approval under the current server-owned host policy. This field represents host-policy approval within the MVP. |
| external_domain_count | Distinct normalized external destination hostnames, using the hostname convention of the existing egress policy. |
| changes_last_24h | Changes supported by a reliable historical source. Polling cycles and a single modification timestamp cannot establish this count. |
| business_purpose | Accountable owner-provided business context. |
| data_fields | Owner-provided or reliably observed schema descriptions; exclude actual sensitive record values. |
| connector_metadata | Sanitized, factual connector descriptions with observed and owner-provided information distinguished. |

The five count columns already exist as nullable integers.
NULL continues to mean unavailable or insufficient evidence.
Zero is permitted only when sufficient evidence establishes zero.

Partial observations may be retained as partial evidence, but must
not be supplied to ML as complete totals.

If polling-based change observations are used, their coverage and
limitations must be explicit. They must not silently be presented
as a complete change-event history.

Any change to model features or their meaning requires documented
compatibility analysis and, where necessary, retraining and evaluation.

## Provenance and completeness

The ingestion design must retain:

- Source platform and application identity.
- Observation and ingestion timestamps.
- Collector/contract version.
- Collection completeness and field-specific pending reasons.
- The approval-policy revision or fingerprint used for derived counts.

Allowlist changes must cause affected derived counts and assessments
to be reconsidered even when application configuration is unchanged.

Persist only the sanitized information needed for identification,
assessment and evidence. Exclude credentials, header values, request
bodies and URL user information, query strings and fragments.

Owner-provided business facts must remain distinguishable from
automatically observed technical facts.

## Processing behavior

Inventory persistence must succeed independently of ML availability.

Incomplete observations must not overwrite current facts with
fabricated zeros. Previously assessed facts must not remain presented
as current when their supporting evidence has become invalid.

Eligible assessments run automatically after relevant facts change.
Missing prerequisites remain pending with explicit reasons.

Reassessment must preserve assessment history and avoid duplicate
approval or training side effects.

ML classification remains advisory. Authoritative classification
changes continue through governed actions.

## Verification boundaries

The first response-validation increment passed 22 focused tests in
the user's checkout. Those tests include malformed responses,
explicit empty action lists and existing observation/sender behavior.

The existing workflow-ingestion test uses a fake database connection.
It does not prove that the SQL executes correctly in PostgreSQL.

Still required:

- Source feasibility and connector-identity verification.
- Internal-boundary configuration.
- Historical change-data strategy.
- Observation ingestion and persistence implementation.
- Policy-change and assessment-freshness tests.
- PostgreSQL integration tests.
- End-to-end Appsmith runtime evidence.
