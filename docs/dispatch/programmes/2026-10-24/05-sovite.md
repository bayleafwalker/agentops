# Sovite remote execution and hosting

Operator-approved programme, 24 October 2026. Target: approximately 30 hours of useful autonomous implementation after launch, with review and deployment on the operator return.

Read [the long-running worker contract](../../long-running-worker.md). Explicitly use GPT-6 Luna with high reasoning when the runtime supports it. You own discovery, planning, test/interface definition and backlog realignment within this programme. This authority supersedes generic bounded-build or coordinator-only planning instructions for this run. Do not stop after the first increment.

## Work and source reconciliation

Work references: agentops#2850, agentops#2849, vuoro-cloud distribution CL-K06. These are existing work references, not new terminal decisions.

Source anchors, to reconcile against canonical source at launch:

- sovite:b712d5f69a62e618e66acb6a6beae9dad5e25e56

Every source anchor is distinct from deployed state. A pending parent may already contain accepted source children. Preserve accepted work and historical evidence.

## Source areas

- sovite owner execution API, control/worker/helper/SDK/CLI and tests
- sovite generated contract and package assets
- sovite hosting/chart composition disabled until workstation acceptance
- vuoro pinned Sovite adapter seam after its owner candidate qualifies

## Ordered implementation queue

1. Complete and freeze F2 request/status contracts and real owner tests; ordinary planning, interface refinement and implementation are authorized within accepted R4/F2 semantics.

2. Implement fenced execution pull/start/renew/status/handback/complete/lookup APIs, preserving original owner responses, transaction boundaries and operation-journal identity. Validate external profile/caps before owner effects, including idle/replay.

3. Implement authenticated package assets and ordinary installed validation, retaining core Python>=3.11 and feature gating>=3.12 before routes/sessions/effects. Consume the shared namespace/resource-root repair rather than inventing a duplicate.

4. Remove control database/operator/caller credentials from worker/native harness composition; implement scoped control API clients, capability refresh/revocation and output-storage boundaries.

5. Continue remote helper enrollment/renewal/rotation/revocation, lifecycle reconciliation, demand and remote-host qualification tooling in accepted R5-R8 order. No transparent replay, model fallback or binding substitution.

6. Continue S4-S6 role separation, retention/recovery and disabled hosted composition, then pinned Vuoro receipt-adapter integration. Provide fixtures for two workspace isolation; no live migration, chart rollout, edge enablement or qualification claim.

## Verification

- Use the pinned source CI commands with disposable SQLite and PostgreSQL and required zero-skip cases.
- Run actual HTTP/owner races, response-loss, revocation, expired fence, artifact-integrity and cold installed-wheel tests.
- Render and validate charts offline; test absence of broad control credentials in worker/native/gateway outputs.

Inspect current pinned source before selecting an exact focused test invocation. Install only from the environment-approved pinned dependency setup. Missing tools, unexecuted gates and intentional optional skips remain explicit. Define adversarial cases before relying on a new guard, and watch the wrong behavior fail.

## Collaboration and handback

Use a dedicated candidate branch and exact dependency commits. Contract foundation is the shared generator owner; requests/continuation owns the request lifecycle; Cloud recovery owns schema-coordinate administration; Cloud product owns the TUI/web projections; telemetry owns optional metadata exporters. The integration session alone resolves overlapping locks/manifests. Continue independent items while a sibling dependency is unavailable.

Checkpoint coherent commits, verification and next work at each increment. Use a persistent native goal; verify automatic continuation and remote environment rather than assuming either. In the final three hours prioritize integration repair and handback. Stop substantive work when all admitted useful scope is done, the review deadline arrives or no meaningful independent work remains. No idle loops.

No production/main merge, promotion, deployment, protected-service mutation, credential copying, raw private handoff/capture/dataset transfer or terminal owner acceptance is authorized. Use task-specific source and synthetic fixtures. Report candidate commits/hashes, exact checks, dependency pins, remaining defects and the workstation actions needed to assess and deploy.
