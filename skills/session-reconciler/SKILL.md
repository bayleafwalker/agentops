---
name: session-reconciler
description: Fresh post-session reconciler (Tier 2 latency-optimization path). Use when dispatched immediately after one session ends, with that session's capsule id, to reconcile it now instead of waiting for the canonical periodic scribe. Never mutates sprintctl state directly; the scribe remains the correctness path.
---

## Goal

Give one just-ended session a reconciliation outcome *now*, instead of at the
next periodic scribe pass. This is the **latency optimization** described in
`docs/plans/agentops/session-mechanization-plan.md` (Tier 2): if this skill
never runs, nothing is lost — the canonical periodic scribe
(`skills/session-scribe/SKILL.md`) converges the record anyway. Never treat
this path as load-bearing for correctness.

This skill supplies the *judgment* half — classifying what one capsule means.
The *mechanism* half (idempotence guards, single-capsule scope enforcement,
shared-cursor bookkeeping, schema-validated artifact writing) is
`templates/dispatch/scripts/session_reconciler.py`, which delegates to
`session_scribe.py` under the hood. Use the script for every mechanical step;
do not hand-roll cursor math or proposal JSON.

## Relationship to the scribe

- **Shared cursor.** Both paths advance the same durable cursor at
  `<root>/session-scribe/cursor.json`. A capsule reconciled here is invisible
  to the scribe, and vice versa. There is no double-processing by
  construction.
- **Single-capsule scope.** The reconciler handles exactly the capsule it was
  dispatched for. Grouping related sessions is the scribe's job; the script's
  `emit` refuses multi-capsule proposals.
- **You are fresh by design.** Do not run this skill from the session that
  did the work — the whole point of Tier 2 is that the exhausted primary
  agent never does its own bookkeeping.

## Inputs

- The capsule id of the just-ended session (from the dispatch payload or the
  Tier-0 wrapper's exhaust).
- Artifact root for the target repo: `_artifacts/<repo>/`.
- Read access to the repo's live sprint projection (`sprintctl item list`,
  `sprintctl item show`, `sprintctl sprint show`) and its watermark/age.
- The repo's dispatch manifest and any linked plan documents, for done
  criteria and scope boundaries.

## Steps

1. **Assemble context.** Run
   `python templates/dispatch/scripts/session_reconciler.py context --root _artifacts/<repo> --project <repo> --capsule-id <id>`.
   - `status: already-consumed` → **stop**. The scribe or a prior reconciler
     run already accounted for this capsule; a re-trigger is a clean no-op.
   - `status: ready` → the packet contains the capsule's target, reservation, git
     evidence, verification results, starting watermark, any
     `related_unconsumed_same_target` siblings, and any `existing_proposals`
     already referencing this capsule.

2. **Decide whether to defer to the scribe.** If
   `related_unconsumed_same_target` is non-empty, other unreconciled sessions
   share this capsule's target. Reconciling one capsule of a group in
   isolation can misjudge progress (e.g. proposing completion when a sibling
   session's failing verification says otherwise). Prefer to **stop and
   leave the whole group for the scribe** unless this capsule's outcome is
   clearly independent of its siblings. Leaving the capsule unconsumed is a
   legitimate outcome of this skill — it stays visible to the scribe, whose
   cadence bounds the added latency.

3. **Check for already-decided ground.** If `existing_proposals` (or a scan
   of `reconciliation-proposals/*.json` for a matching `dedup_key`) shows a
   `rejected` or `superseded` proposal covering what this capsule would
   propose, do not recreate it unless this capsule adds evidence the prior
   decision did not have.

4. **Gather sprint context**, using only what the capsule actually points
   at — do not paste the whole backlog:
   - `sprintctl item show --id <id>` for an explicit `wi:` target;
   - the touched paths and diff stats from the capsule's `git` block;
   - the capsule's `verification` results;
   - linked plan documents and their done criteria, when the item or its
     refs name one.
   Note the capsule's `starting_watermark.age_seconds`: a very stale
   watermark means the session may have acted on an outdated projection —
   weigh conflicts accordingly.

5. **Classify the capsule** into exactly one of the six outcomes from
   `session-mechanization-contracts.md`: `link-existing-item`,
   `mark-item-advanced`, `propose-completion`, `flag-conflict-or-duplicate`,
   `propose-new-item`, `incidental-no-change`. Same judgment standard as the
   scribe: explicit target + passing verification + diff matching done
   criteria supports high confidence; candidate-rank targets or failing
   verification do not. When uncertain between two outcomes, prefer the less
   committal one — the reviewer decides from here, not the reconciler.

6. **Record the outcome**:
   - `incidental-no-change` →
     `session_reconciler.py no-change --root <root> --project <repo> --capsule-id <id> --confidence <level> --rationale "<text>"`.
   - Any other classification → author a proposal JSON exactly as the scribe
     skill describes (dedup_key, one `source_capsules` entry using the
     `capsule_ref` the `context` packet already computed, evidence_refs,
     basis, target, classification, proposed_commands, confidence; omit
     `proposal_id`/`created_at`/`lifecycle`), then
     `session_reconciler.py emit --root <root> --proposal <path> --capsule-id <id>`.

## Output Contract

- At most one capsule is consumed per run, and only when a schema-valid
  proposal or no-change record was written for it.
- A re-triggered run for an already-consumed capsule exits cleanly without
  writing anything (the script enforces this).
- Deferring to the scribe (leaving the capsule unconsumed) is a recorded
  decision in the dispatch summary, not a silent skip.
- No sprintctl authority command executes from this skill. `proposed_commands`
  are what acceptance *would* run — recording the proposal is not running it.

## Do Not

- Do not call any `sprintctl item done`, `item transition`, `sprint activate`,
  or reservation-mutating command from this skill — see `write-surface-policy.md`.
- Do not fold sibling capsules into the proposal to "save a scribe pass";
  the single-capsule scope is what keeps the latency path simple and safe.
- Do not advance or edit cursor state by hand — only through the script.
- Do not treat this path as required. If it is unavailable, broken, or
  ambiguous, leaving the capsule for the scribe is the correct move.
- Do not route this work to, or confuse it with, the `scribectl` repository
  (an unrelated fiction-writing contract runner).

## Related documents

- `docs/plans/agentops/session-mechanization-plan.md` — Tier 2 and the
  scribe-as-correctness-path posture this skill implements.
- `docs/dispatch/session-mechanization-contracts.md` — `session-capsule/v1`
  and `reconciliation-proposal/v1` field contracts.
- `templates/dispatch/skills/session-scribe/SKILL.md` — the periodic
  correctness path; shares the six-outcome judgment standard.
- `templates/dispatch/scripts/session_reconciler.py` — the mechanical half
  this skill drives.
- `docs/plans/agentops/write-surface-policy.md` — which surfaces may execute
  the sprintctl authority commands a proposal names.
