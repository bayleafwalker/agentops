# Durable operator actions: request lifecycle and collated TUI/UI

Status: user-requested planning refinement, 18 October 2026. This specifies planned work; it does not claim an implemented or deployed inbox. Parent: **CL-K03 / vuoro-cloud#2682**, G12/F12, with G01 (attention), G04 (continuity), G06 (authority) and G07 (evidence). Governing direction: [two-year KAOS roadmap](2026-10-18-kaos-2028-roadmap.md).

## Outcome and current gap

The operator returns after an overnight absence, finds one current list of required actions, completes them without reconstructing conversations, and affected work resumes correctly or explicitly becomes ready for continuation—even if an original session has disappeared.

Sampled historical Claude and Codex sessions show three failure patterns: requests referring to commands earlier in chat; repeated blocked turns conflating interactive execution and explicit authorization; and runtime-policy failures repeatedly handed to the operator. These are historical observations, not a current pending-action census. Raw session logs, personal identifiers and privileged procedures are not published in this plan.

The September 27 [telemetry and operator-actions proposal](../2026-09-27-telemetry-audit-and-operator-actions.md) identified scratchpad/chat requests but is historical proposal context, not proof of adoption. Cloud's current `exception_inbox` source is a bounded projection without persistent acknowledgement, assignment or request lifecycle. CL-K02 / agentops#2626 retains that exception-projection scope. This refinement makes the separate CL-K03 product outcome concrete; it does not revive the retired cockpit, scheduler or ActionQ runner.

## KAOS refinement and responsibility

Achieve[OperatorCanActWithoutReconstructingConversation] AND Maintain[RequestMatchesCurrentNeed] AND Achieve[DependentWorkCanContinue] AND Avoid[RequestGrantsAuthority]. These AND-refine G12 with applicable G04/G06/G07 invariants from the parent roadmap.

| Obligation | Responsible agent/owner | Observable requirement |
|---|---|---|
| Raise only a verified need | Requesting agent and native harness | Explain why the operator is needed and link the checked blocker; routine authorized work stays with the agent |
| Preserve current request meaning | Canonical coordination owner, contracted through Vuoro | Stable identity, revision checks, session/work links, procedure versions, explicit lifecycle and deduplication |
| Perform/authorize/decide/provide information | Operator in the appropriate native or protected interface | Explicit response of the correct type; viewing, copying, deferring and silence are not grants |
| Verify outcome | Existing target/evidence owner or labeled human attester | Source observation or explicit attestation with scope, revision, time and uncertainty |
| Continue affected work | Work owner and qualified native runtime adapter | Only dependent work waits; retry-safe notification, checkpoint and successor context |
| Present and manage attention | Cloud-owned TUI/web composition | Shared request API, correct entitlements, freshness, actionable procedures and bounded notifications |

OA-01 must settle the exact canonical request storage owner against existing contracts before implementation. Cloud composes the views; it does not fork work acceptance or protected-effect semantics. UI-local state cannot be authoritative request state. Session status, request resolution, operation acceptance and work completion remain distinct.

## Required request packet

Every actionable request carries:

- Stable request ID, current revision, type (`perform`, `authorize`, `decide`, `provide-information`), required outcome and reason for operator involvement.
- Raising actor, owning work and all dependent work references; requesting session/runtime IDs, project, workspace and host, with appropriate source-session links.
- Exact execution context: host, directory, intended identity and target environment/resource; required inputs and their secure acquisition paths.
- Complete versioned procedure: ordered steps, exact commands or links where relevant, expected results, preconditions, verification, partial progress and failure/recovery instructions. A chat pointer alone is insufficient.
- Checked blocker and observation time, freshness conditions, relevant source/commit/artifact revisions, deadlines if real, and what would invalidate or remove the request.
- Completion basis, resolution evidence and continuation packet; assignment/defer/decline history where applicable.

Secret values and raw transcripts are excluded. Sensitive procedures remain subject to authorized owner reads and appropriate retention/export policy; aggregation must not leak another workspace's data. Request text is untrusted content, never a capability grant.

## Lifecycle and invariants

Use a durable lifecycle with explicit open, reported-performed/verification, resolved, withdrawn and superseded outcomes. Readiness, freshness, assignment and deferral are separate dimensions: expiry of an instruction does not prove the underlying need vanished.

1. Publish before yielding; retries return the same request. Coalesce only compatible requests with the same target, purpose and authority scope, preserving every dependant.
2. Update through revision checks. Material changes to commands, targets, payloads or authority invalidate prior acceptance of the old version; cosmetic edits do not manufacture repeated approvals.
3. Dead sessions retain their requests with freshness uncertain. An owner or successor may reconcile them. Silence or a missed heartbeat cannot resolve or withdraw an action.
4. Revalidate relevant preconditions before presenting instructions as ready. Changed commits, expired links and unavailable sources remain visible as requiring refresh.
5. Record step progress and uncertain outcomes; reconcile target state before retrying an operation that may already have taken effect. An in-progress ownership/claim mechanism must prevent concurrent operators from unknowingly repeating a step without acting as effect authority.
6. Operator reports of performance trigger verification when available. Physical work may resolve through explicitly labeled human attestation; unavailable verification remains unknown rather than failure or success.
7. Source-proven completion, deliberate withdrawal, supersession and decline are distinguishable. One requester withdrawing its need cannot erase other dependants.
8. Deferral names a time or change condition. Decline reaches affected work so the approach can be revised or stopped. Acknowledgement is neither authorization nor completion.
9. Resolution delivery is retryable and idempotent at the logical event level. It never replays the protected operation. Record each dependant's continuation acknowledgement separately.
10. If a runtime cannot wake/resume, expose `continuation ready` with a usable packet. A successor can continue without the original chat. Native runtimes retain scheduling and execution.

