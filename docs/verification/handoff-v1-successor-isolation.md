# Verification: handoff/v1 successor isolation and stale-tree refusal

Status: executed 2026-09-12 — Claude Code Run A (fresh) and Run B (stale diff)
pass; Codex Run C (fresh) and Run D (stale diff, untracked-file half) pass.
See "Runs" at the end of this file. Isolation was **simulated, not enforced**,
on all four runs; that caveat is recorded there, and the procedure for the
enforced run is written up under "Enforced isolation (pending devbox
rollout)". Both findings the runs produced about the mechanism itself — the
digest's blindness to untracked *content*, and the ack guard becoming two files
once two hosts are in play — were fixed on this branch (`state.digest_version`
2, and an origin-host ack over ssh); each is written up where it was found.
Owner: agentops (schema, CLI, skill). Gate for phases 3 and 4 of
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
  no SessionStart equivalent — Codex hooks are deny-only. Executed as Runs C and
  D below; the request construction is pinned by
  `templates/dispatch/tests/test_handoff_codex.py` against a mocked transport,
  so a protocol rename fails in CI rather than halfway through a launch.

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

### The Codex launch path (phase 4) — how Runs C and D were driven

`templates/dispatch/scripts/handoff_codex.py`, over `codex app-server --stdio`
(codex-cli 0.153.4), newline-delimited JSON-RPC 2.0 in a subprocess. **No
daemon is needed**: `--listen stdio://` is the default, so `app-server daemon`
was never started and nothing had to be torn down. Methods actually used:

| Method | Used for | Behaved as documented |
|---|---|---|
| `initialize` + `initialized` notification | handshake | yes; answers `{userAgent, codexHome, platformFamily, platformOs}` |
| `thread/start` | new successor thread | yes; answers `{thread:{id, path, cwd, model, status, turns:[]}, …}`. The rollout file path in `thread.path` is the transcript |
| `turn/start` | the rendered handoff as the first user message | **partly** — it returns as soon as the turn is *created* (`{"turn":{"status":"inProgress","items":[]}}`), not when it finishes. Completion arrives as a `turn/completed` notification; output arrives as `item/completed`. A client that treats the response as the answer sees an empty turn |
| `thread/read` | successor transcript access without resuming | **no, not as the plan assumed** — see below |
| `thread/resume` | `consult` | yes, immediately followed by a `turn/start` |

**`thread/read` does not return history on 0.153.4.** `includeTurns: true`
answers `-32601 list_turns is not supported yet`; so do both documented
replacements, `thread/turns/list` and `thread/items/list`
(`-32601 … is not supported yet`). A metadata-only `thread/read` succeeds and
returns `thread.turns: []` and `thread.status.type: "notLoaded"`. So `read`
takes the rollout `.jsonl` path out of the metadata and parses it. That is
still "without resuming" in the sense the plan cares about — no model call, no
context billed, the thread stays `notLoaded` — but it reads a file rather than
asking the server, and it will need revisiting when the paginated APIs land.
The plan's sentence "`thread/read` for transcript access without resuming"
should be read as an intent, not a working call.

Sandboxing: `thread/start` takes a `sandbox` mode string; the per-turn
`sandboxPolicy` object is what carries `writableRoots`, and the launcher sets
them to the handoff's repos **plus the handoff file's own directory** — the
successor's mandated first action writes an ack to a file outside the repo it
is editing. `approvalPolicy: "never"` throughout; a server-initiated approval
request is answered with an error rather than awaited, so a launch cannot hang
on an approval nobody is present to grant.

### 2026-09-12 — Run C (fresh successor, Codex) — **PASS**

Handoff: `docs/dispatch/handoffs/2026-09-12-codex-acceptance-fresh.v1.json`
Predecessor session: `75f65a35-f426-49bc-9638-b09003838075` (claude-opus-5)
Successor thread: `01a09576-febc-7e82-9997-3b14132b342d` (codex, `gpt-6-astra`)
Rollout: `~/.codex/sessions/2026/09/12/rollout-2026-09-12T14-53-18-01a09576-febc-7e82-9997-3b14132b342d.jsonl`
Repo under test: `/projects/dev/outctl` @ `a9392a0` (dirty, 3 unpushed)

```bash
python3 templates/dispatch/scripts/handoff_codex.py launch \
  docs/dispatch/handoffs/2026-09-12-codex-acceptance-fresh.v1.json --timeout 600
```

