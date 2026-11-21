# CR-002 — Appsmith v2.2 route boundary for LO2.1

Status: source inspection and negative runtime proof; no universal publish
enforcement or positive live fixture accepted.

## Pinned source and installed boundary

The observed Appsmith image declares revision
`d847cf495020767bfe53f4ead37a24513a51d7d4`. The pinned
`ApplicationControllerCE` maps `Url.APPLICATION_URL` to application operations.
The installed Caddy guard calls `publish_target` on every request. It evaluates
policy only for the canonical `POST /api/v1/applications/publish/{24-hex-id}`;
all other canonical paths get a 204 preflight and are forwarded to Appsmith.
The authenticated negative publish returned 403 with a matching persisted
decision receipt, as documented in
`compliance/evidence/CR-002-LO2-Appsmith-publish-denial-checkpoint.md`.

| Pinned controller operation | Guard behavior | Assurance interpretation |
|---|---|---|
| `POST /applications/publish/{branchedApplicationId}` | Policy preflight for the canonical 24-hex ID; unsupported branch, query or path format denied | Authenticated denial verified for the review-pending LO1 app; no live allow verified |
| `POST /applications` | Preflight currently returns 204 | Pinned `createApplication` calls `publishWithoutPermissionChecks` after creating the default page. Proposed guard change blocks this route; creating apps through the proxy then stops until native creation is governed. |
| `POST /applications/clone/{id}` | Preflight currently returns 204 | Pinned `cloneApplication` calls `publishWithoutPermissionChecks` for the copy. Proposed guard change blocks this route; cloning through the proxy then stops. |
| `PUT /applications/{branchedApplicationId}` | Preflight returns 204 | Changes application metadata; no evidence that this operation itself publishes |
| `PUT /applications/{id}/page/{pageId}/makeDefault` and `/reorder` | Preflight returns 204 | Changes draft/page configuration; may invalidate earlier observed approval |
| `POST /applications/snapshot/{id}/restore` | Preflight returns 204 | Restores application state; no evidence that restore itself publishes |
| `POST /applications/import/{workspaceId}` and `/import/partial/{workspaceId}/{id}` | Preflight returns 204 | Import can change app configuration; whether it reaches a published version requires separate source and runtime proof |
| `POST /applications/clone/{id}` and `POST /applications/{id}/fork/{workspaceId}` | Preflight returns 204 | Creates another application context; new IDs need independent discovery and policy evidence |

The table covers only the controller available for pinned inspection. Other
controllers, especially Git and any CI/CD routes, require separate version-pinned
source inventory. A path being forwarded is not proof of successful mutation or
of a publish bypass. The local OpenAPI probe returned HTML for `/v3/docs` and
`/v3/api-docs`; that probe does not establish endpoint absence.

The proposed create/clone blocks are a compatibility-breaking safeguard, not
an installed control. The pinned `ApplicationPageServiceCEImpl` invokes
`publishWithoutPermissionChecks` from both `createApplication` and the clone
flow. The guard patch blocks these POST requests before Appsmith receives them;
it does not authorize app creation, close other publication routes, or prove
the existing manual publish is revision-bound. Apply only with an approved
plan for creating applications and a rollback. Positive proxy fixtures are
synthetic and do not demonstrate a live governance-approved application.

## Revision binding needed before an allowed native publish

`check_publish` locks a governance database row, reads the latest Appsmith
discovery observation and compares it with the approval's observation. The
three-minute freshness test and observation digest are useful, but the lock is
not held by Appsmith's draft store. A draft edit can occur after discovery or
after proxy preflight, before `ApplicationPageService.publish` reads the draft.
An additional immediate read from Appsmith before forwarding still leaves the
same race.

The release boundary must enforce the approval against the **exact draft
revision consumed by publish**. The preferred implementation point is the
Appsmith publish transaction or a native revision precondition that Appsmith
checks atomically at publish. A proxy-only alternative would need to serialize
every relevant draft mutation and publication across all entry points for the
entire upstream operation, including Git/internal paths; the current Caddy
`forward_auth` does not provide that transaction. Do not add a timestamp-only
or read-then-forward check and describe it as race closure.

## Acceptance sequence

1. Complete version-pinned controller inventory and select the enforcement
   point for manual, Git and CI/CD publication. State which publication paths
   are disabled or out of the MVP boundary.
2. Test mutation between assessment and publish. Verify that the actual
   published draft revision is the approved one, or that publish is denied.
3. Run the isolated Caddy positive fixture: preflight 204 forwards one request
   and preserves native Appsmith success/permission responses. This is not a
   live governance approval.
4. Create a separate controlled Appsmith app. Complete genuine registration,
   authoritative classification, passing scan, nonanomalous assessment,
   required training and current governance approval. Verify the preflight and
   native app permission, publish once, and compare published state and audit
   receipt. The existing LO1 proof app remains review-pending and unchanged.

Read-only fixture screening found zero eligible applications out of 19; its
fields do not establish current source freshness, training or policy digests.
LO2.1 stays PARTIAL until the above acceptance evidence exists.
