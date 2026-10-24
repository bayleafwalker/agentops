# Cloud recovery and generated administration

Operator-approved programme, 24 October 2026. Target: approximately 30 hours of useful autonomous implementation after launch, with review and deployment on the operator return.

Read [the long-running worker contract](../../long-running-worker.md). Explicitly use GPT-6 Luna with high reasoning when the runtime supports it. You own discovery, planning, test/interface definition and backlog realignment within this programme. This authority supersedes generic bounded-build or coordinator-only planning instructions for this run. Do not stop after the first increment.

## Work and source reconciliation

Work references: agentops#2599, agentops#2863, agentops#2646. These are existing work references, not new terminal decisions.

Source anchors, to reconcile against canonical source at launch:

- vuoro-cloud:a237bbdade2528c6769af666bc84c25e3caa1ca3
- vuoro-cloud:PR297 head 937afc7de18433de58d60fa1ace03aa2617beacb

Every source anchor is distinct from deployed state. A pending parent may already contain accepted source children. Preserve accepted work and historical evidence.

## Source areas

- vuoro-cloud/src/vuoro_cloud generated schema-coordinate API, loader, operation reader and CLI seams
- vuoro-cloud/contracts and generated package assets
- vuoro-cloud/scripts and tests for disposable source/recovery/runtime qualification

## Ordered implementation queue

1. Reconcile PR297 candidate and current canonical source; preserve the original collector refusal and strict owner/image/UID checks. Prepare source only; do not merge or rerun field observers.

2. After a qualified foundation candidate exists, implement the three generated schema-coordinate read/reconcile/operation-lookup routes and typed CLI adapter. Preserve lossless signed integers, exact C0/Q15 bytes, current owner CAS and existing authentication lifecycle.

3. Qualify restricted-role disposable PostgreSQL, real HTTP/native clients, transaction visibility, response loss after commit, scoped lookup, concurrent CAS, audit rollback and refusal bookkeeping. Unknown results never trigger automatic mutation replay.

4. Complete disposable backup/source/clone identity and restore-verification tooling needed by 2599, retaining field freshness and source-owner observations as workstation gates.

5. Continue recovery diagnostics, migration compatibility and staged hold/resume source tests. Produce exact field action and rollback packets without touching live tenants.

## Verification

- nix develop --command make check-fast
- nix develop --command make test-integration using isolated owned PostgreSQL only
- Run generated-contract regeneration and installed-consumer checks plus targeted C0/Q/role/catalog/collector regressions.

Inspect current pinned source before selecting an exact focused test invocation. Install only from the environment-approved pinned dependency setup. Missing tools, unexecuted gates and intentional optional skips remain explicit. Define adversarial cases before relying on a new guard, and watch the wrong behavior fail.

## Collaboration and handback

Use a dedicated candidate branch and exact dependency commits. Contract foundation is the shared generator owner; requests/continuation owns the request lifecycle; Cloud recovery owns schema-coordinate administration; Cloud product owns the TUI/web projections; telemetry owns optional metadata exporters. The integration session alone resolves overlapping locks/manifests. Continue independent items while a sibling dependency is unavailable.

Checkpoint coherent commits, verification and next work at each increment. Use a persistent native goal; verify automatic continuation and remote environment rather than assuming either. In the final three hours prioritize integration repair and handback. Stop substantive work when all admitted useful scope is done, the review deadline arrives or no meaningful independent work remains. No idle loops.

No production/main merge, promotion, deployment, protected-service mutation, credential copying, raw private handoff/capture/dataset transfer or terminal owner acceptance is authorized. Use task-specific source and synthetic fixtures. Report candidate commits/hashes, exact checks, dependency pins, remaining defects and the workstation actions needed to assess and deploy.
