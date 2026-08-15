---
name: item-done
description: Use when a sprint item's implementation is complete and verified. Captures knowledge events while context is hot, then marks done and refreshes the snapshot at the right scope boundary.
---

## Goal

Close a sprint item cleanly: confirm verification passes, capture durable knowledge before context cools, update sprint state, and commit at the right scope boundary.

If sprintctl mutation is not allowed in the current session, do not half-complete this workflow; report the blocked closeout steps explicitly instead.

## Inputs

- A completed, verified sprint item with an active reservation.
- A loaded project DB via `.envrc` or exported `SPRINTCTL_DB`.
- The reservation `id` for the current session.

## Steps

1. **Confirm verification is clean.** Run targeted checks for the files changed in this item — blocking, foreground, fast-fail. Use the repo's verification commands from the dispatch packet, manifest, or overlay. For pytest projects, a focused command should normally use `pytest <targeted-tests> -x --tb=short`. Do not proceed if targeted checks fail; use the self-healing loop (diagnose and fix, up to 5 cycles) before escalating.

2. **Reflect — log knowledge events while context is hot.** Before marking done, ask: did any of these happen?
   - A design choice was made between two viable options
   - A blocker was resolved by a non-obvious fix
   - A pattern emerged that applies to other items or future sprints
   - A migration or schema decision was made
   - An integration failure revealed a wrong assumption

   If yes, log it now:
   ```bash
   sprintctl event add --sprint-id <id> --item-id <item-id> \
     --type <decision|lesson-learned> --actor <actor> \
     --payload '{"summary":"<one sentence>","detail":"<reasoning>","tags":["<tag>"],"confidence":"<high|medium|low>"}'
   ```
   Include `summary` and `detail` at minimum. If nothing non-obvious happened, skip this step.

3. **Commit at the right scope boundary.** Use one commit per reviewable scope. Commit when this item closes a tight, related scope. Do not commit mechanically per item; do not bundle unrelated work.

4. **Mark done, then release the reservation.**
   ```bash
   sprintctl item status --id <id> --status done --expected-revision <revision>
   sprintctl reservation release --id <reservation-id> --actor <actor>
   ```
   Read `<revision>` from `sprintctl item show --id <id> --json`. These are two operations: the transition is guarded by the revision compare-and-swap, and releasing is a separate coordination signal. There is no token file to clean up.

5. **Refresh the snapshot only when it is needed now.** If updated sprint state must be shared immediately (handoff, end-of-batch, review handoff, sprint close), run `sprint-snapshot`. Otherwise stop after the release and batch the refresh at the next natural milestone instead of creating a mechanical per-item snapshot commit.

## Output Contract

- Targeted verification passes before the item closes.
- Knowledge events logged while context is hot.
- Item status and reservation state match live `sprintctl` state.
- Commit made at the scope boundary, not mechanically per item.

## Do Not

- Do not mark done without passing verification.
- Do not skip knowledge event logging to save time — log now or it is lost.
- Do not release another session's reservation as part of finishing your own work.
- Do not background a verification command whose exit status gates item closeout.
- Do not manufacture events if nothing non-obvious happened; one honest event beats three thin ones.
- Do not omit `--expected-revision`; a direct transition requires it, and it is what makes a stale basis fail closed.
- Do not silently skip the done transition, the release, or a required snapshot refresh; if state mutation is unavailable, report the block instead.
