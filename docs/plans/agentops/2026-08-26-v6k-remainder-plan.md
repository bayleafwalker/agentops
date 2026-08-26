# V6-K's remainder — the staging fix, the landing, and three carried debts

Prepared 2026-08-26. Written to the standard set by `2026-08-26-open-owner-decisions.md`: every
factual claim below was re-verified against the code, the sink or the hosts before being written.
**Four claims changed shape during checking and two reversed outright** — one of them is the claim
this document was commissioned to confirm.

Companion documents: `docs/dispatch/handover-2026-08-23-metanarrative-v5.md` §2/§5/§6/§7,
`docs/dispatch/workflow-topology.md`, `docs/plans/agentops/2026-08-26-measurement-instrument-findings.md`,
`docs/plans/agentops/2026-08-25-l6-d9-restate-pilot-design.md` §2b.

---

## 0. Classification, per the house format's three axes

| # | Item | Derivable? | Authorization needed? | New value choice? | Output |
|---|---|---|---|---|---|
| A | Packet staging in `hybrid_dispatch.py` | **Yes** — the seam is determined by three existing mechanisms | Rule 14 title only | No | Resolved action |
| A′ | *Is `readable_context_paths` reachable by a contained worker?* | **Yes, and it is answered: YES** | — | No | **Finding reversed — see §1.2** |
| B | How V6-K lands | **Yes** | No | No | Resolved action: re-dispatch |
| C | Finding B + §2b/D-9 restatement | **Yes** — arithmetic, once the window is pinned | No | No | Resolved action; **the recorded finding is itself wrong — see §3** |
| D | devbox containment weakness | Diagnosis derivable; **unverified this session** | **Yes** — a gitops-nixos change the owner deploys | No | Resolved action + one deploy to ratify |
| E | `AUDITCTL_ARTIFACTS_ROOT` in the hook oracles | **Yes** | No | No | Resolved action; **the recorded debt names the wrong file and understates by 40× — see §5** |
| F | 424 fixture events in the live agentops audit ledger | Diagnosis derivable; the disposal is not | **Yes** | **Yes** | **The one policy question — §6** |
| — | Finding E (subagent spend) | — | — | — | **Already a live owner decision. Not re-opened, not re-argued. Pending.** |

Six items. Five resolve to actions. One narrowly framed policy question. That is the shape
`2026-08-26-open-owner-decisions.md` says this document should have.

---

## 1. (a) The packet-staging fix

### 1.1 What actually broke

`worker_argv` passes `--file <packet_path>` (`hybrid_dispatch.py:705`, `:726`), and `packet_path`
is `args.packet.resolve()` — the path in the **coordinator's checkout** (`:2350`). A contained
worker cannot read that tree; that is the identity's entire purpose. The receipt records the
consequence exactly:

```
Error: File not found: /projects/dev/agentops/docs/evidence/packets/V6-K-human-turns.json
```

Three separately-verified facts pin why this is structural, not incidental:

1. **The workspace is a clone at `starting_commit`** (`prepare_workspace`, `:1090`), and the
   packet is **commit 2** of the freeze. Verified: `docs/evidence/packets/V6-K-human-turns.json`
   is absent at `f40d2ca` and present at `7f428a6`. So the packet is *never* inside the workspace
   by construction — the two-commit freeze shape guarantees it. Widening paths cannot fix this
   and neither can any packet's own declarations.
2. **The workstation's containment is real and the devbox's is not.** Measured today:
   `/projects/dev` is `drwxrws--- bayleaf developers`; `agentworker` is `uid=1101(agentworker),
   groups=1101(agentworker),933(agentdispatch)` — not in `developers`. It cannot traverse. The
   shared group is `agentdispatch`, and the prepared workspace is `drwxrwxr-x bayleaf
   agentdispatch`, as is its `.git`.
3. **`external_directory: deny` is not a boundary.** `coordinator_tree_state`'s own docstring
   (`:1806`) records that it "did not stop a worker from writing an absolute path into the
   coordinator's tree." Any staging design that leans on it is leaning on a rule the code says
   does not hold.

### 1.2 `readable_context_paths` — the hypothesis is falsified, and it is not close

The brief asked whether `readable_context_paths` is reachable by a contained worker, on the theory
that if it is not, **every** packet declaring readable context has been silently degraded.

**It is reachable, and no packet has been degraded.** Two independent checks:

- **Mechanically:** `readable_context_paths` is never handed to the worker at all. It is used in
  exactly two places — an escape check in `validate_packet` (`:316`) and the declared-set half of
  the L-2b read-trace (`:1397`). It grants nothing. The worker's read grant is blanket
  `read/glob/grep/list: allow` (`build_overlay`, `:612-615`) scoped by `cwd=worktree` and the uid.
  Every repo-relative path present at `starting_commit` is therefore readable, because it is *in
  the clone*.
