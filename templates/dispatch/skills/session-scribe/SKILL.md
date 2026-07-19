---
name: session-scribe
description: The canonical periodic scribe (agentops-owned; NOT the scribectl repo). Use at a deterministic trigger point (scheduled dispatch, not ad hoc) to consume unreconciled session-capsule/v1 exhaust for one repo and produce reviewable reconciliation-proposal/v1 artifacts. Never mutates sprintctl state directly.
---

## Goal

Converge the sprint record with what actually happened, on a bounded, visible
cadence — even when no per-session reconciliation ever ran. This is **the
correctness path** per
`docs/plans/agentops/session-mechanization-plan.md`: everything else (Tier 2
immediate reconciliation) is a latency optimization on top of it, not a
substitute for it.

This skill supplies the *judgment* half of the scribe — reading capsules and
classifying what they mean. The *mechanism* half (durable-cursor bookkeeping,
capsule discovery/grouping, schema-validated artifact writing) is
`templates/dispatch/scripts/session_scribe.py`. Use the script for every
mechanical step below; do not hand-roll cursor math or hand-write proposal
JSON from scratch.

## Naming

**This is not `scribectl`.** `scribectl` is an unrelated fiction-writing
contract runner (Obsidian vault pipeline). Do not route this work to, or
confuse it with, that repository.

## Inputs

- Artifact root for the target repo: `_artifacts/<repo>/` (contains
  `session-capsules/*.json`, and this skill's own
  `session-scribe/cursor.json` and `reconciliation-proposals/*.json`).
- Read access to the repo's live sprint projection (`sprintctl item list`,
  `sprintctl item show`, `sprintctl sprint show`) and its watermark/age.
- The repo's dispatch manifest and any linked plan documents, for done
  criteria and scope boundaries.

## Steps

1. **Plan.** Run
   `python templates/dispatch/scripts/session_scribe.py plan --root _artifacts/<repo>`.
   This prints every capsule not yet past the durable cursor, grouped by
   `target.ref` (capsules sharing an explicit or candidate target are grouped
   together; untargeted capsules are singleton groups keyed by
   `capsule:<id>`). An empty `groups` array means nothing to do — stop here.

2. **Check for already-decided ground.** Before classifying a group, scan
   existing `reconciliation-proposals/*.json` under the same root for a
   `rejected` or `superseded` proposal whose `dedup_key` would match what
   this group is about to produce. If one exists and no new evidence changes
   the picture, do not recreate an equivalent proposal — the rejection is
   already durable history. Only propose again if new capsules in the group
   add evidence the prior decision did not have.

3. **Gather context per group**, using only what the group's `target.ref`
   and capsules actually point at — do not paste the whole backlog:
   - `sprintctl item show --id <id>` for an explicit `wi:` target;
   - the touched paths and diff stats from each capsule's `git` block;
   - each capsule's `verification` results;
   - linked plan documents and their done criteria, when the item or its
     refs name one.

4. **Classify each group** into exactly one of the six outcomes from
   `session-mechanization-plan.md` / `session-mechanization-contracts.md`:
   `link-existing-item`, `mark-item-advanced`, `propose-completion`,
   `flag-conflict-or-duplicate`, `propose-new-item`, `incidental-no-change`.
   This is the genuine judgment this skill exists to supply — a group with
   an explicit target, passing verification, and a diff that matches the
   item's done criteria supports high confidence; a group with only
   candidate-rank targets or failing verification does not. Record honest
   `confidence.level` and a `confidence.rationale` that states what evidence
   supports or limits it. When uncertain between two outcomes, prefer the
   less committal one (e.g. `mark-item-advanced` over `propose-completion`)
   — the reviewer decides from here, not the scribe.

5. **Record the outcome**:
   - `incidental-no-change` →
     `session_scribe.py no-change --root <root> --project <repo> --capsule-id <id> --confidence <level> --rationale "<text>"`
     once per capsule in the group (no-change is recorded per capsule, not
     per group, since each capsule is independently "nothing happened
     here").
   - Any other classification → author a proposal JSON with
     `dedup_key`, `source_capsules` (one entry per capsule in the group,
     `capsule_ref` built from the capsule's file path and content —
     `kind: artifact`, `source: <repo>:_artifacts/<repo>/session-capsules/<id>.json`,
     `revision: sha256:<digest of that file>`), `evidence_refs`, `basis`,
     `target`, `classification`, `proposed_commands` (the sprintctl
     authority commands acceptance would run — `item.done`,
     `item.transition`, `sprint.activate`, etc.), and `confidence`. Omit
     `proposal_id`, `created_at`, and `lifecycle` — the script fills those
     in. Then run
     `session_scribe.py emit --root <root> --proposal <path> --consumes <capsule-id> [<capsule-id> ...]`
     listing every capsule the group covers.

6. **Repeat per group**, then re-run `plan` to confirm `unconsumed_count`
   reaches `0` for this pass. `status` gives the reconciliation-lag summary
   (unreconciled count, oldest unreconciled age) for the dogfooding metrics
   in the mechanization plan — surface it in the dispatch summary so lag is
   visible even when this pass fully drains the queue.

## Output Contract

- Every capsule discovered by `plan` at the start of the run either appears
  in a written proposal's `source_capsules` or gets an explicit
  `incidental-no-change` record — no capsule is silently dropped.
- The durable cursor only advances for capsules actually accounted for by a
  written, schema-valid artifact (the script enforces this: `emit` and
  `no-change` validate before they write, and only advance the cursor after
  a successful write).
- No sprintctl authority command executes from this skill. `proposed_commands`
  in a written proposal are what acceptance *would* run — recording the
  proposal is not running it.
- Rejected and superseded proposals stay on disk as durable history; they are
  never deleted or overwritten to make room for a fresh attempt.

## Do Not

- Do not call any `sprintctl item done`, `item transition`, `sprint activate`,
  or claim-mutating command from this skill. Proposals are reviewed and
  accepted through normal sprintctl authority commands by a separate action
  — see `write-surface-policy.md`.
- Do not hand-write `proposal_id`, `dedup_key` collisions, or cursor state
  by editing JSON files directly — use the script's `emit`/`no-change`/`plan`
  subcommands so validation and cursor advancement stay atomic.
- Do not merge unrelated capsules into one group because it is convenient;
  group only by the mechanical `target.ref` signal the script already uses.
- Do not treat a `low`-confidence classification as a reason to skip
  recording it. Low confidence is a legitimate, reviewable outcome —
  silence is not.
- Do not assign this work to, or describe it as, the `scribectl` repository.

## Related documents

- `docs/plans/agentops/session-mechanization-plan.md` — product direction,
  Tier 0/1/2, dogfooding metrics, cockpit surfaces.
- `docs/dispatch/session-mechanization-contracts.md` — `session-capsule/v1`
  and `reconciliation-proposal/v1` field contracts.
- `docs/plans/agentops/state-event-command-matrix.md` — per-event
  classification and ownership.
- `docs/plans/agentops/write-surface-policy.md` — which surfaces may execute
  the sprintctl authority commands a proposal names.
- `templates/dispatch/scripts/session_scribe.py` — the mechanical half this
  skill drives.
