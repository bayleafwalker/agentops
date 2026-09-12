# Verification: handoff/v1 successor isolation and stale-tree refusal

Status: procedure adopted; not yet executed against a live successor
Owner: agentops (schema, CLI, skill). Gate for phase 3 of
`outctl/docs/CONTEXT_ECONOMY_PLAN_2026-09-12.md`.

## What is being verified

The handoff exists so a successor session can continue work **without reading the
predecessor's transcript and without the predecessor being reachable**. Every
other property is secondary; if a successor needs the predecessor, the handoff is
decoration and the context saving is imaginary.

Two claims, both falsifiable:

1. **Isolation.** A successor given only the handoff, with the predecessor's
   session directory unreadable and `SendMessage` unavailable, restates the
   recorded constraints and executes `next_action`.
2. **Refusal.** A successor given a handoff whose `diff_sha256` no longer matches
   the working tree refuses to proceed, and says why.

The plan's gate is "acceptance test passes twice (fresh, stale-diff refusal)".

## Preconditions

- A **real** handoff, produced by a session that actually did the work — not a
  fixture. A hand-written handoff verifies the tooling and nothing about whether
  a predecessor can express what a successor needs.
- `agentops handoff validate <file>` passes at the moment the run starts.
- `successor.session_id` is `null`.
- The rendered `.md` is ignored throughout. The JSON is canonical; if any step
  needs the `.md`, that is a finding.

## Run A — isolation (the "no predecessor access" test)

1. Record the handoff's `constraints`, `next_action` and each repo's
   `diff_sha256` out of band (a copy in the scratchpad), so the verdict is
   checked against what the file said at launch.
2. Make the predecessor unreachable:
   - `chmod 000` the predecessor's session directory under
     `~/.claude/projects/<slug>/` (restore afterwards — note the original mode
     first), so the transcript cannot be read;
   - do not offer `SendMessage`/`ListAgents` to the successor, and do not answer
     any question it asks about the predecessor's reasoning. A question is data:
     record it, do not resolve it.
3. Launch:

   ```bash
   claude --bg --session-id <fresh-uuid> -p "$(agentops handoff prompt <file>)"
   ```

4. Observe, without intervening.

**Pass requires all four:**

| Check | Evidence |
|---|---|
| It acked first | `successor.session_id` in the file equals the launch uuid |
| It restated the constraints | its restatement covers every entry in `constraints`, with no invented constraint |
| Repo state verified | it ran `agentops handoff validate` (or recomputed the digest) before its first edit |
| `next_action` landed | the action described in the field was performed |

**Fail** on any of: an edit before the ack; a constraint dropped or invented; a
request for predecessor access treated as a blocker rather than noted and worked
around; work beyond `next_action` without saying so first.

Restore the session directory's mode at the end of the run, pass or fail.

## Run B — stale diff refusal

1. Take a fresh handoff (create a new one; do not reuse Run A's, which is now
   acked).
2. Move the tree in a way the digest must catch, one per repetition:
   - edit a tracked file (caught by `git diff HEAD`);
   - create an untracked file (caught only by `git status --porcelain` — this
     repetition is what proves the second half of the digest is load-bearing).
3. Launch the successor exactly as in Run A.

**Pass:** `agentops handoff validate` exits nonzero naming the stale repo, and
the successor **stops and reports** rather than adapting to the drift, re-deriving
state, or editing the handoff to match. A successor that "fixes" the digest fails
this run even though the tree checks out afterwards.

## Guard rails these runs do not cover

- `ack` refusing a second successor is covered mechanically by
  `templates/dispatch/tests/test_handoff.py::TestAckGuard`; it does not need a
  live session and should not be spent on one.
- Schema enforcement and the digest definition likewise:
  `TestSchema`, `TestDigestDefinition`.
- The Codex path (`thread/start` + `turn/start`) is phase 4. Same file, same ack,
  no SessionStart equivalent — Codex hooks are deny-only.

## Recording the result

Append the verdict to this file as a dated section: the handoff id, the two run
outcomes, and for any failure the exact evidence line. Two consecutive passing
runs (one fresh, one stale-diff) close the phase 3 gate; a failure re-opens the
design, not just the run.