Local retry outboxes, if needed, are non-authoritative: show unsynced status, preserve identity, reconcile conflicts and never infer grants or owner completion while disconnected.

## TUI and UI experience

Start with a keyboard-first TUI over the shared lifecycle. Offer ready, needs-refresh, verifying, deferred and history views. Show action, context, affected work, real urgency and last check; allow filtering by project/workspace/host/runtime and grouping compatible actions by environment. Show collection coverage so an unavailable runtime does not appear to have no requests.

Selecting a row reveals the complete action packet and procedure with preserved step progress. Provide appropriate controls: open native approval flow, open instructions or target, copy a command, report performed, provide a decision/input, defer, decline and open source context. Opening or copying must not execute. Native approval requests remain native, bound to their actual scope; human execution is not equivalent to permission for agent execution. Do not add approval prompts for work already authorized.

Later web UI shares the same records and revisions. Notifications stay quiet for unchanged non-actionable state and surface new actionable requests, meaningful changes or real deadlines according to operator preferences. Bulk operations cannot collapse different authority scopes into blanket approval.

## Agent and runtime integration

Provide an explicit shared CLI/MCP request-publishing interface for native Claude and Codex consumers. Qualify local, hosted and other runtime modes individually; do not infer that an existing desktop session can be attached or awakened because a separate API exposes approvals/events. Codex's [documented app-server integration](https://developers.openai.com/blog/codex-as-a-platform) is one candidate surface, not qualification of every mode.

Agents publish complete requests, revise/withdraw them as source conditions change, checkpoint the dependent work, and continue independent work. When no useful work remains they yield; they do not spend repeated turns announcing the same blocker. Resolution supplies exact current request/work revisions and evidence to the native continuation mechanism.

Cheap/local models may propose requests extracted from historical transcripts. Candidates require reconciliation before becoming actionable; summarization cannot establish that a privileged command remains necessary or authorized. Discovery integrations must not scrape unsupported private endpoints or introduce a new runtime scheduler.

## Obstacles and qualification cases

| Obstacle | Required evidence |
|---|---|
| Instructions refer to earlier chat | Operator completes from request packet alone |
| Agent unnecessarily hands off permitted work | Checked reason is visible; routine escalation is not admitted as inherent operator authority |
| Session crashes or request updates race | Request survives; concurrent revision conflicts; takeover preserves dependants |
| Target changes after procedure publication | Old procedure is no longer ready; materially changed acceptance is not reused |
| Operator executes partially or reports success incorrectly | Progress survives; uncertain effects reconcile; false report does not become verified completion |
| Another session already completed the work | Source reconciliation resolves once and notifies all affected work without repeating effects |
| One requester cancels a shared need | Other dependants remain served |
| Delivery is lost/duplicated or native wake unavailable | Retry-safe delivery; explicit continuation-ready fallback and successor packet |
| Source/service is offline or tenant permission is revoked | Unknown/unsynced state is explicit; no missing-as-empty or unauthorized disclosure |
| Notification load grows | Unchanged requests stay quiet; measure attention and unnecessary/stale requests with denominators |

## Delivery and sequencing

The six registered slices below refine CL-K03; they are not six new top-level goal families. Inspect current implementations and existing items before each slice, specify interfaces/obstacles, implement or onboard, qualify success/refusal/recovery, release under existing authority, and verify use with support/upgrade/rollback/export documentation.

Move the first useful TUI workflow earlier than broad web/notification rollout. Contract discovery and a bounded pilot need not wait for a complete attention product. Full hosted exposure retains entitlement and source-owner gates; automated paid continuation retains applicable VU-K08 budget gates. AO-K02 supplies the baseline. CL-K02 exceptions can link to requests but are not the sole way sessions raise a request. No effect authority is expanded by this planning change.

### OA-01 — Define and implement durable operator-request contract

Owner: `vuoro`. Served item: **vuoro#2725**. Prerequisites: contract discovery.

Ratify canonical coordination ownership and API alongside existing work/effect owners; implement stable identity, revision-safe updates, multiple requesting sessions and work dependencies, typed perform/authorize/decide/provide-information requests, complete versioned procedures, freshness and withdrawal semantics. No new effect authority or independent work-status ledger.

Acceptance: Duplicate retries create one request; concurrent revisions conflict explicitly; one requester withdrawing preserves other dependants; dead sessions retain requests with uncertain freshness; material command/target/authority changes invalidate prior acceptance; unavailable source is not completed or withdrawn.