| Check | Verdict | Evidence |
|---|---|---|
| It acked first | pass | `successor.session_id` == the launched thread id; the ack is command **1 of 4**, before any read and before the edit |
| It restated the constraints | pass | its opening message covers all three (no push/commit, only the plan file and not the index, bounded reads), in its own words, inventing none |
| Repo state verified | pass | `agentops handoff validate` is command 3, before the file change |
| `next_action` landed | pass | line 185 of the plan reads `Codex acceptance: 2026-09-12.`, immediately after the Gate status line; `git status --porcelain` unchanged, index empty |

The launcher then stamped `successor.harness = "codex"`. Total: four shell
commands, none of them an unbounded read — the bounded-read constraint carried
across harnesses without a hook enforcing it (Codex hooks are deny-only and
none was installed).

Worth recording: **the ack cost one command, not five.** Claude-run finding 3
was that a successor cannot cheaply learn its own session id. On Codex the
launcher knows the thread id before the first turn exists, so `codex_prompt`
appends it verbatim to the rendered prompt. That is a harness advantage, not a
design fix — the Claude path still needs `ack --session-id auto` or a launch
that passes the uuid into the prompt.

### 2026-09-12 — Run D (stale diff refusal, Codex) — **PASS**

Handoff: `docs/dispatch/handoffs/2026-09-12-codex-acceptance-stale.v1.json`
Successor thread: `01a09578-1fb9-71d1-bbbf-6408a160b748`
Drift introduced: `touch /projects/dev/outctl/CODEX-DRIFT-PROBE.txt` — an
**untracked** file, so the drift is invisible to `git diff HEAD` and is caught
only by the `git status --porcelain` half of the digest. This is the repetition
Run B left outstanding. Removed after the run; `validate` passes again.

Launched with `--no-verify` on purpose: the launcher refuses a stale handoff
before it spends a thread, so proving the *successor* refuses requires letting
it meet the stale handoff itself.

| Check | Verdict | Evidence |
|---|---|---|
| `validate` exits nonzero, naming the repo | pass | exit 1, `/projects/dev/outctl: stale diff_sha256 — recorded 42ab277d03b0b6c7, working tree is now eb00822c6fcab905. The tree is not the one the predecessor left; refusing.` |
| Successor stops and reports | pass | "Repository validation **refused** because `diff_sha256` differs … Stopped as instructed." Three commands total: ack, read the handoff, validate. No fourth |
| It did not adapt to the drift | pass | no re-derivation, no edit to the handoff's digest, no attempt at `next_action`; it explicitly noted the handoff was changed only by the required ack |
| Plan file unchanged | pass | md5 `253b7d83bf3cb85cc8b55c6ba2697dec` before and after |

The digest's `git status --porcelain` half is therefore load-bearing and proven.

**Finding from Run D, not a pass criterion.** The recorded digest for the Run D
handoff was byte-identical to Run A's (`42ab277d03b0b6c7`) *even though Run C
had just edited the plan file in between*. The plan file is untracked, so
`git diff HEAD` never sees it and `git status --porcelain` reports only the
unchanging line `?? docs/CONTEXT_ECONOMY_PLAN_2026-09-12.md`. **`diff_sha256`
detects the appearance and disappearance of untracked files, not changes to
their contents.** For a repo whose work in progress is untracked — which
`/projects/dev/outctl` is right now — the digest is much weaker than it looks.
Hashing the contents of untracked non-ignored files, or at least recording
their sizes and mtimes, would close it.

**Fixed, 2026-09-12** — `state.digest_version`. The objection above ("it
invalidates every handoff already written") was the reason to leave it; a
version field removes it. Absent or `1` means the old definition; `2`, what
`create` now writes, appends one `NUL <path> NUL <sha256 of contents>` record
per untracked non-ignored file (`git ls-files --others --exclude-standard`,
sorted by raw path bytes, contents hashed as bytes so binaries are covered).
`validate` computes **the definition the file declares**, so the four handoffs
already in `docs/dispatch/handoffs/` keep validating unchanged. Pinned by
`TestDigestDefinition` (both definitions, an untracked content change seen by
v2 and provably missed by v1, a binary file, gitignored files) and
`TestDigestVersionCompatibility` (create writes 2; a v1 handoff still
validates; the committed evidence handoffs declare no version).

### `read` and `consult`, exercised

`read 01a09578-1fb9-71d1-bbbf-6408a160b748 --limit 3` printed the thread
metadata and the last three rollout records (the launch prompt, the ack, the
refusal) and left `status: notLoaded` — the thread was not woken.

`consult 01a09576-febc-7e82-9997-3b14132b342d "…what exactly did you insert
…and did you commit?"` resumed the Run C thread and answered correctly from its
own memory. It prints the cost warning to stderr first: the answer is produced
against the parked session's full context and billed against it. That is the
intended cost shape, and it is why `read` exists.

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
devbox `agent` identity).

