---
doc_id: session-note-contract-plan
status: ratified (2026-07-23 — see operator decisions for per-item rulings)
supersedes: null
---

# Session-note contract plan: semantic session notes (session-note/v1)

Implementation plan for the semantic-trace gap named in
[`../trace-originating-req.md`](../trace-originating-req.md). Planned as
`frontier-plan` output per `agentops.dispatch.json`; build executes as
`fast-build` with `review_required: true`, review as `review-synthesis`.

## Framing: what this is and is not

The word "trace" in the originating requirement is **session-level**, not
execution-level. The traceq / pytest execution-evidence experiment
([`../trace-commission.md`](../trace-commission.md)) is a separate,
already-decided workstream — do not merge the two or reuse a `trace*` name
here, to keep that namespace clean.

Most of the originating requirement is already covered by decided
architecture:

| Requirement fragment | Already covered by |
|---|---|
| Mechanical session metadata, commits, verification, crash recovery | `session-capsule/v1` (Tier 0, [`../../dispatch/session-mechanization-contracts.md`](../../dispatch/session-mechanization-contracts.md)) |
| Governance/backlog claims reaching the sprint record | scribe #1107 / reconciler #1108 / cockpit queue #1109, #1173 |
| Knowledge, audit, cost, process projections "later" | kctl/auditctl domains + dogfooding metrics in [`session-mechanization-plan.md`](session-mechanization-plan.md) |
| Cross-machine transport, in target state | served-substrate observation ingestion (`/api/audit/v1`), outbox per `adr-outbox-sync-model` |

The genuine gap is the **semantic layer**: agent-authored handover, summary,
and outcome notes as stable, discoverable artifacts. The capsule is
deliberately mechanical (prompt digest, never content); nothing today durably
captures "this session reached this state, pick up here" — the originating
requirement's most common operational case (/clear re-pickup, end-of-day
handoff, `-resume` session-ID crawling). Because `/projects/dev` is
machine-local Btrfs (commit 6704e44), file-convention artifacts alone can
never satisfy the cross-machine half; that constraint shapes Phase 2 below.

### Boundary against adjacent sprintctl prior art

Two existing sprintctl surfaces are adjacent but do not cover the gap, and
the contract must not duplicate them:

- **`sprintctl handoff`** produces a working-memory bundle *projected from
  authoritative sprint state* (items, events). It is mechanical, sprint-scoped,
  and cannot carry authored "pick up here" prose from a session that made no
  sprint events. A session note is authored, repo/project-scoped observation.
- **`sprintctl item note`** records a structured note event *on a work item*
  in the authoritative record. The common /clear re-pickup case is frequently
  not item-bound, and notes must never be authority mutations. A session note
  that implies backlog change flows through the existing scribe →
  `reconciliation-proposal/v1` path, which needs no change.

The reader tooling below may *reference* both (a note can carry `wi:` refs;
the skill may suggest `sprintctl handoff` alongside the latest note), but the
artifact itself stays an agentops-owned observation.

## Goal

Define and implement **session-note/v1**: an agentops-owned artifact contract
plus writer/reader tooling, so any session can (a) durably record a
handover/summary/outcome note bound to its repo, project, and optional
work-item refs, and (b) retrieve the latest relevant note at session start
without session IDs or transcript crawling.

## Phase 1 scope (buildable now, single-machine value)

All file areas inside manifest `allowed_path_roots`.

### Contract

`templates/dispatch/session-mechanization/session-note.schema.json`, sibling
to the capsule schema, plus a `session-note.example.json`. Fields:

| Field | Rule |
|---|---|
| `schema_version` | `session-note/v1`. |
| `note_id` | UUID. |
| `origin_stream_id` | UUID, same outbox semantics as the capsule (`adr-outbox-sync-model`). |
| `runtime_session_id` | Nullable — manual sessions exist; same field semantics as the capsule. |
| `repo.project` / `repo.repo_id` | Same rule as `session-capsule/v1`. |
| `note_kind` | `handover` \| `summary` \| `outcome`. **Deliberately only three**: `governance` and `process-observation` kinds were considered and deferred — no demonstrated consumer exists yet (kill-criteria discipline from the trace commission). Adding a kind later is an additive v1.x change; removing one is not. |
| `target_refs` | Zero or more prefixed refs from the existing `wi:`/`sprint:` vocabulary (`dispatch-manifest.md`). |
| `capsule_ref` | Nullable `artifact`-kind immutable ref to the session's capsule, when one exists. |
| `created_at` | RFC 3339 timestamp. |
| `supersedes` | Nullable note ref, forming the repeated-/clear chain; `latest` resolution follows the chain head. Chains are not assumed linear: concurrent sessions can produce **multiple heads**, and the tiebreak is newest `created_at`, then `note_id` for determinism. The resolver tolerates dangling `supersedes` refs (pruned or off-machine ancestor) and guards against cycles with a visited set. |
| `body` | Markdown, **max 16 384 bytes (16 KiB)** — an explicit cap so notes stay handover-sized, not transcript-sized. Normative check in the validator, mirrored as `maxLength` in the schema. |
| `privacy` | Capsule posture applies: a note is deliberately authored content — that is its point — but it must never embed transcripts or credentials. |

Body structure: v1 keeps a free markdown body. Study slice **D2 (session
handoff — SBAR, HSE shift-handover, SRE on-call handoffs;
[`vuoro-phase1-study-backlog.md`](vuoro-phase1-study-backlog.md))** is
expected to produce evidence on structured vs free-text handoff. That
evidence lands first as **recommended section headings in the skill**
(instruction-level, no schema change); only if it proves out does a v2 add
structured body fields. This sequences the schema decision after the study
without blocking on it.

### Matrix classification (row text, to land with the schema)

One row in `state-event-command-matrix.md`, same shape as `session-capsule/v1`:

> | `session-note/v1` | observation (artifact + pointer) | yes | no (pointer is non-validation-bearing) | note pointer visible immediately | the observation itself, once ingested |

Appendable offline, never authoritative, never discarded for stale basis.

### Validator

Extend `templates/dispatch/scripts/validate_session_mechanization_artifacts.py`
to discover `session-notes/*.json`; it remains the normative check (schema
mirrors for editor support only, per the existing convention).

### Writer/reader

`templates/dispatch/scripts/session_notes.py`:

- `append` — writes a validating artifact to
  `_artifacts/<repo>/session-notes/` (working convention by analogy with
  capsules; the contracts doc's "not mandated, working convention" language
  applies).
- `latest --repo <r> [--project <p>] [--kind handover]` — resolves the latest
  non-superseded note; with `--project`, resolves across **all member repos'**
  `_artifacts` dirs — the cross-repository half of the requirement,
  deliverable now.
- `list` — enumerates with kind/repo/date filters.

### Skill

`templates/dispatch/skills/session-handover/SKILL.md`: when ending or
/clear-summarizing, write the summary as a session-note via the script
**instead of** (not in addition to) pasting it forward; on start, inject
`latest` output when no hook has already done so. Register in manifest
`skills.selected`.

**Known tension, named deliberately**: the mechanization plan's product
direction is "move recording from instruction to mechanism"; a skill is an
instruction executed by the agent at its most exhausted. The automation layer
below exists to shrink the instruction surface to the minimum that genuinely
requires judgment — the note's *content*. What remains skill-only is listed
honestly there; the coverage metric is the designed signal for whichever
residual instruction surface decays.

### Automation and hooks (mechanism layer)

Routine, not memory: both halves of the loop get a deterministic trigger so
no session has to remember to prompt for them. Per the mechanization plan,
harness-specific hooks **supplement** the harness-neutral Tier-0 wrapper and
are not its substitute — hooks cover Claude Code sessions now; the wrapper
(actionq-owned, Phase 2) is what covers every harness including `manual`.

