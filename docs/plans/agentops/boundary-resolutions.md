---
doc_id: boundary-resolutions
status: ratified
proposed_by: operator
ratified_by: operator
ratified_at: 2026-08-12
created_at: 2026-08-12
references:
  - ecosystem-simplification-plan.md
  - vuoro-served-substrate-plan.md
  - vuoro/docs/plans/architectural-simplification-alignment.md
  - actionq/docs/plans/vuoro-served-execution-alignment.md
  - agentops/docs/plans/agentops/write-surface-policy.md
  - vuoro/docs/architecture/portable-execution.md
---

# Boundary resolutions for ecosystem simplification

This document records decisions for the five critical-path contention points
identified in `ecosystem-simplification-plan.md`. Each resolution is proposed
here and must be ratified before dependent work begins.

## R1 — Execution authority: `actionq` owns one-shot and daemon execution

**Resolution:** `actionq` is the sole execution authority for the ecosystem.
`actionq-dispatcher` is deprecated as a compatibility shim whose only
permitted behavior is to launch `actionq-daemon --once`.

**Rationale:** The historical `dispatcher-once` coordinator responsibilities
(queue claims, worktree preparation, harness invocation, policy enforcement,
settlement) have moved into `actionq-daemon`. Keeping two packages that
appear to coordinate execution creates confusion about who may claim actions
and who may prepare worktrees.

**Consequences:**
- `actionq-dispatcher/AGENTS.md` and ecosystem docs are updated to state that
  the package is deprecated and must not grow new behavior.
- No new queue, claim, worktree, harness, or settlement logic is added to
  `actionq-dispatcher`.
- Once `actionq-daemon` parity is proven in production, `actionq-dispatcher`
  may be retired.

**Ratification:** ratified 2026-08-12

## R2 — Worktree/runner materialization: ActionQ owns worktree preparation; Runner is an internal package

**Resolution:** ActionQ owns worktree preparation as part of its execution
authority. The portable-execution architecture's "Runner" is realized as an
internal package within `actionq` (or a closely-coordinated sub-package), not
a separate repository member.

**Rationale:** `vuoro/docs/architecture/portable-execution.md` assigns
repository materialization and harness invocation to a Runner, while
`actionq/AGENTS.md` claims worktree preparation. The current implementation
collapses runner behavior into `actionq-daemon`. Creating a separate member
for Runner would add coordination overhead without a distinct state domain;
the runner's outputs (execution envelopes, receipts) are ephemeral artifacts,
not a new authority class.

**Consequences:**
- `vuoro/docs/architecture/portable-execution.md` is updated to clarify that
  the Runner is an internal ActionQ package.
- ActionQ may expose a stable Runner interface for future external runners,
  but no cross-member Runner repository is created in this tranche.
- Worktree preparation remains inside `actionq` and does not move to
  `vuoro` or a new member.

**Ratification:** ratified 2026-08-12

## R3 — Cockpit write surface: sprint activation uses sprintctl authority command

**Resolution:** Cockpit sprint activation is performed by calling the
sprintctl authority command (`sprintctl sprint status --status active`). The
grandfathered direct-SQL exception documented in `write-surface-policy.md` is
removed.

**Rationale:** `write-surface-policy.md` states that no remote surface may be
handed `SPRINTCTL_URL` semantics (raw database write access). The cockpit
sprint-activation route now invokes the domain-owned sprintctl command rather
than executing SQL directly, satisfying the policy. The stale exception text
must be removed to prevent future routes from treating it as precedent.

**Consequences:**
- `apps/web/lib/cockpit/sprintctl.js` already calls `sprintctl sprint status`
  for activation; no further code change is required for this resolution.
- The "Documented boundary exception: cockpit sprint-activation SQL
  transaction" section in `write-surface-policy.md` is deleted and replaced
  with a note that activation is domain-owned.

**Ratification:** ratified 2026-08-12

## R4 — Recovery authority: remove the service-side in-memory recovery reconciler

**Resolution:** The in-memory recovery reconciler currently proposed inside
`vuoro-service` is removed. Recovery records remain local client exports or
are routed to a durable domain-owned adapter when such an adapter exists.

**Rationale:** `vuoro/docs/plans/architectural-simplification-alignment.md`
V-S2 presents two options: retain local client export and remove the
disconnected service reconciler, or route versioned recovery operations to a
durable domain-owned adapter. Vuoro must not become recovery authority. The
in-memory reconciler has no durable owner and would make Vuoro responsible
for recovery semantics without a catalog-backed domain adapter.

**Consequences:**
- The service-side recovery reconciler is not implemented, or is removed if
  present.
- Recovery export remains a local `vuoro-client` concern.
- Future recovery authority must be a domain-owned adapter (likely
  `sprintctl` or `auditctl`) with a published catalog contract.

**Ratification:** ratified 2026-08-12

## R5 — outctl membership: outctl is a full ecosystem member

**Resolution:** `outctl` is a full member of the agent-ops substrate. It is
consistently represented in project member tables, AGENTS guidance, and
generated project context.

**Rationale:** `outctl` exists in the derived project folder and is described
in `agentops/docs/ecosystem.md`, but it is inconsistently omitted from member
enumerations. This leads to accidental exclusion from cross-member work and
confusion about whether it participates in the served-substrate migration.

**Consequences:**
- `outctl` is added to the project member table and `project.context.json`.
- `outctl` remains local-only and non-authoritative; it does not own command
  scheduling, work state, action lifecycle, audit judgments, curated
  knowledge, or remote execution.
- `outctl`'s W0–W8 Rust migration remains a separate owner-local plan.

**Ratification:** ratified 2026-08-12

## Next steps

1. Ratify each resolution above.
2. Update affected member AGENTS.md, plan documents, and ecosystem docs to
   match the ratified decisions.
3. Proceed with `ecosystem-simplification-plan.md` Batch 1 implementation
   items B1.2–B1.5.
