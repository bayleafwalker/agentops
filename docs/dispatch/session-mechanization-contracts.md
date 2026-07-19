# Session mechanization contracts: session-capsule/v1 and reconciliation-proposal/v1

Status: adopted for session-mechanization work (item #1106)

These are the two agentops-owned artifact contracts named in
[`docs/plans/agentops/session-mechanization-plan.md`](../plans/agentops/session-mechanization-plan.md)
and classified in
[`docs/plans/agentops/state-event-command-matrix.md`](../plans/agentops/state-event-command-matrix.md).
Per the matrix's ownership rule, the Tier-0 session wrapper *mechanism* and
session lifecycle *state* are proposed as `actionq`-owned; agentops owns the
capsule/exhaust *contract* below, the cross-domain projection, the scribe, and
the cockpit surfaces that read it. Both artifact types are classified
**observation**: appendable offline, never authoritative on their own, never
silently discarded for a stale basis revision.

This document defines the contract only. It does not implement the Tier-0
wrapper — that remains the actionq-owned wrapper mechanism. Both consumers
are implemented: the canonical periodic scribe (item #1107,
`templates/dispatch/skills/session-scribe/SKILL.md` +
`templates/dispatch/scripts/session_scribe.py`) and the fresh post-session
reconciler (item #1108,
`templates/dispatch/skills/session-reconciler/SKILL.md` +
`templates/dispatch/scripts/session_reconciler.py`), which share one
durable cursor so neither path double-processes a capsule.

## Canonical schemas

- `templates/dispatch/session-mechanization/session-capsule.schema.json`
- `templates/dispatch/session-mechanization/reconciliation-proposal.schema.json`

Both mirror structure for editor support only. The dependency-free semantic
validator is normative:

```bash
python /projects/dev/agentops/templates/dispatch/scripts/validate_session_mechanization_artifacts.py --root .
```

Run against explicit paths, or let it discover `session-capsules/*.json` and
`reconciliation-proposals/*.json` under `--root`.

## session-capsule/v1

Tier-0 mechanical session exhaust: what a harness-neutral session wrapper
recorded with no agent cooperation required. Created **once, at session end**
(clean or crash-inferred) — there is no partial or open capsule state in v1.

| Field | Rule |
|---|---|
| `capsule_id`, `origin_stream_id` | UUIDs. `origin_stream_id` is the producer outbox stream identity from `adr-outbox-sync-model`; a capsule never carries a remote-origin id. |
| `runtime_session_id` | Same field name and semantics actionq already projects in session summaries (`actionq/actionq/db.py:summarize_sessions`). |
| `repo.project` | Portable repo scope identifier (e.g. `agentops`). `repo.repo_id` is the optional minted UUID once dispatch manifests carry it. |
| `harness`, `model` | `harness` is a free string, deliberately not an enum — the wrapper must work for any harness, including `manual` for human-only sessions, which also sets `model` to `null`. |
| `actor` | Who ran the session. |
| `target` | Null, or `{rank, ref}` per the Tier-1 ranking in the mechanization plan. `ref` uses the prefixed vocabulary from [`dispatch-manifest.md`](dispatch-manifest.md) (`wi:`, `sprint:`). Only `rank: explicit` may pair with an automatically acquired claim. |
| `claim` | Null, or the claim held during the session (`claim_id`, `work_item_id`, `claim_type`, `acquired_automatically`). |
| `starting_watermark` | `{ingest_offset, age_seconds}` — the remote projection watermark visible at session start, so a reconciler knows how stale the session's view was. |
| `started_at`, `ended_at`, `end` | `end.kind` is `clean-end` or `end-inferred` (crash recovery); `end.reason` and `end.exit_code` are nullable. |
| `git` | `base_commit`, `head_commit`, `commits[]`, `branch`, `worktree`, `dirty`, `patch_digest` (required sha256 when `dirty`), `diff_stat`, `touched_paths[]`. |
| `verification` | Array of `{command, result, evidence_ref}`; `result` is `pass`, `fail`, `error`, or `skipped`. |
| `privacy` | `raw_transcript_captured` (bool) and `raw_transcript_ref` (must be null unless captured). Raw prompts and transcripts stay opt-in private artifacts with explicit retention — a capsule never embeds transcript content, only a pointer when one was deliberately captured. |

## reconciliation-proposal/v1

A reviewable artifact produced by the canonical periodic scribe or a fresh
post-session reconciler. **The scribe is not `scribectl`** — see fact 10 of
[`ops-upgrade-reconciliation-2026-07.md`](../plans/agentops/ops-upgrade-reconciliation-2026-07.md).
A proposal never mutates authoritative state; acceptance executes as normal
sprintctl authority commands (`item.done`, `item.transition`, `sprint.activate`,
etc. — see the matrix's sprintctl table).

| Field | Rule |
|---|---|
| `proposal_id` | UUID. |
| `dedup_key` | Stable string so the scribe does not repeatedly rediscover a rejected proposal. |
| `source_capsules` | One or more `{runtime_session_id, capsule_ref}`; `capsule_ref` is an `artifact` kind ref to the source `session-capsule/v1`. |
| `evidence_refs` | Immutable refs (same `kind` vocabulary as `capability-receipt.schema.json`: `git-commit`, `sprint-event`, `document`, `verification-result`, `release`, `artifact`). |
| `basis` | `{observed_revision, current_revision}` — the target aggregate's revision when evidence was gathered versus now. Equal when nothing else advanced it meanwhile. |
| `classification` | One of the six outcomes the mechanization plan lists: `link-existing-item`, `mark-item-advanced`, `propose-completion`, `flag-conflict-or-duplicate`, `propose-new-item`, `incidental-no-change`. |
| `target` | Null only when `classification` is `incidental-no-change`; otherwise `{kind, ref}`. |
| `proposed_commands` | Empty only when `classification` is `incidental-no-change`; otherwise one or more `{command_type, params}` — the sprintctl authority commands to run on acceptance. |
| `confidence` | `{level: high\|medium\|low, rationale}`. |
| `lifecycle` | `{state: pending\|accepted\|rejected\|superseded, decided_at, decided_by, rejection_reason, superseded_by}`. A `pending` proposal carries no decision fields; `rejected` requires `rejection_reason`; `superseded` requires `superseded_by`. |

`incidental-no-change` is a first-class outcome, not an omission — the
mechanization plan is explicit that not every session should create backlog
activity, but every code-bearing session should eventually receive a recorded
reconciliation outcome.

### Agentops execution sidecar

Proposal acceptance and sprintctl command success are deliberately separate
facts. The cockpit executor persists its internal runtime record at
`reconciliation-executions/<proposal-id>.json` with
`schema_version: reconciliation-execution/v1`. This is an agentops-owned
sidecar, not a third cross-repository proposal contract. It contains:

- the proposal ID and deduplication key;
- overall state (`deferred`, `pending`, `succeeded`, `rejected`, `partial`, or
  `unavailable`);
- executor actor, timestamps, and attempt count; and
- an ordered command list with deterministic `request_event_id`, command type,
  aggregate ID, basis revision, non-secret payload, attempts, and the
  correlated sprintctl decision or availability error.

The sidecar never stores claim tokens or other authority credentials. A
terminal accepted/rejected command is not resubmitted. An unavailable or
crash-interrupted command is retried with the same request UUID, allowing
sprintctl to return the original atomic decision. The shared
`reconciliation-proposal/v1` remains unchanged so producers do not need to
understand executor runtime state.

## What this contract does not decide

- Which outbox transports these artifacts (actionq's Tier-0 wrapper, or a
  direct agentops-owned channel) and which `record_type` string classifies
  them as `observation` in a producer's taxonomy. That is an integration
  decision for whichever repo implements the wrapper (proposed: `actionq`)
  and is out of scope for this contract.
- Where finalized artifacts are stored. This contract does not mandate it,
  but the shipped scribe implementation (`session_scribe.py`) operates
  against `_artifacts/<repo>/session-capsules/*.json` and
  `_artifacts/<repo>/reconciliation-proposals/*.json` by analogy with
  capability receipts — treat that as the working convention until a Tier-0
  wrapper decision says otherwise.
- The scribe's internal durable-cursor bookkeeping (which session exhaust it
  has already consumed) — that belongs to the scribe implementation (#1107),
  not to the proposal artifact it emits.

## Related documents

- [`session-mechanization-plan.md`](../plans/agentops/session-mechanization-plan.md) — product direction, Tier 0/1/2, dogfooding metrics, cockpit surfaces.
- [`state-event-command-matrix.md`](../plans/agentops/state-event-command-matrix.md) — per-event classification and ownership.
- `sprintctl/docs/plans/adr-outbox-sync-model.md` — outbox, identity, and cursor model these artifacts ride on.
- [`dispatch-manifest.md`](dispatch-manifest.md) — the `wi:`/`sprint:`/`sha:`/`pr:` ref vocabulary reused in `target.ref`.
- `templates/dispatch/capability-receipt/` — the sibling artifact-plus-validator convention this contract follows.