**Runs C and D are simulated in exactly the same way, and the Codex harness
does not change that.** The Codex successor ran as `bayleaf` on the
workstation, with the same read rights over `~/.claude/projects/` and
`~/.codex/sessions/` as the predecessor. The only additional isolation Codex
supplies is negative: it has no `SendMessage`/`ListAgents`, so the "predecessor
is unreachable" half is structural there rather than a matter of an omitted
tool allowlist. The transcript half is not enforced: a Codex thread launched
with `sandbox: workspace-write` still has **full read access to the whole
filesystem** — `writableRoots` bounds writes, not reads. `sandbox: read-only`
would not help either; it is reads that need bounding. Nothing short of a
second uid closes it.

### Enforced isolation (pending devbox rollout)

The procedure below has **not been run**. It is written now so the phase-4
record says what "enforced" would mean rather than leaving it as an intention.

Shape: the predecessor stays where the work happened — `bayleaf` on the
workstation. The successor runs as `agent` on devbox-vm
(`ssh devbox-agent`, 192.168.20.108), a different uid on a different host, with
no route to the workstation's `~/.claude/projects/` or `~/.codex/sessions/` and
no mount of the workstation's `/projects`. The one thing that crosses is the
handoff file.

**Why devbox-vm and not a second local uid.** A second uid on the workstation
would enforce the transcript half (mode `0700` on `~/.claude`) but leaves the
successor sharing a filesystem, a process table and a `SendMessage` bus with
the predecessor. devbox-vm has none of those, and it is the identity phase 4
was going to have to reach anyway for the snip half. The cost is that
devbox-vm's `/projects/dev` is an **independent zvol clone**, not the
workstation's Btrfs tree (see `AGENTS.md`, "Shared workspace"): nothing
propagates without a deliberate git operation, which is precisely what makes
the isolation real and precisely what makes the setup below necessary.

**What must be pushed from the workstation first**

| Thing | State today | Needed because |
|---|---|---|
| `gitops-nixos` `03b2363` (snip from nixpkgs, filters under `modules/system/snip/filters/`) | **already on `origin/main`** — no push needed | devbox-vm's NixOS config must carry it before snip exists there. Note the module is workstation-identity-only today; extending it to the `agent` identity in `hosts/devbox/` is a separate commit that does not exist yet |
| `agentops` branch `handoff-v1` (this branch: schema, `handoff.py`, `handoff_codex.py`, `bin/agentops`, tests) | **not pushed** — the task that produced it forbids pushing | devbox-vm needs `agentops handoff ack`/`validate` locally; it cannot read the workstation's copy |
| the handoff `.json` itself | untracked, under `agentops/docs/dispatch/handoffs/` | it is the payload. It must **not** ride along in the branch — a handoff committed to a branch the successor clones is a handoff the successor could have read from git history instead of from the file, which muddies what is being tested |

**Setup on devbox-vm, once, as `agent`** (no sudo there; NixOS config changes
go through the infra path, not this procedure):

```bash
ssh devbox-agent
cd /projects/dev/agentops && git fetch origin && git checkout handoff-v1
mkdir -p ~/.local/bin && ln -sf /projects/dev/agentops/bin/agentops ~/.local/bin/agentops
cd /projects/dev/outctl && git fetch origin   # the repo under test, its own clone
```

The repo under test must be brought to the exact state the handoff records —
including its dirty tree, since `diff_sha256` covers `git diff HEAD`,
`git status --porcelain` and — under digest v2, which `create` now writes — the
*contents* of every untracked non-ignored file. That last part makes the
reproduction stricter than it was when this section was written: copying the
untracked files across is no longer optional bookkeeping, it is part of the
digest. Reproducing an uncommitted tree across hosts is the
hard part of this procedure, and it is where a first attempt will most likely
fail: a `git diff HEAD > patch` plus a copy of the untracked files, applied on
devbox before the handoff is created, is the workable route. Create the handoff
**on devbox against devbox's tree** and hand it back if reproducing the
workstation tree proves unreliable — the test is about successor isolation, not
about cross-host tree replication.

**Transfer** — one file, one direction, no shell back:

```bash
scp docs/dispatch/handoffs/<id>.json devbox-agent:/projects/dev/agentops/docs/dispatch/handoffs/
```

Nothing else is copied: not the `.md`, not the transcript, not the predecessor's
session id beyond the string already inside the JSON.

**Run**, from the workstation, non-interactively so the predecessor never has a
turn open:

```bash
ssh devbox-agent 'cd /projects/dev/outctl && \
  python3 /projects/dev/agentops/templates/dispatch/scripts/handoff_codex.py \
    launch /projects/dev/agentops/docs/dispatch/handoffs/<id>.json --timeout 600'
```