- **Empirically:** all 40 packets in `docs/evidence/packets/` carrying a `starting_commit` were
  checked, resolving every declared readable path against that commit's tree.
  **40 packets checked, 0 with an unreachable declared readable path.** V6-K's own four are all
  present at `f40d2ca`.

So the real finding is narrower and sharper than the hypothesis: **exactly one artifact the worker
is given cannot be read, and it is the packet — the only one that is deliberately not in the
tree.** The failure mode is not "read paths are degraded"; it is "the one file whose whole design
is to live outside the starting commit is passed by a path only the coordinator can resolve." Note
the second-order effect: with `--file` broken, the worker also never learned what its readable
context *was*, because that list only reaches it inside the packet JSON.

One honest caveat, recorded rather than buried: a packet could declare a readable path that exists
on the coordinator's disk but not at `starting_commit`, and nothing checks that today.
`check_oracle_reference` has a message about a path that does "not exist in the workspace the
worker will be given" (`:1266`), but it fires on the reference patch, not on
`readable_context_paths`. Zero packets have tripped it. **Do not build a gate for a defect with a
zero-instance history** — record it as a debt line and move on.

### 1.3 Where to stage — and why not the two obvious places

| Seam | Verdict |
|---|---|
| **Into the worktree's working tree** (e.g. `<worktree>/.agentops-packet.json`) | **Rejected, and this is the decisive check.** `post_gates` computes `touched` as `git diff --name-only <starting_commit>` **∪ `git ls-files --others --exclude-standard`** (`:2136-2143`). An untracked staged packet is a touched path, so it fails `diff-scope-respected` on every packet and makes `diff-nonempty` true even when the worker wrote nothing. Worse, `dispatch_release.py:623` runs `git add -A`, so it would land in the commit and the PR. `reroot_agent_context`/`restore_agent_context` (`:818`, `:847`) exist solely to un-do a *smaller* version of this problem; do not create a second one. |
| **A sibling directory outside the worktree** (e.g. `/tmp/agentops-hybrid/packets/<repo>/<task>/`) | Workable but strictly worse: it needs its own `chown`/`chmod` to `agentdispatch`, it has its own lifecycle to clean up, and its readability by the worker depends on `external_directory: deny` not applying to `--file` — a rule `:1806` says is not reliable. |
| **Inline the packet JSON into the worker message** | Rejected. It removes the read path entirely, but it materially changes what the model sees on every dispatch, which de-comparabilises the whole `mechanical_bulk` qualification corpus for a containment bug. Wrong trade. |
| **`<worktree>/.git/agentops/packet.json`** | **Recommended.** Inside the workspace, so no `external_directory` question. Invisible to `git diff`, to `git ls-files --others`, and to `git add -A` — git never enumerates its own directory, so no gate, no commit and no PR can pick it up. Already correctly moded: `.git` is `drwxrwxr-x bayleaf agentdispatch`, and `share_workspace_with_group` walks `[workspace, *workspace.rglob("*")]` (`:942`), which **does** include dotfiles (verified: `pathlib.rglob` does not skip them, unlike `glob.glob`). Disposed with the workspace. |

### 1.4 Stage in `run`, not in `prepare`

`_receipt` hashes the packet **as loaded at the moment of the stage that emits it** (`:2234`,
`sort_keys=True, separators=(",",":")`), and `prepare` and `run` are separate process invocations
with a human gap between them. That gap is exactly where `claim_id` is filled in today (§9.1). If
`prepare` stages a copy and `run` hashes `args.packet`, the two can differ and nothing would
notice — the worker would implement one packet while the receipt attested to another. Staging in
`run`, from the same in-memory `packet` object that is about to be hashed, makes divergence
unrepresentable.

### 1.5 The resolved action

