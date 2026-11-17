# CR-002: LO1 Appsmith MVP acceptance

Verdict: FULL for LO1.1, LO1.2 and LO1.3 within the Appsmith reference-platform
MVP demonstrated here. This is project acceptance, not external certification
or full CR-002/all-objectives acceptance. Evidence was supplied from the live
Mac deployment and reconciled with the implementation and regression results.

| Requirement | Supporting evidence |
|---|---|
| LO1.1: ML discovery of unauthorized applications | The independently collected, unregistered application became anomalous and a shadow IT candidate; matching persisted configuration-snapshot assessment `82e3ba19-8f93-493f-ba5b-9f1c8e476c37`. |
| LO1.2: Automated inventory, classification and risk | Inventory was populated automatically. An authenticated owner declaration enabled automatic advisory classification; corrected source evidence automatically produced assessment `3f80cb68-8f0e-4162-83dd-c9a39d4fdde0`. Risk was assessed as 60/high. |
| LO1.3: Continuous monitoring of new applications | Application absent from the 18-record baseline at 2026-11-16T08:30:33.874297+00:00; first discovered at 2026-11-16T08:31:30.703710+00:00; continued observations through 2026-11-17T02:08:37.908845+00:00. |

Application: `20fe2957-f769-4faa-a23a-1fa28584c359`; Appsmith identity: `6afabf4265d61d1e1b332ac1`.
The 56.83-second interval starts at baseline capture,
not the exact creation time. Scheduled polling detected the newly created
Appsmith application and subsequent configuration changes. Publication-event
telemetry and execution-time traffic were not demonstrated by this evidence.

## Verified repair and assessment behavior

Both the nested datasource-storage extraction and action-reference join were
deployed. User runtime regression: 117 passed. Discovery was healthy after
recreation. Local broader regression: 492 passed, 106 skipped, 3 subtests passed;
skipped integration tests are not claimed as passed runtime checks.

The current receipt reports six connectors, six external hosts and five
unapproved integrations. The latest classification has no unresolved-destination
warning. The historical assessment retains its original warning for auditability.
The suggestion remains public at 0.5394 confidence with human review required;
governed classification remains unknown. These advisory/authority boundaries
are functioning safeguards, not an unperformed automatic-classification step.

## Demonstrated scope and limits

- Live Appsmith reference platform and configuration observations; broader
  platform discovery is not claimed by this verdict.
- Owner-provided business purpose and schema context remain explicitly
  attested inputs. Their semantic truth is not inferred from technical metadata.
- The controlled anomaly demonstration and synthetic model evaluation do not
  establish production accuracy, universal detection, or an uptime SLA.
- Missing full-day telemetry remains unknown; the snapshot model uses four
  observed counts and does not claim temporal behavior analysis.
- DLP enforcement, deployment blocking, governed-label approval and other
  learning objectives retain their own acceptance requirements.

## Evidence and source correspondence

Portable receipts are in `cr002-lo1-appsmith/` beside this document. The baseline
summary omits unrelated inventory; source hashes identify the original local
receipts. Original evidence remains under `.git/cr002-connector-storage-proof/`
and `.git/cr002-lo1-connector-pNRZfl/` on the operator's machine.

Deployed discovery image reported by the operator:
`sha256:77695d0b00ab6236ac925db4c042474d207d1756b0696bfccbf8ef92f0333d5b`.
Pre-rollout image tag: `lcnc-discovery-rollback:20261117T020623Z`.
The source baseline was `c05a35b` plus the datasource-storage and action-reference
fixes. The commit containing this record checkpoints those incremental fixes.
This dated acceptance record supersedes earlier LO1 pending checkpoint wording
for the stated scope; historical records remain preserved.