### OA-02 — Integrate Claude and Codex request publication and reconciliation

Owner: `agentops`. Served item: **agentops#2726**. Prerequisites: vuoro#2725.

Implement shared CLI/MCP publishing contract through qualified native-runtime integrations; verify genuine operator blockers; publish complete instructions before yielding; update or withdraw stable requests; use non-authoritative retry outbox during outages. Qualify each local/cloud/runtime mode separately. Transcript extraction may suggest candidates only.

Acceptance: Both Claude and Codex publish and revise requests with session/project/workspace/host links; retry/reconnect deduplicates; unsupported modes are explicit; routine permitted work is not handed off; raw logs and secrets are excluded; session closure is not completion.

### OA-03 — Deliver operator-action TUI over shared request lifecycle

Owner: `vuoro-cloud`. Served item: **vuoro-cloud#2727**. Prerequisites: vuoro#2725, agentops#2726.

Build keyboard-first collated TUI with ready/revalidation/verification/deferred views, impact and context filters, complete multi-step procedures, exact host/cwd/identity/target, expected results, progress and recovery, source-session links, defer/decline/report-performed actions. Reuse shared owner API and per-workspace entitlements.

Acceptance: Operator completes a request without reopening chat; wrong-host/stale-revision requests cannot appear ready; procedure progress survives restart; unauthorized project data is absent; viewing/copying or reporting performed is not authorization or successful effect; sensitive values remain outside durable request content.

### OA-04 — Verify operator outcomes and deliver safe continuation events

Owner: `vuoro`. Served item: **vuoro#2728**. Prerequisites: vuoro#2725, agentops#2726.

Implement explicit completion basis (authorized source observation or human attestation), partial/uncertain result reconciliation, versioned resolution events and retry-safe delivery; integrate through native-runtime owners for wake/resume or explicit continuation-ready packets. Scope blocked work precisely and support successor takeover without introducing a scheduler.

Acceptance: A false performed report remains unverified; physical work can resolve with labeled human attestation; multiple dependants receive one logical resolution; lost/duplicate delivery never repeats an effect; unavailable native wake produces visible continuation-ready state; a successor continues from current work and exact evidence without original chat.

### OA-05 — Add shared web view and bounded operator notifications

Owner: `vuoro-cloud`. Served item: **vuoro-cloud#2729**. Prerequisites: vuoro-cloud#2727, vuoro#2728, agentops#2730.

Reuse qualified request API for web UI; add assignment, defer-until/change conditions, explicit deadlines and bounded notification preferences. Batch compatible contexts while retaining independent authority boundaries; show coverage and freshness across runtimes. Qualify notification and identity integrations rather than duplicating native approval controls.

Acceptance: TUI/web show consistent revisions; unauthorized tenant data never leaks; unchanged requests remain quiet; meaningful changes re-surface appropriately; defer and decline propagate to affected work; expired action instructions require refresh; partial runtime coverage is visible.

### OA-06 — Qualify overnight operator-action workflow across both runtimes

Owner: `agentops`. Served item: **agentops#2730**. Prerequisites: vuoro-cloud#2727, vuoro#2728.

Run real interactive authentication, multi-step operator procedure and explicit authorization workflows with Claude and Codex; include dead requester, shared request, stale target, partial failure, missed wake and another session completing work. Compare against predeclared AO-K02 attention baseline; document setup, support, upgrade, rollback and export.

Acceptance: After an overnight absence the operator acts from one current list without reconstructing chats; affected work resumes or explicitly becomes continuation-ready; all mandatory negative cases pass; report denominators, stale/unnecessary requests, repeated prompts, operator effort, human wait and post-resolution delay. Retain/revise/adopt decision uses evidence, not screen availability.

## Field acceptance

OA-06 runs three real workflows across Claude and Codex: interactive authentication, a multi-step operator procedure, and an explicit authorization decision. Include overnight absence, a dead requesting session, shared requests, a stale target, partial failure, an unavailable source, missed/duplicate resolution delivery and completion by another session.

Predeclare workload/window and attention baseline. Report current-request coverage, stale and unnecessary requests, repeated prompts, operator minutes, blocked time waiting for the person versus verification/continuation delay, and failed/unsupported cases. Do not claim reduced burden from screen availability. An evidence-backed adopt/revise/retain decision closes the pilot; web/notification expansion follows the qualified TUI lifecycle.

Tracker status is authoritative in served Sprintctl. This document records requirements and registered references, not a second live work ledger. Earlier status/active reservations on linked work are preserved.

## Contract rewrite dependency amendment

This is the first complete consumer of the [estate contract rewrite](2026-10-18-estate-contract-rewrite.md). OA-01 joins EC-02 contract ownership; OA-02 uses EC-03 generation and EC-09 native integration; OA-03/OA-05 join EC-08 hosted/UI migration; OA-04 joins EC-05 work-provider and EC-07 evidence migration; OA-06 supplies the EC-20 field-proof gate. Existing functional acceptance and native execution boundaries remain. Discovery and credential-free prototypes may precede stack selection; production implementation uses the qualified EC-00 decision and foundation. No separate legacy operator API is to be built merely to migrate it later.