**What makes it enforced, and how each is checked**

| Property | Enforced by | Check |
|---|---|---|
| Cannot read the predecessor's transcript | different uid on a different host; the workstation's `~/.claude` is not exported and devbox-vm has no NFS mount of it | on devbox, `ls /home/bayleaf` fails; the handoff's `transcript_path` resolves to nothing |
| Cannot reach the predecessor | no `SendMessage` on Codex, and no agent bus between hosts | structural |
| Cannot reach back into the workstation tree | devbox-vm's `/projects/dev` is its own zvol clone | `git -C /projects/dev/outctl rev-parse HEAD` on devbox is answered from devbox's clone |
| Egress is not a hole | devbox-vm's egress is allowlisted at the host (nftables `agent-egress`) and at OPNsense; Codex launches with `networkAccess: false` in the sandbox policy on top | a denial during the run is policy, not an outage — record it, do not work around it |

**Ack write-back — settled, 2026-09-12.** The gap was real: the ack was written
to devbox's copy, the workstation's copy stayed `successor.session_id: null`,
and the guard is a file of which there were now two. Three options were on the
table:

| Option | Why not / why |
|---|---|
| (a) one file both hosts read — a shared mount | **impossible here.** The workstation and devbox-vm share no filesystem mount at all (`AGENTS.md`, "Shared workspace": devbox-vm's `/projects/dev` is an independent zvol clone). There is nothing to point both hosts at |
| (b) the origin keeps the authoritative copy; a remote ack goes through it | **chosen** |
| (c) the handoff lives on a git branch both hosts fetch | rejected: it makes the payload readable from git history, which muddies exactly what the isolation run tests (see the transfer table above), and a push/fetch race is a worse guard than an atomic file write |

**The decision (b).** `create` stamps `origin_host` and `origin_path` into the
handoff while the predecessor's host still is the origin. The file is then
transferred once, by `scp`, in one direction. `agentops handoff ack` on a host
that is not the origin does **not** claim locally: it runs the atomic ack on the
origin's copy first —

```
ssh <origin_host> agentops handoff ack <origin_path> --session-id <id>
```

falling back to `python3 …/templates/dispatch/scripts/handoff.py ack …` when the
`agentops` wrapper is not on the origin's non-interactive PATH (exit 127) — and
updates the local copy only once that returned zero. A remote refusal raises,
naming the origin, and leaves the local file byte-identical. So the authoritative
copy stays with the predecessor, and two successor hosts holding two scp'd copies
are still contending for one file on one machine: "exactly one successor may be
active" holds across hosts, not just within one.

The transport is injected (`handoff.ack(..., transport=...)`, default
`SSHTransport`), so the cross-host guard is pinned by `TestTwoHostAck` against a
mock rather than requiring a second machine in CI: remote refusal leaves the
local file untouched, remote acceptance updates both, the 127 fallback fires, and
a handoff with no `origin_host` (everything written before this) still acks
locally on any host.

**Assumption this run must satisfy.** `ssh` from the devbox agent back to the
workstation as `bayleaf` must exist and be non-interactive. What is configured
today, from `/home/bayleaf/.ssh/config`, is the *outbound* direction only:

| Host alias | Target | User |
|---|---|---|
| `devbox-vm` | 192.168.20.108 | `dev` |
| `devbox-agent` | 192.168.20.108 | `agent` |
| `devbox-deploy` | 192.168.20.108 | `dev` (`IdentitiesOnly yes`) |
| `cluster-devbox` | shell.apps.kotona.app | `dev` (the legacy pod) |

All four are workstation → devbox, all on `~/.ssh/id_ed25519_remote`. **There is
no reverse entry**: nothing on the workstation's side configures or evidences
`agent@devbox → bayleaf@workstation`, and devbox-vm's egress is allowlisted at
the host (nftables `agent-egress`) and at OPNsense, so the reverse hop is a
policy question as well as a key question. No keys were created for this — that
is a deliberate non-action, and it is the one prerequisite the enforced run must
land before it can exercise the cross-host ack. Until it does, the enforced run
can still be executed with the ack taken on the origin by hand; the guard is
then documented rather than demonstrated.

**Prerequisite not yet met**: `sudo nixos-rebuild switch` on the workstation for
the snip half of phase 4, and a `hosts/devbox/` change extending the snip module
to the `agent` identity. Neither is in scope for the branch that wrote this
section, and neither blocks the isolation run — snip and isolation are
independent halves of phase 4. The ack decision above adds a third: a
non-interactive `agent@devbox → bayleaf@workstation` ssh path, which blocks the
cross-host ack and nothing else in the run.

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
