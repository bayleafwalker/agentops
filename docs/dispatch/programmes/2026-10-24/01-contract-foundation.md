# Contract foundation

Operator-approved programme, 24 October 2026. Target: approximately 30 hours of useful autonomous implementation after launch, with review and deployment on the operator return.

Read [the long-running worker contract](../../long-running-worker.md). Explicitly use GPT-6 Luna with high reasoning when the runtime supports it. You own discovery, planning, test/interface definition and backlog realignment within this programme. This authority supersedes generic bounded-build or coordinator-only planning instructions for this run. Do not stop after the first increment.

## Work and source reconciliation

Work references: vuoro#2734, vuoro#2735, agentops#2736. These are existing work references, not new terminal decisions.

Source anchors, to reconcile against canonical source at launch:

- vuoro:61df7c27217b1e2818737b19481ebe07e4c9f6bd

Every source anchor is distinct from deployed state. A pending parent may already contain accepted source children. Preserve accepted work and historical evidence.

## Source areas

- vuoro/packages/vuoro-contracts
- vuoro/tools/contracts
- vuoro/scripts/contracts
- vuoro/packages/vuoro-client and vuoro-service generated-contract consumer seams

## Ordered implementation queue

1. Qualify the existing namespace repair, including deterministic unique package names derived from the full exact contract ID, relative imports, and multi-contract installed consumers. Reconcile available candidate source before reimplementing it.

2. Finish portable namespace tests and CI: retain the original 257 production cases, add the separate 26-case gate, and prove meaningful released-source failures. Published runtime 0.1.0 remains immutable.

3. Implement supported installed SDK/resource-root closure with ordinary bytecode enabled, exact inventory verification, authenticated package data and bounded extraction. No global sys.path alias, duplicate SDK or silently ignored cache files.

4. Complete clean regeneration, cross-language semantic vectors, offline wheel consumption and compatibility tests; provide pinned provisional candidates to Cloud and Sovite.

5. Continue domain-package ownership and generated-client migrations under EC-02/03 when the foundation gates pass; preserve one semantic source and owner boundaries.

## Verification

- Run the existing exact production toolchain workflow commands, including pinned compiler/generator/executable admission and original 257-case zero-skip gate.
- Run the separate 26-case portable namespace gate after implementing and independently verifying it.
- Build the wheel and test ordinary installation away from the checkout, integrity tampering, multiple contracts and cross-language transport parity.

Inspect current pinned source before selecting an exact focused test invocation. Install only from the environment-approved pinned dependency setup. Missing tools, unexecuted gates and intentional optional skips remain explicit. Define adversarial cases before relying on a new guard, and watch the wrong behavior fail.

## Collaboration and handback

Use a dedicated candidate branch and exact dependency commits. Contract foundation is the shared generator owner; requests/continuation owns the request lifecycle; Cloud recovery owns schema-coordinate administration; Cloud product owns the TUI/web projections; telemetry owns optional metadata exporters. The integration session alone resolves overlapping locks/manifests. Continue independent items while a sibling dependency is unavailable.

Checkpoint coherent commits, verification and next work at each increment. Use a persistent native goal; verify automatic continuation and remote environment rather than assuming either. In the final three hours prioritize integration repair and handback. Stop substantive work when all admitted useful scope is done, the review deadline arrives or no meaningful independent work remains. No idle loops.

No production/main merge, promotion, deployment, protected-service mutation, credential copying, raw private handoff/capture/dataset transfer or terminal owner acceptance is authorized. Use task-specific source and synthetic fixtures. Report candidate commits/hashes, exact checks, dependency pins, remaining defects and the workstation actions needed to assess and deploy.
