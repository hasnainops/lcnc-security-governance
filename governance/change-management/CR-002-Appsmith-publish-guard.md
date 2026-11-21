# CR-002 — Appsmith manual publish preflight

Status: installed with a recorded native publish denial; error-response
compatibility correction prepared. Browser retest and remaining acceptance pending.
This does not close LO2.1 or change the existing LO1 acceptance.

## Problem and scope

The deployed Caddy proxy forwarded Appsmith API requests without consulting the
governance decisions. Recording an OPA allow/deny did not intercept native Deploy.
The v2.2 Appsmith image identifies revision
`d847cf495020767bfe53f4ead37a24513a51d7d4`; its ApplicationControllerCE maps manual
publish to `POST /api/v1/applications/publish/{branchedApplicationId}`.

The new Caddy preflight intercepts that canonical, non-Git publish request.
The proxy overwrites routing headers and sends neither cookies nor Authorization
to the governance preflight. On allow, it forwards the original request to
Appsmith, which still checks its native session and permissions. Denials and
preflight failures are returned without contacting the Appsmith publish endpoint.
The guard runs on all requests to avoid a path-matcher normalization bypass;
ordinary canonical reads/writes return immediately without database/OPA queries.
The UI consequently depends on preflight availability. Noncanonical encoded
paths are rejected conservatively and may require a future compatibility change.

## Decision evidence

The server resolves the native Appsmith ID to exactly one discovered application.
It requires registered status, known authoritative classification, assessed low
risk, completed scan with a passing result, assessed non-anomalous state, no
classification review requirement, completed required training, and a current
automatic governance approval. The existing governance policy is consulted again.
A dedicated default-deny Rego policy supplies publish-specific conditions.

The current observed source must be complete, no more than three minutes old,
and match the observation underlying the approval (excluding poll time and
ordering of identified collections). Current feature evidence must reference
that observation. The automatic approval's semantic input digest is recomputed;
changed inputs, stale evidence, missing policy, contradictory/malformed OPA
responses and DB/audit failures cannot produce a forwarding permission.

Evaluation receipts use `access_decisions`, action `publish_preflight`, subject
`appsmith-proxy`, role `service`, version `appsmith-publish-preflight-v1`.
They are not authenticated-user records or deployment completion receipts.
CTRL-06 remains not_assessed. The existing workload grants suffice; no migration
or Vault credential changes are necessary.

## Validation and rollout

- Python tests exercise approval, denial, stale/changed evidence, incomplete
  inputs, ambiguous identity, audit failures and invalid OPA responses.
- OPA 1.19.0 runs the original 15 tests plus six publish policy tests.
- Caddy 2.11.4 boundary tests use isolated upstream fixtures. They check that
  denials/errors do not contact upstream, spoofed headers and encoded paths do
  not bypass the gate, and native credentials/body and native 401 survive forwarding.
- The installer validates the Caddy config and OPA policies before restarting
  anything, saves rollback images, rebuilds only the two API replicas, restarts
  the existing OPA container, and tests both replicas before enabling the proxy.
- The proxy uses the observed Caddy digest; Appsmith/OPA containers are not
  recreated from their newer Compose tags. No application state is rewritten.
- An unauthenticated request for a nonexistent application tests guard routing
  without publishing the LO1 probe. Live authenticated denial remains pending.

Run `python3 scripts/rollout-lo2-publish-guard.py` after the targeted Python tests.
Installation evidence and a rollback command are saved under the Git directory.
On installation failure the script attempts to restore the prior API/proxy images.
The prior proxy has no deployment guard; rollback restores that baseline.
The source Compose file still contains the guard, so a later normal `compose up`
can re-enable it; follow the saved rollback command until the problem is resolved.

## Remaining assurance limits

1. This is a preflight over observed metadata, not an atomic approval of the live
   Appsmith draft. An edit between discovery and publish is not prevented. A
   revision-bound release mechanism or synchronous mutation control is needed
   before claiming current-configuration enforcement.
2. Git/import/clone/restore and other publication or configuration paths have not
   been intercepted or acceptance-tested. Git branch publish requests are denied.
3. Human-reviewed approvals are not accepted by this first gate. Only matching
   automatic approvals qualify. Do not change an application's risk, registration
   or governed classification just to obtain an allowed test.
4. Local Docker administrators and trusted internal workloads are outside the
   browser proxy boundary; no published Appsmith port alone is not proof of
   universal interception. Control-plane authentication is a separate limitation.
5. This change establishes no new DLP, model-accuracy or compliance certification
   claim. The LO1 application's genuine review/scan findings remain visible.

Next acceptance: retain the authenticated native Deploy denial, verify a legitimate
allowed fixture and native permission denial, then close the draft-change race and
alternate-operation coverage before reassessing LO2.1 completeness.

## Native denial response correction

The reported installation passed 59 Python checks and 21 OPA checks. A subsequent
native Deploy attempt produced denial receipt
`df805eb4-8e04-4be5-9c94-b027b5859eb6` at `2026-11-17T12:41:18.787204+00:00`.
The browser also displayed `undefined is not an object` while reading
`responseMeta.error`. This is evidence of a recorded preflight denial and a
response compatibility defect, not completed native acceptance.

The exact deployed Appsmith revision's `handleBadRequestError` reads
`error.response.data.responseMeta.error.code` even for HTTP 403/503, before
checking for a 400 status. Its `ResponseDTO` provides `responseMeta`, `data`, and
`errorDisplay`; `validateResponse` uses `responseMeta.success` and the error
message. The guard now supplies that envelope for policy denial, malformed
requests, and unavailable governance checks. Existing machine-readable reasons,
receipt fields, cache directives and receipt headers remain present.

HTTP 403/503 remain non-success statuses, so Caddy still refuses forwarding.
Success remains HTTP 204. Routing, policy, approval requirements and database
receipt generation are unchanged. This correction requires rebuilding only the
two governance API replicas. Run `scripts/rollout-lo2-publish-response.py` after
the tests. It retains the current guarded API images for rollback and checks
each replacement before proceeding. Do not rerun the initial rollout script or
restore the original unguarded proxy. Its replica probes create denial receipts
and must not be misrepresented as authenticated native Deploy evidence.

Regression checks exercise all guard error branches and pass the actual serialized
API denial/unavailable bodies through Caddy 2.11.4 to verify preserved JSON and
zero publish requests to the fixture upstream. A live browser retest is still
required. The guard's conservative encoded-path rejection and alternate publish
paths remain outside this correction.

Reference source at revision `d847cf495020767bfe53f4ead37a24513a51d7d4`:
- `app/client/src/api/interceptors/response/failureHandlers/handleBadRequestError.ts`
- `app/client/src/sagas/ErrorSagas.tsx`
- `app/server/appsmith-server/src/main/java/com/appsmith/server/dtos/ResponseDTO.java`
- `app/server/appsmith-server/src/main/java/com/appsmith/server/dtos/ResponseMetaDTO.java`
