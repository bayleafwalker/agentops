# Retention and whole-application recovery

Operator-approved programme, 24 October 2026. Target: approximately 30 hours of useful autonomous implementation after launch, with review and deployment on the operator return.

Read [the long-running worker contract](../../long-running-worker.md). Explicitly use GPT-6 Luna with high reasoning when the runtime supports it. You own discovery, planning, test/interface definition and backlog realignment within this programme. This authority supersedes generic bounded-build or coordinator-only planning instructions for this run. Do not stop after the first increment.

## Work and source reconciliation

Work references: agentops#2828. These are existing work references, not new terminal decisions.

Source anchors, to reconcile against canonical source at launch:

- appservice canonical main refreshed at dispatch; accepted retention source baseline 34f7624cee9bd89be7b5810ccec4aec219870755

Every source anchor is distinct from deployed state. A pending parent may already contain accepted source children. Preserve accepted work and historical evidence.

## Source areas

- appservice recovery/retention source tools, synthetic fixtures, guards and runbooks
- agentops host evidence lifecycle where needed

## Ordered implementation queue

1. Investigate supported upstream input-disable/replay-barrier capabilities using pinned primary source and document exact admission/queued/in-flight flush/restart scope. Do not guess an environment flag or fork vendor ingestion.

2. If a supported contract exists, implement the smallest supported integration plus omission, admitted-positive and forbidden-replay regression tests in a disposable synthetic deployment.

3. Complete the all-entrypoint inventory and reusable quarantine/readiness diagnostics, whole-app restore verification, timestamp/TTL and retained-copy checks. Historical deletion completeness and publication permission remain separate.

4. Build reusable fixtures proving exact original-style shared batch and expired replay behavior, true consumption and both physical/API observations without private datasets. A queue acknowledgement or cleanup after replay is not prevention.

5. Continue host evidence cleanup/opt-in and backup expiry/recovery regression tooling while unsupported barrier questions are isolated. No new authoritative deletion ledger or all-copy erasure claim.

6. The operator deferred review of retained isolated state to their return on 2026-10-25. Cloud sessions never access or delete that state; quarantine and stopped serving components remain required.

## Verification

- Use synthetic owned disposable resources; no restored customer/workstation dataset or production credentials.
- Run positive consumption, barrier omission, queued-before-activation, in-flight flush and restart cases where supported.
- Run affected source/guard tests and mise run validate; keep unsupported upstream capability a precise blocker rather than fabricated acceptance.

Inspect current pinned source before selecting an exact focused test invocation. Install only from the environment-approved pinned dependency setup. Missing tools, unexecuted gates and intentional optional skips remain explicit. Define adversarial cases before relying on a new guard, and watch the wrong behavior fail.

## Collaboration and handback

Use a dedicated candidate branch and exact dependency commits. Contract foundation is the shared generator owner; requests/continuation owns the request lifecycle; Cloud recovery owns schema-coordinate administration; Cloud product owns the TUI/web projections; telemetry owns optional metadata exporters. The integration session alone resolves overlapping locks/manifests. Continue independent items while a sibling dependency is unavailable.

Checkpoint coherent commits, verification and next work at each increment. Use a persistent native goal; verify automatic continuation and remote environment rather than assuming either. In the final three hours prioritize integration repair and handback. Stop substantive work when all admitted useful scope is done, the review deadline arrives or no meaningful independent work remains. No idle loops.

No production/main merge, promotion, deployment, protected-service mutation, credential copying, raw private handoff/capture/dataset transfer or terminal owner acceptance is authorized. Use task-specific source and synthetic fixtures. Report candidate commits/hashes, exact checks, dependency pins, remaining defects and the workstation actions needed to assess and deploy.
