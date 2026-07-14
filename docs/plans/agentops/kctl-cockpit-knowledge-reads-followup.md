---
doc_id: kctl-cockpit-knowledge-reads-followup
status: draft
supersedes: null
---

# kctl artifact integration for cockpit knowledge reads — follow-up definition

Definition deliverable for sprint item #953. Decides **how the agent-cockpit
will read kctl knowledge**, assigns the follow-up work to owning repos, and
bounds what is explicitly out of scope. It creates no protocol text of its
own; kctl remains the knowledge-review authority
([`state-event-command-matrix.md`](state-event-command-matrix.md)).

## Context

kctl is a local-first, read-only consumer of sprintctl events with a
review pipeline (`candidate → approved → published → rendered markdown`) in
two streams (`durable`, `coordination`). Its convergence artifact is
committed markdown (`knowledge-base.md` / repo-policy ops target). The
cockpit currently reads sprintctl (Postgres), actionq (Postgres/HTTP), and
audit NDJSON under `COCKPIT_ARTIFACTS_ROOT` — it has **no knowledge
surface**. kctl's backlog sprint (#381, "knowledge artifacts and cockpit
reads") exists for exactly this work; sprintctl sprint 374 items 876–895
also describe kctl-owned knowledge-model work parked in the wrong scope
(reconciliation fact 8) and must be reconciled against this definition, not
duplicated.

## Decision: structured artifact export, not markdown scraping, not DB reads

Three candidate read paths were considered:

1. **Cockpit parses committed `knowledge-base.md`.** Zero kctl changes, but
   markdown scraping couples the cockpit to a human-format render and loses
   stream/status/provenance fields. Acceptable only as a link-out.
2. **kctl-owned structured artifact export** — chosen. kctl writes a
   versioned, machine-readable knowledge artifact under
   `_artifacts/<repo>/knowledge/`; the cockpit consumes it read-only from
   `COCKPIT_ARTIFACTS_ROOT`, exactly as it already does for audit NDJSON and
   reconciliation proposals. This is also the path ADR-001 deferred
   ("`kctl` structured export format … defer until the orchestrator needs
   it") — the cockpit is now the consumer that needs it.
3. **Cockpit reads kctl's SQLite directly.** Rejected: couples the cockpit
   to kctl internals and violates the ownership rule (same class of mistake
   as the pre-#1105 direct SQL sprint-activation write).

Contract sketch (to be specified properly in the kctl-owned item, as
`knowledge-artifact/v1`): one NDJSON record per published entry with stable
entry id, stream (`durable` | `coordination`), lifecycle status, source
sprintctl event refs, repo scope, published/rendered timestamps, and content
digest. Export is idempotent and append/replace-safe so repeated runs
converge. Read-only for every consumer; **review lifecycle transitions stay
kctl CLI authority commands** — the cockpit renders knowledge, it does not
accept/reject candidates (any future write goes through the
[write-surface policy](write-surface-policy.md) as a mediated tier, not
direct).

## Follow-up items (bound by this definition)

kctl sprint #381 already carries the kctl-side items; this definition
annotates them (doc refs added) rather than duplicating them:

| Scope / sprint | Item | Role under this definition | Depends on |
|---|---|---|---|
| kctl #381 | #954 Design `_artifacts` knowledge NDJSON contract for cockpit reads | specifies `knowledge-artifact/v1` (field sketch above); must also reconcile sprintctl sprint-374 items 876–895 (parked knowledge-model work) — annotate or supersede, don't duplicate | — |
| kctl #381 | #955 Implement optional knowledge NDJSON render/export under `_artifacts` | the idempotent `kctl export` producer | #954 |
| kctl #381 | #958 Expose stable JSON status/review surfaces for future cockpit knowledge pane | read-only status surface; **not** a write path | #954 |
| agentops #380 | #1165 cockpit knowledge read surface: `lib/cockpit/knowledge.js` + `GET /cockpit/api/knowledge` + shell section, reading `knowledge-artifact/v1` from `COCKPIT_ARTIFACTS_ROOT` (created with this definition) | the consumer | #955 shipped |

Non-scope: cockpit-side review actions; kctl writing to sprintctl (contract
stays read-only); any knowledge search/index service; changing kctl's
local-first SQLite model.

## Related documents

- [`state-event-command-matrix.md`](state-event-command-matrix.md) — kctl
  review lifecycle ownership.
- [`write-surface-policy.md`](write-surface-policy.md) — why the cockpit
  gets no direct write path here.
- [`session-mechanization-plan.md`](session-mechanization-plan.md) — the
  artifact-under-`_artifacts` reading convention this reuses.
- `sprintctl-orchestrator/ADR-001-orchestration-boundary.md` (superseded) —
  origin of the deferred structured-export idea.
