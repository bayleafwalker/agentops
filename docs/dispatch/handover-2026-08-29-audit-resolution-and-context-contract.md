# Handover — audit resolution, the resolved-context contract, and what is owed

**Date:** 2026-08-29 · **Supersedes:** nothing; this is a continuation of
`handover-2026-08-29` work recorded in note 3d86fae2 (commit 97920ba).

## Landing status

| Repo | Branch | HEAD | State |
|---|---|---|---|
| auditctl | main | `269f98e` | clean, pushed |
| agentops | main | `84de5c4` | clean, pushed |
| vuoro | main | `cf40bff` | clean, pushed |
| appservice | main | `5f6f4c7` | clean, pushed (advanced past this session's `1e47ede`) |
| gitops-nixos | main | `f7405e1` | clean, pushed |
| sprintctl | main | `95e18f5` | clean, pushed (unchanged this session) |
| homelab-analytics | main | `eb56331` | clean, pushed (unchanged this session) |
| scribectl | main | `07ae91b` | clean, pushed (unchanged this session) |

Nothing is parked in a PR. One branch was pushed for preservation only:
`agentops devbox/worktree-snapshot-2026-07-21` — see *Open items*.

## Releases

| Artifact | Version | State |
|---|---|---|
| auditctl | **0.1.4** | released, installed on the workstation |
| auditctl | 0.1.5 | **not cut** — carries the `--allow-index-only` continuity fix; gate is green |
| vuoro-service | 0.1.57 | released, image `sha256:45ac582e…` |
| vuoro-shared | — | rolled to 0.1.57, live handshake confirms |

Production runs auditctl **0.1.3** through the vuoro composition. 0.1.4 and the
unreleased 0.1.5 work are workstation-only so far.

## What got done

**The audit misrouting, fixed at the cause.** `artifacts-root.default` named one
repository and the hook that reads it is symlinked into every repo, so each session
indexed at its own root and appended under agentops. Fixed by deriving the root from
the publishing session (`5757779`), then corrected again when the first fix stopped at
the nearest `.git` and re-created the defect one directory higher in `appservice`
(`a44f01d`). 13 events recovered, verified by set and digest equality.

**`AuditContext`** (`380a5d3`, `5a8ded2`, `89abbf5`) — identity, index and artifacts
root resolved once, atomically, failing closed on contradiction, and attributed. The
root now *defaults* to the resolved repository, which removes the defect's precondition
rather than detecting its symptom. Rule is ancestor-or-equal, not equality: pooled and
co-rooted are both live conventions. Identity no longer comes from the directory name —
worktrees resolve to their main repository and a repo may declare `.auditctl-id`.

**Test isolation** (`b55df7e`) — the suites were writing fixture events into the live
agentops index, measured at +7 (hook) and +3 (python) per run. Both now move it by zero.

**Stores repaired.** agentops rebuilt from authoritative shards (600 kept, 36 fixtures
discarded), gitops-nixos co-rooted into the repository (`f7405e1`). Seven of eight
stores now pair clean; the table is in the contract.

**The contract** — `docs/contracts/session-resolved-context.md`. Four objects, the
resolved-context invariant split by lifetime, ownership boundary, falsifiers, and the
measured fleet state.

## Open items

### 1. nix-daemon is failed — operator, owned by another session

`sudo systemctl restart nix-daemon` was run; the unit is now **failed**, exit status 1
after 48ms, and it logs **nothing** to the journal for that invocation. The stale socket
at `/nix/var/nix/daemon-socket/` was removed by the attempt and nothing is listening now.

The most useful next command is running it in the foreground as root to see the error
the unit is swallowing:

```bash
sudo /usr/bin/nix-daemon --daemon
```

Note that logging nothing is itself a symptom, and it may share a cause with the
original fault (connections reset before `accept()`, daemon logging nothing for them).

**This does not block anything.** `nix shell` needs the daemon; an already-realized
store path does not:

```bash
PGBIN=$(for d in /nix/store/*postgresql-18*/bin; do
          [ -x "$d/initdb" ] && [ -x "$d/pg_ctl" ] &&
          "$d/postgres" --version | awk -v p="$d" '{print $3, p}'
        done | sort -V | tail -1 | awk '{print $2}')
PATH="$PGBIN:$PATH" .venv/bin/python -m pytest tests/ -q     # 133 passed, 1 skipped
```

### 2. `agentops devbox/worktree-snapshot-2026-07-21` needs a decision

devbox held 21 modified tracked files and one untracked test, mtimes 2026-07-18..21,
never committed, single copy on a host with no backup. Ten were byte-identical to main;
**12 genuinely differ**. Snapshotted and pushed so the clone could be fast-forwarded.
Whether any of the 12 carries intent worth landing is unanswered — it needs a reader,
not a script.

### 3. `homelab-analytics` is split and irreducible

One stream across two roots, sequences interleaved, 21 events all on disk. Cannot be
reconciled without violating append-only. Its gate reports 17 index-only, and that
number means *"two roots"*, not *"lost"*. Documented in the contract; no action.

### 4. devbox has no `~/.claude/CLAUDE.md`

Its `AGENTS.md` is now rendered and current, but the home working-agreements file does
not exist for the `agent` identity at all.

## Next steps, in order

1. **Finding 2 — context delivery.** A wrong-but-*coherent* pair still passes:
   `AUDITCTL_DB` alone pointing elsewhere routes both halves there consistently. The
   real class is config *scoping*, and context still arrives through environment
   variables that shared-scope code can overwrite. **This is the precondition for the
   applier** — an applier that receives its context through a channel shared-scope code
   can write inherits the defect no matter how well it is built.
2. **Cut auditctl 0.1.5.** The gate is green including the central verification. Then
   repin the vuoro composition, release vuoro-service, roll vuoro-shared — production is
   still on 0.1.3.
3. **Retire the bash resolver** (`auditctl-resolve.sh` root derivation) once 0.1.5 is
   deployed. It cannot change an outcome any more; it can only fail closed when its walk
   drifts from the Python one. `artifacts-root.default` dies in the same step.
4. **Render `~/.claude/CLAUDE.md`** to devbox — the one live guidance gap.

## Long goal state

A **portable, file-backed contract with one implementation**, so a new executor inherits
the pattern rather than re-deriving it:

- **Project / Workspace / Session / Environment** as distinct objects. Three already
  exist (`project.toml`, `_projects/<name>/project.context.json`,
  `environment-record/*.json`); Session is the one never *produced*, though fragments
  exist (lease identity, `runtime_session_id`, the session-capsule schema).
- **Vuoro defines and resolves; it does not distribute bytes.** Config that gates
  bootstrap cannot depend on a served endpoint being reachable. Git already replicates
  agentops to every agent host — the missing piece is render/apply/drift-check, not
  transport.
- **One generic transactional applier** — render to staging, validate, atomically
  replace, emit a receipt, retain the previous for rollback. It must *absorb*
  `materialize_project.py` and nix activation, both of which already implement this,
  rather than becoming a third.
- **Triggers stay per-host and dumb** — nix activation, systemd user units. That
  difference is cheap and irreducible; the definition and the applier are not.
- **auditctl records conformance; it never states desired state.**
- **Promote to vuoro's served schema only on evidence** — after the contract has run on
  the workstation, devbox, and one clean disposable executor, including at least one
  case where it *rejected* something it should have.

## The methodological finding, which outranks the rest

**Three times in one session, a confident conclusion came from pairing evidence with
the wrong scope.**

1. "40 index-only events, four publishers, unbacked" — an index compared against another
   scope's shards. Retracted.
2. The retraction then **overcorrected**: there really were 36 index-only events. Both
   the claim and its withdrawal were wrong, in opposite directions.
3. "86 orphaned worktree events needing an attribution decision" — test fixtures
   (`sess-a`, `sess-poison`, `x`, `y`), identified by two independent passes as
   production residue because nobody opened a row until the third.
4. The fleet sweep's first run reported five false index-only stores — the pooled repos,
   swept with the default root.

And separately, a capability was recorded as blocked because one route to it was
unavailable, for the second time on the same page (`8442a17` was the first).

The rule now written into the contract and the runbook: **pair evidence with its own
scope before believing what it says about the world, and check whether what you need is
already on disk before recording a blocker.** A `rebuild` message reads as data loss
whether or not any data was lost; the tool cannot tell you which, and neither can a
second reader who inherits the framing.
