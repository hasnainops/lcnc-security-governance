# CR-002 — Initial configuration assessment and independent feature persistence

Status: implementation and local verification; live acceptance pending.

The previous route persisted no counts until all five historical-model inputs
were available. It also used witnessed partial-history changes as the existing
model's changes_last_24h feature in a diagnostic. The route now persists each
verified count independently and uses a separately trained configuration-only
IsolationForest for initial assessment. It no longer invokes that partial-history
diagnostic. Existing diagnostic history is preserved, not relabelled.

The new model has exactly four features: external_integration_count,
unapproved_integration_count, connector_count, external_domain_count.
There is no history input, imputed zero, owner inference, or exposure inference.
Its scope is configuration anomaly detection, not temporal behaviour detection.
The original model and endpoint remain for fully evidenced historical inputs.
A full-history feature vector takes priority over the initial snapshot path.

Independent persistence clears unsupported current counts to NULL and invalidates
anomaly/risk/governance results when their inputs change. The latest-observation
check and application-row lock prevent delayed requests overwriting newer facts.
The snapshot assessor rereads fresh source evidence under the same row lock,
validates the model identity and result, and atomically persists history/current
state. Concurrent identical requests do not create duplicate assessments. A new
model digest triggers reassessment. Inference failure remains retryable on the
next observation; no invented assessment is persisted. No schema migration.

Evidence is retained in ml_assessments: analysis_type=configuration-snapshot,
four actual features, model version/digest, source observation ID/time, input
hash and temporal_history_evaluated=false. The current anomaly status is assessed
for this stated model scope. shadow_it_candidate requires an anomalous result AND
unregistered Appsmith status. It is neither a business approval nor permission to
transfer data. Human review and deterministic governance remain authoritative.

## Model compatibility and evaluation

The Docker build trains the new artifact using the existing synthetic dataset,
with a fixed seed (42), 200 trees, contamination 0.01, and a stratified 70/30 split.
Training uses only normal rows in the training partition (210 rows). Held-out
105-row evaluation: confusion matrix [[87,3],[0,15]], precision 0.8333, recall 1.0.
This is synthetic validation, not production accuracy; original labels may depend
on features omitted by this model. It cannot detect anomalies expressed solely
through change frequency, owner context, credential use or internet exposure.
Existing model artifacts are not rewritten. The new artifact is trained with the
same installed sklearn version used for inference inside the image.

## Verification and boundaries

Real PostgreSQL regression tests cover independently saved zeros with unknown
history, incomplete evidence invalidation/recovery, chronology/freshness guards,
strict count validation, first-observation inference, concurrent replicas,
model changes, rejected upstream output, retry, the production ingestion route,
and prevention of downgrading full-history evidence. ML tests invoke the real
snapshot model and reject historical or invalid input fields.

Local verification uses PostgreSQL 16.2/Python 3.12. The provided Docker fixture
runs the same database tests on PostgreSQL 18.4/Python 3.13 in the user's checkout.
Some unchanged supporting files absent from the uploaded archive were supplied
from the earlier checkout solely to run the broader regression suite.

This does not resolve all LO1 acceptance gaps. Nonempty connector collections
still require complete identities and server-derived destination trust; the
current route does not supply the latter. Those remain pending, not fabricated.
The existing periodic collector is polling, not instantaneous event ingestion.
Runtime verification must demonstrate a new app absent from a correctly timed
baseline, its initial snapshot, classification, risk and human-review routing.
Collection outages and stale display behaviour remain explicit acceptance work.

## Rollout and rollback

Apply against the uploaded source after git apply --check. Run root tests and
the dedicated LO1 PostgreSQL test project. Build ml-analytics (which trains the
new model), then the API images. Preserve running image IDs as rollback tags.
Deploy only ml-analytics and the two APIs using --no-deps. Discovery continues
using its existing ingestion route; no Vault reset or database migration.

On rollback, restore the saved API images first, then the saved ML image.
Historical snapshot rows remain valid records of the model that produced them;
do not delete or relabel them. New-version current assessments must be treated
as historical if rolling back to consumers without the snapshot scope support.
