---
name: item-done
description: Use when a sprint item's implementation is complete and verified. Captures knowledge events while context is hot, then marks done and refreshes the snapshot at the right scope boundary.
---

## Goal

Close a sprint item cleanly: confirm verification passes, capture durable knowledge before context cools, update sprint state, and commit at the right scope boundary.

## Inputs

- A completed, verified sprint item with an active claim.
- A loaded project DB via `.envrc` or exported `SPRINTCTL_DB`.
- The `claim_id` and `claim_token` for the current claim.

## Steps

1. **Confirm verification is clean.** Run targeted checks for the files changed in this item — blocking, foreground, fast-fail. Use the repo's verification commands from the dispatch packet, manifest, or overlay. Do not proceed if targeted checks fail; use the self-healing loop (diagnose and fix, up to 5 cycles) before escalating.

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

4. **Mark done and release the claim.**
   ```bash
   sprintctl item done-from-claim --item-id <id> --claim-id <claim-id> --claim-token <token>
   ```
   Remove `.sprintctl/claims/claim-<item_id>.token` after successful close.

5. **Refresh the snapshot** with `sprint-snapshot` after material status changes.

## Output Contract

- Targeted verification passes before the item closes.
- Knowledge events logged while context is hot.
- Item and claim status match live `sprintctl` state.
- Commit made at the scope boundary, not mechanically per item.

## Do Not

- Do not mark done without passing verification.
- Do not skip knowledge event logging to save time — log now or it is lost.
- Do not pass the claim token to subagents; keep it in the orchestrating session and the local recovery file only.
- Do not heartbeat or reuse a claim whose live identity no longer belongs to the current session.
