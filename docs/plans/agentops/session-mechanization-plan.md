---
doc_id: session-mechanization-plan
status: ratified
supersedes: null
---

# Session mechanization plan: Tier 0/1/2 bookkeeping and the periodic scribe

Cross-repository agentops plan for mechanized session bookkeeping, per the
ratified direction in `sprintctl/docs/ops-upgrade-plan.md` (section 5) and the
verified facts in
[`ops-upgrade-reconciliation-2026-07.md`](ops-upgrade-reconciliation-2026-07.md).

The transport and authority semantics that this plan rides on — outbox model,
observation/command/decision split, identity and cursor model — are specified
canonically in `sprintctl/docs/plans/adr-outbox-sync-model.md` (doc_id
`adr-outbox-sync-model`, authored in the same pass). This plan links to that
ADR and does not duplicate its protocol details. Per-event ownership and
classification live in
[`state-event-command-matrix.md`](state-event-command-matrix.md).

## Product direction

> Move recording from instruction to mechanism wherever possible. Move genuine
> judgment to deterministic trigger points where it does not compete with the
> primary task.

Today, session bookkeeping depends on the primary agent remembering to record
what it did — an instruction competing with the actual task, executed by an
agent at its most exhausted. This plan replaces instruction with mechanism for
everything mechanically observable (Tier 0), injects context deterministically
where judgment used to be improvised (Tier 1), and moves the remaining genuine
judgment to fresh, dedicated reconcilers running at deterministic trigger
points (Tier 2 and the periodic scribe).

## Tier 0 — mechanical session exhaust

A **harness-neutral session wrapper** is the primary lifecycle mechanism.
Harness-specific hooks (Claude Code hooks, etc.) may supplement it but are not
the foundation — the wrapper must work regardless of which harness runs
inside it.

The wrapper mechanically records, with no agent cooperation required:

- `session.started`;
- repo, harness/model, runtime-session and origin-stream identities;
- initial prompt **digest** — not raw prompt content by default;
- explicit work-item or claim reference, when one was given;
- starting remote watermark;
- base/head commits and the commit list produced during the session;
- dirty-state or patch digest;
- diff statistics and touched paths;
- observable verification commands and their results;
- `session.ended`, or `session.end-inferred` when no clean end was observed;
- exit reason and timestamps.

**Privacy contract.** Raw prompts and transcripts are opt-in private artifacts
with explicit retention. A prompt digest is correlation evidence — enough to
tie sessions together, not enough semantic evidence for reconciliation on its
own.

**Failure posture.** Hooks and wrappers instrumenting manual work fail
**open**: a broken recorder must never block a human from working. Claim
acquisition and dispatcher verification gates fail **closed**: authority
operations without their preconditions do not proceed.

**Crash recovery.** Sessions that recorded `session.started` but never a clean
end get a recovery path that emits `session.end-inferred` with whatever
evidence survives (commits, worktree state). No session is silently lost to a
crash.

## Tier 1 — deterministic read-side context injection

At session start, the mechanism injects a **small ranked context packet** of
potentially relevant sprint items into the session. Ranking is deterministic
and prefers, in order:

1. explicit item or sprint reference in the dispatch/prompt;
2. exact path or manifest scope overlap;
3. linked documentation and ownership boundaries;
4. deterministic lexical/semantic candidate matching;
5. repo-level candidates.

The packet includes the cached projection **watermark and its age**, so the
session knows how stale its view of remote state is (see
`adr-outbox-sync-model` for watermark semantics).

**Claim rule:** only an **explicit** target (rank 1) may cause automatic claim
acquisition before the harness begins. Inferred candidates (ranks 2–5) are
advisory context, never automatic claims.

**Size rule:** the packet is bounded to a few useful candidates. Never paste
the whole backlog into the prompt.

## Tier 2 — post-session reconciliation

Do not depend on the exhausted primary agent to perform bookkeeping
correctly. The session-end mechanism creates a **`session-capsule/v1`**
artifact (schema and field contract:
[`session-mechanization-contracts.md`](../../dispatch/session-mechanization-contracts.md))
and enqueues reconciliation.

A **fresh** reconciler — a new session, not the one that did the work —
receives:

- the session capsule;
- commit and diff evidence;
- verification evidence;
- the current sprint projection;
- candidate work items;
- linked plan documents and done criteria;
- claims held during the session.

It may propose:

- link the session to an existing item;
- mark an item advanced;
- propose completion;
- identify conflict or duplicate work;
- propose a new item;
- classify the work as incidental — no backlog change.

Every code-bearing session should eventually receive a reconciliation
outcome, but not every session should create backlog activity. "Incidental,
no change" is a first-class, recorded outcome.

## Canonical periodic scribe

The **periodic scribe is the correctness path**. Immediate per-session
reconciliation (Tier 2 above) is only a latency optimization — if it never
runs, the scribe still converges the record.

The scribe:

- consumes unreconciled session exhaust up to a **durable cursor**;
- creates reviewable **`reconciliation-proposal/v1`** artifacts (schema and
  field contract:
  [`session-mechanization-contracts.md`](../../dispatch/session-mechanization-contracts.md));
- **never directly mutates authoritative sprint state**;
- groups related sessions where useful;
- records explicit no-change outcomes;
- tolerates delayed execution without losing evidence.

Each proposal must include:

- stable proposal ID and source-session IDs;
- evidence refs;
- observed and current aggregate revisions;
- proposed commands;
- confidence and uncertainty;
- a deduplication key;
- lifecycle state: `pending`, `accepted`, `rejected`, `superseded`.

Accepted proposals execute through **normal sprintctl authority commands**
(see `adr-outbox-sync-model` for command/decision semantics). Rejections are
durable so the scribe does not repeatedly rediscover the same proposal.

### Naming: the scribe is NOT `scribectl`

The workspace repository `scribectl` is an **unrelated fiction-writing
contract runner** (Obsidian vault pipeline) — see fact 10 of the
[reconciliation doc](ops-upgrade-reconciliation-2026-07.md). The canonical
periodic scribe described here is a **new, agentops-owned component**. It must
not be assigned to, implemented in, or confused with the `scribectl`
repository. The naming collision is coincidental; treat any backlog item or
doc that routes scribe work to `scribectl` as a misassignment.

## Dogfooding metrics

The architecture must measurably reduce silent sprint drift
(`ops-upgrade-plan.md` section 6). Document, instrument, and backlog metrics
for:

- percentage of manual sessions with Tier-0 traces;
- percentage of code-bearing sessions linked explicitly at start;
- unreconciled session count;
- median and p95 reconciliation age;
- commits older than a threshold without a session/item link;
- accepted, rejected and no-change proposal rates;
- duplicate-work incidents despite claims;
- local projection watermark age;
- stale tool/version incidents;
- human review effort.

**Target failure mode:** bounded, visible reconciliation lag — not months of
silent divergence. When the mechanism degrades, the metrics show a growing
but observable queue, never a quietly wrong sprint record.

## Cockpit surfaces

The agent-cockpit surface (agentops-owned) grows:

- a **review queue** for `reconciliation-proposal/v1` artifacts — pending
  proposals with evidence refs, accept/reject actions executing through
  sprintctl authority commands per the write-surface policy;
- **reconciliation-lag panels** — unreconciled session count, median/p95
  reconciliation age;
- **watermark-age panels** — local projection watermark age per repo.

## Ownership

Per the matrix ([`state-event-command-matrix.md`](state-event-command-matrix.md)):
the Tier-0 session wrapper *mechanism* is proposed as actionq-owned (session
lifecycle authority); the capsule/exhaust *contract*, cross-domain projection,
scribe, and cockpit surfaces are agentops-owned. Proposal acceptance executes
as sprintctl authority commands. See the matrix for the full assignment and
its ratification status.

## Related documents

- [`session-mechanization-contracts.md`](../../dispatch/session-mechanization-contracts.md)
  — `session-capsule/v1` and `reconciliation-proposal/v1` schemas and field
  contracts (item #1106).
- `sprintctl/docs/ops-upgrade-plan.md` — ratified product direction (sections 5, 6).
- `sprintctl/docs/plans/adr-outbox-sync-model.md` — canonical protocol text:
  outbox, observation/command/decision split, identities, cursors.
- [`state-event-command-matrix.md`](state-event-command-matrix.md) — per-event
  classification and ownership.
- [`ops-upgrade-reconciliation-2026-07.md`](ops-upgrade-reconciliation-2026-07.md)
  — verified source-of-truth reconciliation, 2026-07-14.
- [`write-surface-policy.md`](write-surface-policy.md) — which surfaces may
  mutate sprint state.
