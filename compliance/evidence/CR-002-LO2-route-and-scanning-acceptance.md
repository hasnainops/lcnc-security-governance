# CR-002 — LO2 Route and Scanning Acceptance

Date: 2026-11-21

## LO2.1 Alternate publication routes

Live governance proxy tests:

- Application creation: HTTP 403.
- Application cloning: HTTP 403.
- Both returned unreviewed_auto_publish_route.
- Native Git publication delegates to publishApprovedRelease.
- Git guard delegation and denial covered by Java unit tests.

Native source checkpoint:
c43614b584bb708c0873110d6383c2df3ab2af56

Scope limitations:

- Create and clone restrictions apply to the governance proxy.
- Direct isolated Appsmith creation remains available.
- Full native Git lifecycle runtime acceptance is not established.
- Universal publication enforcement is not claimed.

## LO2.2 Automated scanning lifecycle

Application:
ee0752ad-17e1-466f-92bc-6bbe2108f173

Baseline scan:
2f9bcbe4-617c-4b77-b6ee-c718f479b8e8

Baseline result: passed, zero findings.

Introduced a draft REST API named LO2_Insecure_Integration
with destination http://lo2-test.invalid/api.
The API was not executed or deployed.

Insecure observation:
cf452ed2-0858-465a-bbba-b8aaaca64d50

Automatic security scan:
15e0037d-9eac-4a04-b30d-8ec0c8a4a0d2

Results:

- One API action and one HTTP action observed.
- SEC-009 detected with high severity.
- Security scan failed.
- Scan history increased from five to six.
- Dynamic compliance evaluation returned fail.
- Governance evaluation automatically triggered.

Removed the insecure API configuration.

Remediation observation:
ac3174d2-2df5-4f41-8e42-10b31f19c608

Remediation scan:
59e8947b-b121-485d-8fa4-dac08da937f8

Results:

- Zero API actions and zero HTTP actions.
- Observation collection complete.
- Automatic scan passed with zero findings.
- Scan history increased from six to seven.
- Historical SEC-009 finding retained.

## Limitations and outstanding issues

Detection and remediation demonstrated for observed workflow
and HTTP action configurations.

Unresolved connector identity caused incomplete collection
during the insecure configuration test.

The remediation scan reported partial integration-rule
coverage during processing. A passing scan therefore does
not establish that every integration rule was evaluated.

The subsequent database query showed zero integrations
and connectors, but changes_last_24h remained null.

Risk assessment returned HTTP 500 during both cycles.
This operational issue requires focused diagnosis.

CTRL-06 and CTRL-07 compliance correlation remain open.

No universal connector coverage, enterprise certification,
or full LO2 completion is claimed.
