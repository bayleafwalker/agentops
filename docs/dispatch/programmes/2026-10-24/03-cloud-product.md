# Cloud product, TUI and distribution

Operator-approved programme, 24 October 2026. Target: approximately 30 hours of useful autonomous implementation after launch, with review and deployment on the operator return.

Read [the long-running worker contract](../../long-running-worker.md). Explicitly use GPT-6 Luna with high reasoning when the runtime supports it. You own discovery, planning, test/interface definition and backlog realignment within this programme. This authority supersedes generic bounded-build or coordinator-only planning instructions for this run. Do not stop after the first increment.

## Work and source reconciliation

Work references: vuoro-cloud#2727, vuoro-cloud#2729, vuoro-cloud#2682, vuoro-cloud#2683, vuoro-cloud#2684, vuoro-cloud#2741, agentops#2626, agentops#2627, agentops#2628, agentops#2629, agentops#2632, agentops#2634, agentops#2636. These are existing work references, not new terminal decisions.

Source anchors, to reconcile against canonical source at launch:

- vuoro-cloud:a237bbdade2528c6769af666bc84c25e3caa1ca3

Every source anchor is distinct from deployed state. A pending parent may already contain accepted source children. Preserve accepted work and historical evidence.

## Source areas

- vuoro-cloud existing CLI/TUI/web/API composition and generated UI clients
- vuoro-cloud tests, distribution packaging and owner runbooks

## Ordered implementation queue

1. Reconcile source against sprint569 and the related agentops product backlog before selecting increments. Do not rebuild already delivered source because parent status remains pending.

2. Implement source-backed READY/blocker explanations, effective-access explanations using the actual authorization checks, exception projection, coverage denominators and release-impact previews. Missing observations remain unknown.

3. Implement the operator-action TUI over the request owner candidate, with complete versioned procedures, freshness, preserved progress, entitlements and explicit report-performed versus verified outcomes. Work on independent product increments while the request contract is unavailable.

4. Once TUI/request/continuation prerequisites qualify, implement the shared web view and bounded notifications with quiet unchanged requests, revision agreement, defer/change conditions, revoked-access negatives and explicit partial coverage.

5. Build named-client connection guidance and a first-result journey against disposable owner services; gate capability copy on the actual shipped contract. No OAuth registration-policy change or public directory submission.

6. Continue supported versioned composition, install/upgrade/export/rollback tooling, generated hosted-edge migration and isolated tenant-leakage fixtures. Expanded cross-organization authority remains disabled and proposed design must be labeled.

## Verification

- nix develop --command make check-fast
- nix develop --command make test-integration using disposable services
- Use the existing web build/test commands discovered in the pinned source; add keyboard, restart, revision, browser/proxy, authorization-expiry and two-tenant negative coverage.

Inspect current pinned source before selecting an exact focused test invocation. Install only from the environment-approved pinned dependency setup. Missing tools, unexecuted gates and intentional optional skips remain explicit. Define adversarial cases before relying on a new guard, and watch the wrong behavior fail.

## Collaboration and handback

Use a dedicated candidate branch and exact dependency commits. Contract foundation is the shared generator owner; requests/continuation owns the request lifecycle; Cloud recovery owns schema-coordinate administration; Cloud product owns the TUI/web projections; telemetry owns optional metadata exporters. The integration session alone resolves overlapping locks/manifests. Continue independent items while a sibling dependency is unavailable.

Checkpoint coherent commits, verification and next work at each increment. Use a persistent native goal; verify automatic continuation and remote environment rather than assuming either. In the final three hours prioritize integration repair and handback. Stop substantive work when all admitted useful scope is done, the review deadline arrives or no meaningful independent work remains. No idle loops.

No production/main merge, promotion, deployment, protected-service mutation, credential copying, raw private handoff/capture/dataset transfer or terminal owner acceptance is authorized. Use task-specific source and synthetic fixtures. Report candidate commits/hashes, exact checks, dependency pins, remaining defects and the workstation actions needed to assess and deploy.
