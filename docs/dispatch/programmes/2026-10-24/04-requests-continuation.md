# Durable requests and continuation

Operator-approved programme, 24 October 2026. Target: approximately 30 hours of useful autonomous implementation after launch, with review and deployment on the operator return.

Read [the long-running worker contract](../../long-running-worker.md). Explicitly use GPT-6 Luna with high reasoning when the runtime supports it. You own discovery, planning, test/interface definition and backlog realignment within this programme. This authority supersedes generic bounded-build or coordinator-only planning instructions for this run. Do not stop after the first increment.

## Work and source reconciliation

Work references: vuoro#2725, agentops#2726, vuoro#2728, agentops#2730, agentops#2554, agentops#2623, agentops#2638. These are existing work references, not new terminal decisions.

Source anchors, to reconcile against canonical source at launch:

- vuoro:61df7c27217b1e2818737b19481ebe07e4c9f6bd
- sprintctl:b76bd692060ca9b5f53f78d07ee187918a5d265d
- agentops:d38a49fb707c5b17f2b2f0eff7360abbb77ecd5a

Every source anchor is distinct from deployed state. A pending parent may already contain accepted source children. Preserve accepted work and historical evidence.

## Source areas

- vuoro owner request/continuation contracts and transport
- sprintctl owner provider implementation only where current contracts place state
- agentops native publishing/continuation integration and generated tools

## Ordered implementation queue

1. Reconcile OA-01 code and settle candidate storage responsibility against existing owner contracts. Reuse the owner state machine; do not create another work-status authority or resurrect retired runtimes.

2. Implement stable request identity, typed request kinds, revision-safe updates, multiple dependants, full procedures, freshness, withdrawal and supersession. Viewing/copying is not authorization and dead sessions do not resolve requests.

3. Implement Claude/Codex publication and outage reconciliation using qualified native interfaces; unsupported runtime modes are explicit. Exclude raw transcript ingestion and secret values.

4. Implement performed-report verification versus human attestation, partial/uncertain outcomes, idempotent resolution delivery and continuation-ready fallback when native wake is unavailable.

5. Implement bounded current-authorized continuation delta and ordinary work-link consumers; preserve work identity while changing attempts and refuse stale/revoked access.

6. Qualify dead requester, shared request, duplicate/lost delivery, changed target, false performed report and cross-session successor cases with real disposable owner services. Prepare the human pilot without claiming it happened.

## Verification

- Run focused vuoro-client/service/owner tests and the repository boundary gate.
- Run focused sprintctl tests with disposable PostgreSQL and existing required backend matrices when owner changes require it.
- python -m unittest discover -s scripts/tests -p test_model_routing.py for routing-related joins; run the actual affected native integration and hook suites from source.

Inspect current pinned source before selecting an exact focused test invocation. Install only from the environment-approved pinned dependency setup. Missing tools, unexecuted gates and intentional optional skips remain explicit. Define adversarial cases before relying on a new guard, and watch the wrong behavior fail.

## Collaboration and handback

Use a dedicated candidate branch and exact dependency commits. Contract foundation is the shared generator owner; requests/continuation owns the request lifecycle; Cloud recovery owns schema-coordinate administration; Cloud product owns the TUI/web projections; telemetry owns optional metadata exporters. The integration session alone resolves overlapping locks/manifests. Continue independent items while a sibling dependency is unavailable.

Checkpoint coherent commits, verification and next work at each increment. Use a persistent native goal; verify automatic continuation and remote environment rather than assuming either. In the final three hours prioritize integration repair and handback. Stop substantive work when all admitted useful scope is done, the review deadline arrives or no meaningful independent work remains. No idle loops.

No production/main merge, promotion, deployment, protected-service mutation, credential copying, raw private handoff/capture/dataset transfer or terminal owner acceptance is authorized. Use task-specific source and synthetic fixtures. Report candidate commits/hashes, exact checks, dependency pins, remaining defects and the workstation actions needed to assess and deploy.