**One hand-pass PR, title beginning `hand-pass:`** (Rule 14; `hybrid_dispatch.py` is in
`agentops.dispatch.json`'s `hybrid.protected_paths`, and `check_protected_paths.py` will fire).

1. Add `staged_packet_path(worktree) -> Path` returning `worktree / ".git" / "agentops" / "packet.json"`.
2. Add `stage_packet(worktree, packet, worker_user) -> Path`: `mkdir(parents=True, exist_ok=True)`,
   write the packet with the **same canonicalisation `_receipt` uses** (`sort_keys=True`,
   `separators=(",",":")`), then apply the same `chown(-1, worker_shared_gid)` + `S_IWGRP|S_IRGRP`
   treatment `share_workspace_with_group` applies, on the file and both new directories.
3. In `cmd == "run"`, call `stage_packet` immediately before `dispatch_worker` and pass the staged
   path where `packet_path` goes today. `dispatch_worker`'s signature is unchanged; `worker_argv`
   is unchanged. **Do not** change `worker_argv` — its argv shape is asserted by tests and shared
   with the qualification probe.
4. Assert in the receipt: add `inputs.staged_packet_sha256` and assert it equals the existing
   `inputs.packet_hash` payload. That makes "the worker read the packet the receipt attests to" an
   observed fact rather than an inference — the exact discipline `assess_worker_workspace_write`
   applies to writability.
5. **Probe once before trusting it**, per §3h's "re-running beats reasoning": on the workstation,
   `sudo -u agentworker cat <staged path>` must succeed and `sudo -u agentworker cat
   /projects/dev/agentops/docs/evidence/packets/V6-K-human-turns.json` must still fail. A staging
   fix that also opened a read path into the coordinator tree would be a regression wearing a
   green gate.
6. Tests: one asserting the staged path is not in `post_gates()["touched_paths"]` after staging
   into a real prepared workspace, and one asserting the staged bytes hash to `inputs.packet_hash`.
   The first is the one that matters — it is the gate that would have caught the working-tree
   design.

**Classification: derivable.** Nothing here is a value choice; the seam is determined by
`post_gates`'s untracked-file rule, `dispatch_release.py`'s `git add -A`, and the receipt's hash
timing. No owner touchpoint under Rule 4.

---

## 2. (b) How V6-K should land: **re-dispatch, at attempt 1**

### The facts that decide it

- **Reservation #33 is still active.** So the packet needs **no edit**, `packet_hash` stays
  `sha256:5734588600fe7388…`, and attempt 2's receipt will carry the *same* `packet_hash` as the
  void attempt 1. That is a genuinely valuable corpus row: one packet identity, one harness-void
  run, one real run — which is precisely the "harness escalations do not spend D-8's budget"
  distinction (Amendment 2) made visible in data instead of in prose.
- **Attempt 1 produced no evidence about the route or the model** — 093dc77 already rules this,
  correctly. `$0`, 0 tokens, the model never ran.
- **The direct arm produces nothing usable here.** `v5-p1-two-way.json`'s direct run is annotated
  *"NOT packet-isolated… A per-packet direct cost cannot be extracted from it."* Landing V6-K
  direct would add a **second** non-isolable direct row — it would not create the `#2017` control
  arm, because a control arm needs a deliberately isolated, scoped, timed direct run, which is a
  separate design. Do not let "we need a control arm" launder an unisolable measurement into one;
  that is the T-9 error (§3h, "the sink is global") in a new costume.
- **The packet is the shape that goes green.** One additive field, one writable file, an
  independently-authored oracle proven red at `starting_commit` and green under a reference patch
  that also reproduced the real-transcript figures (31/15 and 16/5). Rule 9's additive test is
  satisfied. Eleven packets of this shape have gone green first attempt.
- Expected cost, from the T-series band: **$0.008–$0.022** and 60–350k tokens.

### One harness obstruction to clear first

`prepare_workspace` refuses when the target exists unless `workspace_is_retry_reuse` is true, which
requires `attempt > 1` (`:1069-1086`). The workspace at
`/tmp/agentops-hybrid/worktrees/agentops/V6-K-human-turns` is still standing (`cleanup:
retain-for-review`). **Delete it and keep `attempt: 1`.** Bumping `attempt` to 2 would be a lie in
the record — it would read as "retry after a red gate," which is what the L-4 machinery means —
and it would move `packet_hash`, breaking the one thing that makes the re-dispatch valuable. See
§9.2: the harness cannot currently express "attempt 1 again; the first one never happened," and
that is a real friction cost, not a workaround.

### The resolved sequence

1. Land the §1 hand-pass; merge it; confirm merge-preview green (§4.6 has outperformed the gates
   four to nothing — do not skip it).
2. `rm -rf /tmp/agentops-hybrid/worktrees/agentops/V6-K-human-turns`.
3. `validate` (on devbox, or `--allow-untraced-oracle` with `skipped:untraced` recorded).
4. `prepare` → `run` → `gate` → `receipt` → PR, unchanged, attempt 1, claim 33.
5. Record **both** receipts under `docs/evidence/receipts/V6-K-human-turns/` — attempt 1 keeps its
   void receipt, explicitly marked as harness evidence and excluded from qualification.

**Classification: derivable.** No owner touchpoint. The PR merge is the release-boundary
touchpoint that already exists under Rule 4 and Rule 8.

---

## 3. (c) Finding B, and the §2b/D-9 restatement — **the recorded finding is wrong**

### 3.1 What Finding B says, and what is actually true

Finding B states: *"The numerator (16 turns) ends at 2026-08-24T20:02:32Z. The denominator (11
packets) includes T-11, which landed on 2026-08-25… Either the numerator should extend to cover
T-11's turns, or the denominator is 10."*

