---
name: session-handover
description: Write a durable session-note/v1 instead of pasting a handover or /clear summary forward, and read the latest relevant note back in at session start. Use whenever a session is ending, being /clear-summarized, or starting fresh in a repo that participates in session-mechanization.
---

## Goal

Give a session's authored handover, summary, or outcome a durable,
cross-session, cross-repo home instead of living only in a forwarded prompt
or a transcript nobody re-reads. This is the **semantic** half named in
`docs/plans/agentops/session-note-contract-plan.md`: the session-capsule
mechanism captures *that* a session happened, mechanically; this skill
captures *what it means to pick up here*, in the agent's own words.

This skill supplies the judgment half — deciding what belongs in the note and
which kind it is. The mechanism half (schema-valid writing, supersedes-chain
resolution, cross-repo lookup) is
`templates/dispatch/scripts/session_notes.py`. Use the script for every
mechanical step; do not hand-write note JSON.

**Known tension, named deliberately**: recording a note here is still an
*instruction* the agent has to remember to follow, not a mechanism that
enforces it. Hook wiring that makes capture automatic (`stop-gate`) is
AgentOps #1281, not yet built. Until it lands, this skill is the entire
enforcement surface — treat it as load-bearing, not optional, for now.

## At session start

1. Determine this repo's artifact root: `_artifacts/<repo>/` (matching this
   repo's own name in the project's member list).
2. Check whether a `SessionStart` hook has already injected the latest note.
   The injected form begins with a deterministic sentinel line carrying the
   note's `note_id` — check for that line **by string match**, not judgment.
   If a hook is wired in this repo and already injected it, skip to step 3;
   there is no #1281 hook in this repo yet, so this step is currently always
   a fallback.
3. If nothing was injected, run:
   ```
   python templates/dispatch/scripts/session_notes.py latest \
     --root _artifacts/<repo> --kind handover
   ```
   If nothing comes back, there is no prior handover — proceed normally. If
   a note comes back, read its `body` before doing anything else; it is the
   prior session's "pick up here."
4. For project-wide context spanning multiple member repos, repeat the
   `latest` call once per member's artifact root (`--root` is repeatable) —
   see `resolve_latest_multi` in the script for the cross-repo resolution
   rule (per-repo chain resolved first, then newest wins across repos).

## At session end, /clear, or hand-off

1. Decide the note's `kind` using this rule, not vibes:
   - **`handover`** — this thread is ending and a *different* session, agent,
     or day is expected to resume it. The common case.
   - **`summary`** — same-thread context compression (e.g. approaching a
     context limit) where the current session continues; there is no
     hand-off to a different actor.
   - **`outcome`** — a bounded unit of work concluded (shipped, rejected,
     abandoned) and the note's job is recording what happened, not how to
     continue.
   If genuinely torn between `handover` and `summary`, ask: "will whoever
   reads this next be a different conversation?" Yes → `handover`.
2. Write the note **instead of** pasting the summary forward as prompt text:
   ```
   python templates/dispatch/scripts/session_notes.py append \
     --root _artifacts/<repo> --repo <repo> --kind <handover|summary|outcome> \
     --body "<markdown, under 16 KiB>" \
     [--target-refs wi:<id> ...] \
     [--supersedes <note_id of the note this one replaces>] \
     [--runtime-session-id <id, when available>]
   ```
3. Set `--supersedes` to the note_id from step 3 above when this session read
   one at start and is now producing its replacement — that is what keeps
   the `/clear` chain connected. Omit it when there was nothing to supersede,
   or when this note does not replace a prior one (e.g. a second concurrent
   session's independent handover).
4. Body content: what state was reached, what remains, and anything a fresh
   reader needs that isn't already in committed code or the sprint record.
   Do not restate what `sprintctl item show` or `git log` already say more
   authoritatively. Never include transcripts or credentials — `privacy` is
   deliberately conservative by default (`raw_transcript_captured: false`).
5. `/clear` and session-end fire after the conversation can no longer act, so
   writing the note is the **last thing** this skill does in a turn, not
   something deferred.

## Do not

- Do not paste a handover/summary forward as prompt text *and* write a note
  for the same content — the note replaces that habit, it does not
  supplement it.
- Do not hand-roll note JSON or bypass `session_notes.py`'s validation.
- Do not use `governance` or `process-observation` as a kind — only
  `handover`, `summary`, and `outcome` exist in `session-note/v1`.
- Do not treat a note as authoritative backlog state. A note that implies a
  backlog change still goes through the existing scribe →
  `reconciliation-proposal/v1` path; this skill never mutates sprintctl.
- Do not write a note through anything other than `session_notes.py` — do not
  call sprintctl authority commands from this skill.

## Related documents

- `docs/plans/agentops/session-note-contract-plan.md` — the current design
  this skill implements (Phase 1 scope, operator decisions).
- `docs/dispatch/session-mechanization-contracts.md` — the `session-note/v1`
  field contract.
- `templates/dispatch/scripts/session_notes.py` — the mechanical half this
  skill drives.
- `templates/dispatch/skills/session-scribe/SKILL.md`,
  `templates/dispatch/skills/session-reconciler/SKILL.md` — the adjacent
  capsule-reconciliation paths this contract deliberately does not duplicate.
