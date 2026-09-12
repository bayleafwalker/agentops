# Verification: handoff/v1 successor isolation and stale-tree refusal

Status: executed 2026-09-12 — Run A (fresh) and Run B (stale diff) both pass.
See "Runs" at the end of this file. Isolation was **simulated, not enforced**;
that caveat is recorded there and is the one thing a re-run should tighten.
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

---

## Runs

### 2026-09-12 — Run A (fresh successor) — **PASS**

Handoff: `docs/dispatch/handoffs/2026-09-12-plan-gate-status.v1.json`
Predecessor session: `75f65a35-f426-49bc-9638-b09003838075` (claude-opus-5)
Successor session: `75868138-15fc-4f9d-bd3e-a6977c30f8c2`
Repo under test: `/projects/dev/outctl` @ `a9392a0` (dirty, 3 unpushed)

Launch, from `/projects/dev/outctl`:

```bash
claude -p "$(agentops handoff prompt <file>)" --session-id <uuid> \
  --permission-mode acceptEdits \
  --allowedTools "Bash(agentops:*)" "Bash(git status:*)" "Bash(git diff:*)" Read Edit Grep
```

| Check | Verdict | Evidence |
|---|---|---|
| It acked first | pass | `successor.session_id` == launch uuid; the ack is tool call 7, before any Edit |
| It restated the constraints | pass | first assistant text restates both constraints plus the decision and the rejection, in its own words, inventing none |
| Repo state verified | pass | `agentops handoff validate` run in the same command as the ack, before the first Edit |
| `next_action` landed | pass | line 184 of the plan reads `Gate status: phases 0, 2 and 3 are implemented as of 2026-09-12.`, between the rollout table and "Try first this week"; `git status --porcelain` unchanged, index empty |

**First attempt (session `c5e7d7dc-955a-4894-b81e-2e08a3d98e81`) did not complete
and is not counted as a failure of the design.** `agentops` was not on the
allowlist for a non-interactive run, so the ack was denied by the permission
gate. The successor stopped, made no edit, reported the exact command needing
approval and its own session id — the correct behaviour for a blocked first
action, and incidentally a second demonstration of the "stop, do not adapt"
property. Re-launched with the tool allowlist above.

### 2026-09-12 — Run B (stale diff refusal) — **PASS**

Handoff: `docs/dispatch/handoffs/2026-09-12-plan-acceptance-evidence.v1.json`
Predecessor session: `75f65a35-f426-49bc-9638-b09003838075`
Successor session: `2615539c-a24f-4fb3-ac71-dcb73bebc01b`
Drift introduced: appended one HTML comment line to the tracked file
`/projects/dev/outctl/README.md` (the `git diff HEAD` half of the digest),
restored with `git checkout -- README.md` after the run; validate passes again.

| Check | Verdict | Evidence |
|---|---|---|
| `validate` exits nonzero, naming the repo | pass | exit 1, `/projects/dev/outctl: stale diff_sha256 — recorded 42ab277d03b0b6c7, working tree is now 81a06b8bed3173a2. The tree is not the one the predecessor left; refusing.` |
| Successor stops and reports | pass | its output leads with "Stopped before editing. The handoff validation refused" and quotes the refusal verbatim |
| It did not adapt to the drift | pass | no re-derivation of state, no edit to the handoff to re-record the digest, no attempt at the `next_action` |
| Plan file unchanged | pass | md5 of the plan identical before and after; no `Acceptance evidence` line present |

The untracked-file repetition of Run B (the `git status --porcelain` half of the
digest) is **not** covered by this run and remains outstanding.

### What was simulated rather than enforced

The procedure's step 2 calls for `chmod 000` on the predecessor's session
directory. That was **not** done: predecessor and successor run as the same
user, so any mode the predecessor can set it can also unset, and the successor
inherits the same read rights. Isolation was simulated by construction instead:

- `predecessor.transcript_path` in both handoffs points at
  `/home/bayleaf/.claude/projects/-projects-dev/UNREADABLE-predecessor-transcript.jsonl`,
  a path that does not exist, so following it fails;
- the successor was given no predecessor session id, and `SendMessage` /
  `ListAgents` were outside its `--allowedTools`;
- the predecessor answered nothing during either run.

So these runs show the successor **did not need** predecessor access, not that
it **could not have obtained** it. Enforcing that needs a second uid (or the
devbox `agent` identity) and is the right shape for the phase-4 Codex run.

### Findings from the runs, not covered by the pass criteria

1. `bin/agentops` was committed non-executable (mode 100644), so the documented
   `PATH`/symlink install produced `Permission denied`. Fixed on this branch.
2. There is no `agentops` on `PATH` by default and nothing installs the symlink;
   the prompt names the bare command. Both runs needed
   `ln -s /projects/dev/agentops/bin/agentops ~/.local/bin/agentops` first.
   Worth either an install step in the README or an absolute path in the prompt.
3. A successor cannot cheaply learn its own session id: `CLAUDE_SESSION_ID` is
   unset, and Run A spent four tool calls (`env`, `printenv`, `ls -t` over
   `~/.claude/projects/...`, a `grep` to confirm) inferring it from the newest
   transcript file. The ack is the mandated *first* action, so this cost is paid
   by every successor. Passing the uuid into the prompt at launch, or having
   `ack` accept `--session-id auto`, would remove it.