The direction is right. The mechanism is not, and it matters. Measured against
`docs/evidence/scorecards/v5-t-series.generated.json`:

```
scope: {"project": "agentops", "since": "2026-08-24T18:00:00Z", "until": null}
frontier: {"sessions": 1, "turns": 16, ...}
worker: {"tasks": 11, "attempts": 11}
```

**`until` is `null` — the window is unbounded.** The numerator is not "scoped to 20:02:32Z"; it is
scoped to *whenever the sink last happened to be written before the generator ran*. The scorecard
is therefore **not reproducible from its own scope block**, and it drifts every day. Re-reducing
`/projects/dev/.claude/session-costs.jsonl` today over `project=agentops, since=2026-08-24T18:00Z,
until=unbounded` gives:

| | as committed | as the scope block would produce today |
|---|---|---|
| sessions | 1 | **5** |
| turns | 16 | **56** |

That is the **fifth** instance of the §3h pattern — a number that is arithmetically correct and
says the wrong thing — and it is on the scorecard produced by the tool that T-9 built specifically
so *"a reader never has to tell 'absent' from 'unbounded'."* T-9 made all three scope keys always
present. It did not make anyone fill the third one in. **A field that is always present and always
`null` is the same defect as a `format: "uuid"` that never bites**: a claim the repository makes
and does not keep.

### 3.2 And Finding A commits Finding B's error inside its own fix

Finding A's recommendation table read:

| | turns | / 11 packets |
|---|---|---|
| As recorded | 16 | 1.45 |
| Human prompts only | **5** | **0.45** |

The `5` is the **T-series-window** count. The `11` includes T-11, which is outside it. **0.45
divides a window-scoped numerator by an unscoped denominator — Finding B's exact error,
uncorrected, inside Finding A's headline number.** Finding A's own full-session figure is in the
same section: *"Across the full session: 31 hook-turns, **15** human."*

Restated consistently, the two coherent readings are:

| Window | turns | human | packets | human/packet | 5× falsifier target |
|---|---|---|---|---|---|
| Truncated at 2026-08-24T20:02:32Z | 16 | 5 | **10** | 0.50 | ≤ 0.10 |
| Whole release, to T-11's close | **31** | **15** | 11 | **1.36** | **≤ 0.27** |

**They differ by 2.7×, and the published 0.45 is neither.** A v7 challenger graded against 0.45
would be held to ≤0.09 prompts per packet — roughly "one human prompt per eleven packets" — which
no plausible topology achieves, so the falsifier would be unfalsifiable in the wrong direction.
Finding A's headline ("a challenger that cut supervision not at all would still clear the target")
is directionally right about the *old* metric and lands on a *new* number that is wrong the other
way.

### 3.3 The resolved action

Pin the window; do not shrink the denominator.