- **Injection — `SessionStart` hook** (matchers `startup|resume|clear`):
  runs `session_notes.py latest --hook`, a hook-mode entry point that reads
  the hook payload on stdin, resolves repo/project from the working
  directory, and prints the latest relevant note (bounded) on stdout for
  context injection. Judgment-free, so it belongs entirely to mechanism.
  This makes the /clear **re-pickup** half fully automatic. The output
  begins with a **deterministic already-injected sentinel line carrying the
  `note_id`**, so the skill's "when no hook has already done so" fallback —
  and later the wrapper's dedup — is a string match, never a judgment call.
  When the Tier-1 context packet absorbs injection, the hook entry is
  removed from the baseline in the same change (ratified, decision 2).
  The hook also drops a **session marker** (HEAD sha keyed by
  `runtime_session_id`) so the stop-gate's commits-since-start heuristic has
  a mechanical baseline instead of silently degrading to dirty-only.
- **Capture — `Stop` hook (stop-gate)**: `session_notes.py stop-gate` blocks
  turn-end **at most once** per session (honoring `stop_hook_active` to
  prevent loops) when the session did meaningful work (dirty worktree, or
  commits since session start — cheap, mechanical heuristics) and no note
  exists for this `runtime_session_id`; the block reason instructs the agent
  to write the note via `append` or state why none is needed. Judgment stays
  with the agent that has the context; *remembering* moves to mechanism.
- **Honest residue (still instruction-shaped)**: `/clear` and `SessionEnd`
  fire after the conversation can no longer act, so a pre-/clear summary
  redirect remains the skill's job; and codex/manual sessions (this repo's
  `default_harness` is codex) get no Claude hooks at all. These are exactly
  the populations the coverage metric below watches, and the wrapper closes
  in Phase 2.
- **Coverage automation — `session_notes.py coverage`**: emits the
  note-coverage report mechanically (notes vs capsules once #1174 capsules
  flow; notes/week proxy until then), so the metric is a command, not a
  manual census. Scheduling can later ride the existing
  `session_mechanization_trigger.py` tick conventions; the report command is
  the Phase 1 deliverable.
- **Distribution**: hook wiring ships as `.claude/settings.json` hook
  entries in this repo (dogfood first) plus a documented snippet in
  `templates/dispatch/repository-baseline/` for adopting repos — the
  baseline currently carries no `.claude` template, so this is a new,
  deliberately small baseline surface.

### Dogfooding metric

