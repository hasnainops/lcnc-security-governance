# CR-002: LO2 Appsmith publish denial checkpoint

Verdict: PARTIAL for LO2.1. The canonical manual Appsmith Deploy route was
blocked by the installed governance preflight in an authenticated negative test.
This is a scoped checkpoint, not complete LO2 or Appsmith-wide policy acceptance.

## Operator-supplied runtime evidence

Target governance application `20fe2957-f769-4faa-a23a-1fa28584c359` maps to
Appsmith application `6afabf4265d61d1e1b332ac1`. Its current posture is
unregistered, anomalous, review pending, classification unknown and required
training incomplete. The observed negative case must be denied.

- The operator installed the publish guard behind the Appsmith proxy. The
  focused Python suite passed 59 tests; the OPA suite passed 21 tests. The
  response-envelope follow-up passed 67 focused Python tests and both API
  replicas returned formatted, persisted HTTP 403 denials. These are operator
  outputs; the two patches are still local to the operator until committed.
- An authenticated discovery-account session read the target application
  through the same proxy, then issued one POST to
  `/api/v1/applications/publish/6afabf4265d61d1e1b332ac1`. It received
  HTTP 403 and `LCNC-PUBLISH-DENIED`. Header/body decision ID
  `e6f68de3-09cb-4cdc-ba74-f0b25b884c9d` matched the persisted
  `publish_preflight` deny receipt and its reasons. The preliminary check had
  separate decision ID `99254da5-c01f-456a-a19e-a8ba9127d947`.
- The operator's browser screenshot showed Appsmith's native Deploy control
  and the message: "Deployment blocked by governance. Review and resolve the
  application's outstanding governance requirements before deploying."
  The screenshot is conversation evidence and is not stored in this repository.
  It has no receipt identifier, so it cannot be paired to the API request above.

The sanitized terminal receipt remains on the operator's Mac at
`.git/cr002-lo2-native-publish-proof-20261118T024611918434Z/native-publish-denial.json`.
Earlier browser-adjacent access-decision counts also recorded denials, but
counting them does not establish one-to-one request attribution.

## Remaining LO2.1 coverage

1. The test establishes one canonical manual publish route through the proxy.
   Inspect other native publish, Git, import and configuration mutation routes
   and test that the intended governance rules intercept each relevant route.
2. The preflight uses a recent observed configuration; an edit between
   discovery and publish can change what is deployed. Establish how the
   protected operation is bound to the evaluated draft or record the race as
   an explicit boundary of the MVP.
3. Appsmith's application-home response omitted `lastDeployedAt` both before
   and after the test. This receipt cannot independently prove that native
   deployment metadata stayed unchanged. A suitable native state read or a
   separate published-state check is still needed for that assertion.
4. The observed screenshot shows a denial message but a blank editor/spinner.
   Verify normal editor behavior separately before calling the browser flow
   healthy. The screenshot alone does not prove the application identity or
   uniquely identify its audit receipt.

LO2.2 remains verified for observed workflow-change rescanning, with
integration-dependent and broader metadata coverage requiring separate checks.
LO2.3 remains partial: historical DLP receipts do not prove universal egress
enforcement; operation-level CTRL-06 evidence and source-versioned compliance
assessment remain to be established. No LO2.2 or LO2.3 verdict changes here.

Next acceptance step: inventory the Appsmith mutation routes at the deployed
image revision, define the intended interception boundary, test alternate
paths and the observation-to-publish race, then capture a native published-state
comparison without relaxing the negative-test application's governance policy.