1. Re-generate `v5-t-series.generated.json` with an explicit `--until` at T-11's close
   (`2026-08-25T18:00:00Z` covers `3ebf37bd`'s final snapshot at 17:47:06Z), keeping
   `--project agentops --since 2026-08-24T18:00:00Z`. Denominator stays **11**, which is honest:
   T-11 is part of the T-series by the handover's own §3i.
2. **Restate §2b against `human_turns`, using 31 / 15 / 11 → 1.36 human prompts per packet**, and
   restate D-9's 5× target as **≤ 0.27**. Mark the 16/1.45 baseline *superseded, not wrong* — it
   measured something real under a wrong label — exactly as Finding A prescribes.
3. Correct Finding A's own table in place (0.45 → 1.36, with a one-line note saying why), in the
   same spirit the open-decisions document corrects itself in place. A findings document that
   commits the defect its neighbouring finding names is worse than one that never noticed.
4. **Add a `--until` requirement, not a `--until` flag.** `release_scorecard.py` already has the
   flag. Make a scorecard whose `scope.until` is `null` fail to generate, or carry an explicit
   `"until": "unbounded (deliberate)"` sentinel. A release scorecard describes a closed release;
   an open right edge is never what was meant. This is a one-file, one-outcome, additive change
   with an attainable red oracle — **it is a `mechanical_bulk` packet**, not coordinator work.
5. Blocked on V6-K landing for the `human_turns` half only; steps 1, 3 and 4 can proceed now.

**Classification: derivable, arithmetic.** Pinning the window to the release's actual span is
enforcing T-9's existing scope doctrine, not writing new policy — the same "policy application,
not policy making" distinction the open-decisions document names for `#2100`. No owner touchpoint.

---

## 4. (d) The devbox containment weakness

### What is recorded, and what could and could not be verified

093dc77 records: devbox's `/projects/dev` chain is `drwxr-xr-x agent agent` all the way down, so
`agentworker` can read the coordinator's whole checkout there; the workstation's is
`drwxrwx--- bayleaf developers` with `agentworker` deliberately outside `developers`; therefore
"devbox works by accident."

**Verified on the workstation** (`ls -ld`, `id agentworker`): `/projects/dev` is
`drwxrws--- bayleaf developers`, `/projects/dev/agentops` is `drwxrwx--- bayleaf developers`, and
`agentworker` is in `agentworker` and `agentdispatch` only. The workstation half is exactly as
recorded.

**Not verified on devbox during the planning pass** — `ssh devbox` failed on host-key verification.
The devbox half rests on 093dc77's measurement alone. **Say so rather than inherit it**: the
open-decisions document's decision 3 is the standing precedent for what happens when a recorded
measurement of devbox is trusted instead of re-taken (179 commits behind → actually 29; 23 dirty
files → actually 0).

### One correction to the record

093dc77 says this is *"weaker containment than `modules/users/agentworker.nix` describes."*
Read literally, the `.nix` file describes a **write** ban, not a read ban
(*"This user must therefore never gain: … **write access** to anything under /projects"*).
World-readable `/projects/dev` does not violate that sentence.

What it *does* violate is `hybrid_dispatch.py`'s module docstring — the worker "only ever sees the
frozen packet, a disposable worktree, and a session permission overlay" (`:6`) — and the worker's
declared contract, *"no authority, credentials, network, or oracle ownership."* A worker that can
read the coordinator's tree can read every other packet's oracle, every reference patch on disk,
every plan document, and `.envrc`. **Cite the docstring, not the nix comment.** Getting this right
matters because the nix comment is the thing that would be edited, and editing it to ban reads is
a real change with a real justification — not a restatement of something it already said.

### The resolved action

1. **Re-measure devbox first** (`namei -l /projects/dev/agentops`, `id agentworker`,
   `sudo -u agentworker test -r /projects/dev/agentops/agentops.dispatch.json`). One command.
   Do not act on 093dc77's numbers; act on today's.
2. **The §1 staging fix removes the dependency either way.** After it lands, no host needs a read
   path from the worker into the coordinator tree, so devbox's permissions stop being load-bearing
   for dispatch. **Land §1 before touching devbox's modes** — tightening them first would break
   dispatch on devbox for exactly as long as it takes to land §1.
3. Then tighten: a gitops-nixos change putting `/projects/dev` on devbox behind a group
   `agentworker` is not in, plus one sentence in `modules/users/agentworker.nix` extending the ban
   from write to **read**, with the reason (the docstring's "only ever sees" claim).
4. **Verify by reading the host, not the nix file** — the precedent set for gitops-nixos #17/#18
   in §3g.

**Classification: diagnosis derivable; the deploy is ratification.** Bring the PR, not the
question. This is *not* a new value choice: the value ("the worker sees the packet, a worktree and
an overlay") is already written down in two places.

---

## 5. (e) The `AUDITCTL_ARTIFACTS_ROOT` debt — right in kind, wrong in file, understated 40×

The V6-K packet's `debt:` line says: *"`test-cost-hook-fields.sh` does not pin
`AUDITCTL_ARTIFACTS_ROOT`; auditctl is installed on this host, so every run of that oracle writes
real `workflow.session` events into the live audit store."*

Verified, and then measured. `/projects/dev/agentops/.auditctl/auditctl.db`:

```
workflow.session total 450   |   non-uuid (fixture-shaped) session ids: 424   |   94.2%
sess-b 152 · sess-a 81 · sess-poison 81 · no-transcript 81 · sess-t1 10
sess-mixed 4 · sess-all-human 4 · sess-all-noise 4 · sess-no-transcript 4 · smoke3/x/y 1 each
earliest fixture row: 2026-08-23T07:46:20Z
```

**The live agentops audit ledger is 94% test fixtures.** Three corrections to the recorded debt:

1. **The named file is not the main offender.** `test-cost-hook-fields.sh` (session id `sess-t1`)
   accounts for **10** of the 424. The dominant polluter is **`test-session-telemetry.sh`**, at
   **395** rows — and it is *not mentioned in the debt line at all*. It stubs `auditctl` only for
   REQ-003 (`:142-147`) and REQ-005 (`:200-206`); its other three Stop-hook invocations run under
   the ambient `PATH` with the root unpinned (`:41`, `:80`, `:86`). That is the file to fix first.
   It is also `agentops.hooks.tests` — the command carried as a non-`starts_red` guard on V6-K,
   so it runs on every dispatch of this packet.
2. **The debt line's remedy is wrong.** It says *"Fixing it is a protected-path hand-pass under
   `templates/dispatch/hooks/tests/**`."* It is not. `templates/dispatch/hooks/tests/**` is in
   **V6-K's own packet-level `protected_paths`**, not in `agentops.dispatch.json`'s
   `hybrid.protected_paths` — which is exactly `templates/dispatch/hybrid/**`,
   `model-routing.json`, `manifest.schema.json`, `hybrid_dispatch.py`, `agentops.dispatch.json`,
   `.claude/**`. Per-packet protection binds one worker; it is not repo policy. CI
   (`check_protected_paths.py`) reads the manifest list, so a PR touching the hook tests needs no
   `hand-pass:` title. Ordinary work. (The handover has the same conflation for
   `templates/dispatch/tests/**` at Rule 13 — worth one corrective sentence there too.)
3. **The new oracle is clean; the freeze process is not.** `test-human-turns.sh` does it right:
   a stub `auditctl` shadowing the real one on `PATH` and `AUDITCTL_ARTIFACTS_ROOT` pinned into
   the temp dir (`:53-62`, `:80-84`). Yet 16 rows carrying *its* fixture ids
   (`sess-mixed`/`sess-all-human`/`sess-all-noise`/`sess-no-transcript`, 4 each) are in the live
   store, in four clean bursts at **18:06:17, 18:06:48, 18:07:05, 18:07:11 on 2026-08-26** —
   the freeze-verification window ("red at starting_commit / green under reference / t1 green /
   red again after revert" is four runs). They cannot have come through `run_stop`. The most
   likely explanation is by-hand runs of the reference implementation over the oracle's fixtures
   **outside** the oracle's harness. **Flagged as hypothesis, not fact — it needs one repro.**
   If it holds, the point is sharp: the hygiene lives inside the oracle, and the reference-patch
   proof Rule 10/Rule 12 *mandate* runs without it.

### The resolved action

One PR, ordinary title, three parts:

1. `test-session-telemetry.sh`: hoist the stub-`auditctl`-on-`PATH` + pinned-root pattern out of
   REQ-003 and apply it to **every** Stop-hook invocation in the file. `test-human-turns.sh:53-84`
   is the reference implementation of the pattern; copy it.
2. `test-cost-hook-fields.sh`: same treatment (10 rows, but it is the file the debt named and it is
   a two-line change).
3. **Add the invariant, not just the fix:** a check that fails if any hook test invokes
   `log-session-cost.sh` without both `AUDITCTL_ARTIFACTS_ROOT` pinned under `$tmp` and a stub on
   `PATH`. Asserted by a syntactic rule over the test sources, in the spirit of
   `test_release_scorecard_naming.py` — so a *future* hook test is caught with nobody maintaining
   a list. Without this, the next test written repeats it, which is what happened between
   `test-session-telemetry.sh` and `test-cost-hook-fields.sh`.
4. Record the by-hand-verification hole (item 3 above) as a debt line and, if the repro confirms it,
   a `direnv`-independent wrapper for reference-patch verification that pins the root.

**Classification: derivable.** No owner touchpoint. It is not a hand-pass.

---

## 6. The one policy question

> **The live agentops audit ledger is 94% test fixtures (424 of 450 `workflow.session` events,
> from 2026-08-23 onward). §5 stops the bleeding. It does not decide what happens to the 424
> already in it. Which?**
>
> **A. Leave them; filter at read time.** Free, and never lies about the past. Cost: every consumer
> of `workflow.session` must know to exclude non-UUID session ids, forever. That is a maintained
> list in a reader's head — the failure mode T-10 named.
>
> **B. Delete the 424.** The ledger then means what it says. Cost: a delete against an
> append-only audit store. `auditctl` has no "this row was a test" concept, and if it did, the
> deletion would be un-attested.
>
> **C. Retire the store and start a clean one, keeping the old file as an archive.** Preserves the
> old bytes, gives the new store an honest start date, and is the one option that is neither a
> lie nor a deletion. Cost: `#2017`'s frontier baseline loses the 26 real rows in the old store
> unless they are re-derived from the sink — which is possible, because Finding C's backfill
> reduced 179 transcripts newest-per-session.

**Why this one is genuinely the owner's, when the other five are not:** every other item here is
enforcing a rule the repository has already written down. This one asks what an audit ledger *is* —
whether "append-only" is a property of the store or a property of the record, and whether a
mechanically-generated fixture event was ever a record at all. Nothing in the manifest, the
handover or the topology document settles it, and `auditctl` is a shared dependency across
repositories, so the answer sets a precedent beyond agentops.

**Planner's reading: C.** B destroys evidence to fix a labelling problem; A leaves a number that
does not say what it stands for, which is precisely the defect class §3h, T-8, T-9, T-10 and §3.1
above all belong to. C is the only option that keeps both the bytes and the meaning. But it is a
recommendation, not a ruling.

**One narrowly framed question. That is the whole owner surface of this document.**

---

## 7. Pending, not re-opened

**Finding E — subagent spend is uncounted, while Rule 5 makes every packet's oracle a subagent —
is already a live owner decision.** It is not re-argued, re-scoped or re-recommended here. Its
options (A fold / B sibling `subagent_totals` / C caveat) and the recommendation (B) stand as
written in `2026-08-26-measurement-instrument-findings.md`. It blocks nothing in this document:
§3's restatement is about `turns`, not tokens, and lands independently.

The one thing worth noting for whoever rules on it: Finding A's *"the metric counts a subagent
finishing as a human prompt while counting none of that subagent's tokens as spend"* survives §3's
correction intact. The corrected figures (31 turns, 15 human, 16 task-notification-and-plumbing)
make the two-directional error slightly *larger*, not smaller.

---

## 8. Execution order

| # | Action | Blocks | Class |
|---|---|---|---|
| 1 | §1 staging hand-pass on `hybrid_dispatch.py` (`hand-pass:` title) | 2, 4 | derivable |
| 2 | Delete the standing V6-K workspace; re-dispatch at attempt 1, claim 33 | 3 (partly) | derivable |
| 3 | §3 steps 1, 3, 4 (window pin, Finding A correction, `until` invariant packet) — **can start now** | — | derivable |
| 4 | Re-measure devbox; then the gitops-nixos read-ban PR | owner deploy | ratification |
| 5 | §5 hook-test hygiene PR + the syntactic invariant | — | derivable |
| 6 | §3 step 2 (§2b/D-9 restated against `human_turns`) | 2 | derivable |
| — | §6 audit-ledger disposal | — | **owner** |
| — | Finding E | — | **owner, already open** |

---

## 9. Dogfooding: where using agentops to build agentops cost time today

Blunt, verified, and including the candidates that turned out to be fine.

### 9.1 `claim_id` makes "frozen" false in a field that is inside the identity hash — **real, and it is the worst of these**

`validate_packet:297-299` requires `sprint_item.claim_id` to be a positive integer. §6 of the
handover requires a *fresh* reservation per packet. So commit 2 of every freeze commits a packet
that **cannot validate** (V6-K was frozen with `claim_id: null`, and 7f428a6's message says so
plainly), and the packet must then be edited at dispatch time.

`_receipt` hashes the canonicalised **whole packet** (`:2234-2243`), so that edit moves the
identity. Measured on V6-K:

```
sha256 at freeze (7f428a6, claim_id null)  6df25a66a09a7ed14717a8c65a689d0488185d1eeeb41a56c795ccbbd95b50cf
sha256 as dispatched (receipt)             5734588600fe73881ee3c5b2d4a465141cc776dfcda46a1416433224019a1d8b
```

`attempt` is in the same hash, and the retry machinery mandates changing it. So **two of the fields
the process requires mutating are inputs to the hash that is supposed to prove the packet did not
change.** The open-decisions document rejected option B for `#2100` precisely because *"editing
`route` in a frozen packet moves `packet_hash`, so every receipt's `execution_id` de-links"* —
and the same de-linking is happening routinely, by design, on two other fields.

**Resolved, not escalated** — by direct analogy to `#2100`'s option C: add an **additive** receipt
field `frozen_packet_hash`, over the packet with `sprint_item.claim_id` and `attempt` elided.
Nothing historical moves; `packet_hash` keeps its meaning and c191cb2's re-link proof stays valid;
`frozen_packet_hash` becomes the thing that is actually stable across a freeze. One hand-pass;
fold it into §1's PR.

### 9.2 The harness cannot say "attempt 1 again" — **real**

`prepare_workspace:1113-1122` refuses an existing workspace unless `workspace_is_retry_reuse`, which
requires `attempt > 1`. A run that failed *before the worker started* leaves a workspace behind
(`cleanup: retain-for-review`) and no legitimate way to re-run without either `rm -rf` by hand or
bumping `attempt` — which would falsely record a retry-after-red and move `packet_hash` (§9.1).
This is V5-M2's "the packet that could not unblock its own retry" (§3a), one layer down. The
handover records that L-4 fixed it; L-4 fixed the *red-gate* case, not the *harness-void* case.
Cheap fix: let `workspace_is_retry_reuse` also admit a workspace whose branch matches and whose
`git diff <starting_commit>` is empty — that is provably a workspace no worker ever wrote to.

### 9.3 The two-commit freeze dance — **real, and it is the direct cause of the V6-K failure**

Oracle at commit 1, packet at commit 2. That is a good rule (Rule 10; M-1's first run was void
because the reference patch was committed at `starting_commit`), and §3h shows it earning its keep
— V5-T9's `starts_red` defect was caught at `prepare` with `starting_commit` never moving. But its
unavoidable consequence is that **the packet is never in the workspace**, which is the whole of §1.
Cost today: one failed dispatch, one evidence commit, this plan's §1. The rule is right; the
harness just never noticed what it implied about how the packet reaches the worker.

Related, and separately expensive: the freeze-branch trap (debt #8) already **lost three packets**
outright — `V5-M13`, `V6-B`, `V6-C` had receipts with no packet, recovered from a stale remote and
from unreferenced objects (c191cb2). The cherry-pick-commit-2 workaround "cost one extra PR per
row (#116, #119, #122, #128, #135 for five rows) and only narrowed the loss window." Five extra PRs
is a measured, real cost of this shape. It is now settled (merge the freeze branch), so it should
not recur.

### 9.4 Protected paths forcing hand-passes for command registration — **NOT a problem; already fixed**

`check_protected_paths.py` carries the `#83` exemption: `agentops.dispatch.json` only, purely
additive keys under `hybrid.commands` only, under a title beginning `[hybrid]` (`:42-51`, `:76-98`).
Commit 1 of the V6-K freeze registered `agentops.hooks.tests.human-turns` and did not need a
hand-pass. **This one is fine — the fix holds, and it has held natively since #84.** Say so rather
than carry it as folklore.

Likewise `templates/dispatch/hooks/tests/**` is *not* repo-protected (§5, item 2), so the hook-test
hygiene work is ordinary. The V6-K debt line asserting otherwise would have manufactured a
hand-pass that was never needed.

### 9.5 The reference-patch gitignore rule — **mostly fine; the comment is wrong**

The rule moved from `.git/info/exclude` into `.gitignore` today (11fbe01), which was correct — it
*was* clone-local, and the comment now says so honestly. But no case was found where its
clone-locality actually lost anything: the three orphaned packets were lost to the freeze-branch
trap (§9.3), not to the ignore rule. **This candidate is smaller than it looks; do not bill it.**

One real defect remains, though: `.gitignore:21-22` states the rule exists so *"a worker's worktree
can never pick one up by accident."* That is not what it does. `prepare_workspace` uses
`git clone`, which never copies untracked or ignored files; and a reference patch committed with
`add -f` in commit 2 is not present at `starting_commit`, so it is not in the checkout either.
The rule's actual and legitimate function is **guarding Rule 10** — stopping a stray `git add .`
from committing the reference at `starting_commit`, which is exactly what voided M-1's first run.
Fix the comment to say the true reason. A rationale that names the wrong mechanism is how a rule
gets deleted by someone who correctly notices the stated mechanism is impossible.

### 9.6 A correction that was described but never made — **found while checking**

093dc77's message says: *"Also corrected while checking: the v5-p1-two-way loop arm's top-level
outcome reads 'no edits produced', which describes attempt 1 of seven… The summary contradicts the
detail beneath it — the same defect class this tract keeps finding."*

`docs/evidence/scorecards/v5-p1-two-way.json:25` **still read** `"outcome": "no edits produced;
gate diff-nonempty false, registered-commands-green false, passed false"`. 093dc77's diff touches
three files, none of them that one.

This is the sharpest dogfooding cost of the day, because it is the failure mode the whole tract is
organised against, appearing in the commit that names it. A commit message is not a record. Nothing
in the repo can catch this class — a message asserting a file changed, when it did not, is
invisible to every gate, every oracle, the read-trace and the merge-preview.

*(Corrected in the same pass that filed this plan.)*

### 9.7 What did *not* cost time

- The oracle-by-independent-author rule (Rule 5) paid, visibly and twice: revision 1's ambiguity
  report found a defect in the *packet* (a field nothing would read) rather than in the test, and
  revision 2's rationale was falsified on real data and corrected rather than shipped. §3h's
  finding that ambiguity reports are worth more than the tests holds for a third time.
- `validate`'s cold gates, `check_oracle_attainable`'s exit-127 rejection, and the reference-patch
  proof all behaved. The V6-K packet was verified red → green → red before freezing, and the
  reference implementation was checked against real transcripts, which is the check the oracle
  structurally could not make.
- The containment probe worked exactly as designed. Attempt 1 failed *because* containment was
  real. That is the system working; the harness just had a read path it had never needed on the
  only host it had ever run on.