Add **note coverage** to the mechanization plan's dogfooding metrics:
percentage of ended sessions (capsules, once real capsules flow via #1174)
with an associated `session-note/v1`; until then, the proxy is notes written
per week per repo. A decaying ratio is the designed signal that skill-level
recording is failing and the wrapper (mechanism) integration should be
prioritized.

### Docs

- `session-note/v1` section in `session-mechanization-contracts.md`, same
  table format as the capsule.
- The matrix row above.
- Short pointer in `session-mechanization-plan.md`: Tier-1-adjacent
  **cooperative semantic exhaust** — distinct from Tier-0's
  no-cooperation rule, and never a substitute for it.
- Superseded text marked, not rewritten (AGENTS.md documentation-quality
  rule).

### Tests

`templates/dispatch/tests` (unittest, discovery-compatible): schema
round-trip; unknown `note_kind` rejected; oversize body rejected; supersedes
chain resolution, including **two concurrent heads within one repo**
(tiebreak per contract), a dangling `supersedes` ref, and a cycle; `latest`
picks newest across two repos; idempotent re-validation.

## Out of scope

- Execution tracing (traceq) — separate commission.
- The Tier-0 wrapper, transport/outbox integration, and any
  actionq/sprintctl/auditctl runtime behavior (manifest `out_of_scope`;
  wrapper is actionq-owned per decision #968).
- Cockpit surfaces, kctl knowledge extraction from notes, cost analytics —
  later projections; the contract's refs make them possible, nothing more.
- Any authority mutation (see boundary section above).

## Phase 2 (blocked, do not build yet)

Cross-machine visibility: notes ride the same observation-ingestion channel
as capsules — target-state `/api/audit/v1` per the served-substrate plan. The
capsule contract explicitly deferred this transport decision to the Tier-0
wrapper integration; notes inherit that deferral rather than opening a second
channel. Phase 2 unblocks when the wrapper/outbox decision lands.

An interim alternative exists and is deliberately **not** chosen here without
an operator call — see operator decisions.

## Acceptance checks

1. `validate_session_mechanization_artifacts.py --root .` passes with note
   fixtures present; corrupted/oversized fixtures fail clearly.
2. From repo A, `session_notes.py latest --project <p> --kind handover`
   returns a note written from repo B — no session ID involved.
3. `python -m unittest discover -s templates/dispatch/tests` passes (manifest
   verification, targeted-first).
4. Hook loop is mechanical and safe: `latest --hook` emits the newest
   project note given only a hook payload on stdin; `stop-gate` blocks at
   most once per session, never when `stop_hook_active` is set, and passes
   through silently for sessions with no meaningful work or an existing
   note.
5. `session_notes.py coverage` emits the note-coverage report without manual
   counting.
6. Docs updated per the manifest docs family; superseded text marked, not
   rewritten.
7. Build result goes through dispatch-review (`review_required: true`) and
   code-change-verification before close.

## Operator decisions (ratified 2026-07-23)

1. **Naming — ratified `session-note/v1`.** Nothing `trace*`-shaped: trace
   naming stays reserved for more execution-shaped work (traceq). The
   originating requirement's word describes a need, not a name — "trace"
   connotes mechanical execution capture, the opposite of an authored
   observation. Rationale recorded in the contracts doc so future readers of
   the originating requirement aren't confused by the divergence.
2. **Injection ownership — approved for this packet**: hooks + skill now,
   wrapper later. Hardening required (see Automation section): the hook
   prints a deterministic already-injected sentinel carrying the `note_id`,
   so the skill's fallback check — and later the wrapper's dedup — is a
   string match, not a judgment call. Committed now: when the Tier-1 context
   packet absorbs injection, the hook entry leaves the baseline **in the
   same change**; double injection is the failure mode designed out today.
3. **Cross-machine transport — last-priority requirement.** Implement only
   once the service-substrate work has completed for more centralized
   serving. No interim write path: a transitional central-DB channel would
   contradict the direction of minimizing CLIs writing to the central DB,
   and no file-sync escape hatch is sanctioned without a fresh operator
   call. Notes stay machine-local until then; the coverage metric and
   originating requirement keep the pressure visible.
4. **Retention — a project/config question, not a schema one.** Policy:
   keep-all for now, config-allowed per project. Down the line: a
   **clean-history action** and/or **summarize-and-clean-history action**
   (`session_notes.py prune`, dry-run by default — supersedes-aware and
   kind-aware; candidate shape: superseded non-heads prunable ~30 d, stale
   handover heads ~90 d after a newer note exists, summary/outcome heads
   retained pending the kctl-extraction decision, per-repo count cap as
   backstop). Enforcement lands before Phase 2 replicates notes
   off-machine; nothing blocks Phase 1.

## Backlog

Three items in sprint #380 (agentops backlog), track `session-mechanization`:

1. **#1213 — Contract + validator + tests** — schema, example, matrix row,
   contracts doc section, validator discovery, schema/validator tests.
   Bounded; no dependency.
2. **#1214 — Writer/reader + skill + docs** — `session_notes.py`,
   session-handover skill + manifest registration, mechanization-plan
   pointer + coverage metric, cross-repo `latest` tests. Depends on #1213.
3. **#1215 — Hook wiring + coverage automation** — `latest --hook` and
   `stop-gate` entry points, `coverage` report command, `.claude` hook
   entries in this repo, repository-baseline snippet, stop-gate loop/idempotence
   tests. Depends on #1214.

All execute via dispatch-build under the manifest routing above.
