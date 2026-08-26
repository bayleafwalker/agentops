# Session close, 2026-08-25 (second session) — resume from here

Written for a cold session. Read §1 and §2 first; §6 is the list of traps, and two of them are new.

## 1. State as of this handoff

- `agentops` main at **`ddc8fd0`** or later, working tree clean, **1341 tests green** (15 skipped,
  the same deliberate flip-guards in `test_schema_check.py`).
- Merged this session: **#115 – #131**.
- All 18 `*.dispatch.json` in `/projects/dev` validate.
- **No reservation is held.** Claim **30** covered the first three dispatches and **31** covered
  V6-H; both were released at close. Take a fresh one before any dispatch.
- Nothing is in flight. No freeze is waiting to dispatch.

## 2. Where the work stands

`agentops#2046` went from **1 of 6 criteria to 6 of 6** — all met, **awaiting human acceptance**
(the manifest sets `acceptance_authority: human`; I have not marked the item done).

| Criterion | State |
|---|---|
| `context_churn` enforced | Built (before this session) |
| Receipts expose churn metrics | **Built and wired** — #115 (module), #117 (receipt) |
| Exact registered-command execution proven inside the worker | **Built and wired** — #127 (module), #129 (receipt + containment gate) |
| Gate stratification (fast / focused / full) | **Built and wired** — #118 (module), #120 (wiring) |
| Defect-seeded acceptance cases | **Built and wired** — #121 (module), #123 (validate) |
| Corpus comparison attached to `#2017` | **Done** — #130, attached as ref #707/#708. Its finding is that the corpus **cannot yet carry an admission decision**; see §3a |

Four worker rows, all `mechanical_bulk`, all landed. Three were first-attempt green; V6-E needed one
retry (§6). Each followed the same split, which is now the established shape for anything touching
protected code: **the worker writes a new pure-logic module, the coordinator hand-passes the
wiring.** `hybrid_dispatch.py`, `manifest.schema.json` and `templates/dispatch/hybrid/**` are
protected at the manifest level and no packet can make them writable.

### What is actually new in the mechanism

- **Receipts now carry `worker.churn_metrics`** on every run, stopped or not. A healthy run used to
  be a bare `churn_stop: None`, indistinguishable from one that stopped a single read short of its
  limit. Real example from V6-G: 10 tool events, 8 steps without mutation, 5 distinct paths, and 4
  *incomplete* tool events that were previously invisible.
- **Gates run in tiers** (`fast` → `focused` → `full`), and the gate stage stops early on a red
  tier. `required-gates-complete` is a new post-gate: once a run may stop early, "everything that
  ran was green" is no longer the same claim as "everything required ran". Packets that declare no
  `gate_tiers` plan one `full` tier and are unaffected.
- **`validate` runs defect seeds.** A seed patch is applied *on top of the reference* and must turn
  the named oracle commands RED. A seed that leaves the oracle green makes the packet **unfit**.
  `acceptance-properties-discriminating` only ever checked that a `fails_when` string was present.

## 3. The two debts that were eating the evidence

Both fired three times today — **every** receipt this session was withheld — and they compound.
Fixed together in #124.

- The secret scan ran over **JSON-escaped** transcript text, where a newline is the two characters
  `\` and `n`. `secret_assignment` bounds its value with `\S{20,}`, which stops at a real newline
  and not at an escaped one, so the run crossed line boundaries. What matched was
  `WORKER_PLACEHOLDER_API_KEY = "local-only"` — an eleven-character value whose apparent length was
  entirely escapes. **The recorded debt's explanation (`TOKEN = re.compile(...)`) was a guess and
  was wrong.** The scan now decodes escapes first, which also *finds* secrets that `\"` had hidden.
- A withholding wrote **nothing at all**, and `worker_totals` reads receipts — so a tract with a
  withheld receipt was silently short while `cost_reported` stayed true. A withholding now writes a
  stub receipt (numbers and pattern names only, re-scanned before writing) shaped so
  `worker_totals` reads it as a full receipt.

Both entries in `docs/evidence/scorecards/v5-m-series.json` → `debt_for_v5_9` are updated with what
was actually true, not what was predicted.

## 3a. The corpus comparison's finding — read this before qualifying anything

`#2017` now has the measured comparison (`docs/evidence/corpus/`, ref #707). It says **do not admit
the pair on this corpus**, and the reason is not the model:

- one pair only: `mechanical_bulk` / `opencode-go/deepseek-v4-flash`, 19 receipts, first-pass **1.0**;
- but **five dispatched rows are missing from `docs/evidence/receipts/` entirely**, and `V6-E` — the
  single row that went red on attempt 1 — is one of them. Including them: **23/24 ≈ 0.958**;
- the generated scorecard still says `cost_reported: true` and `total_reliable: true`, because every
  receipt it *can* see reported. **A corpus with a hole in it yields a reliability flag that is true
  and a rate that is wrong.**

Fixed forward by #124 (a withholding now writes a countable stub). The five historical rows must be
**backfilled from the dispatch logs or declared lost — the corpus must state which.** That is the
next concrete task and it is small.

## 4. The next rows

1. **Backfill or write off the five missing receipts** (§3a), then re-measure. Until then no
   qualification claim is auditable.
2. **Dispatch two or three ordinary rows.** They will be the first receipts to carry
   `command_evidence` and `churn_metrics` by construction — today it is 0 of 19 and 1 of 19.
3. **`#2100` needs an owner ruling, not engineering.** The decision document is written and attached
   (ref #709): `docs/plans/agentops/2026-08-25-mechanical-bulk-boundary-decision.md`. It found the
   item's premise is **stale** (`oracle.starts_red` is already the expected-failure receipt it asks
   for; all 34 packets carry one) and that the route/class collision is *enforced* by
   `validate_hybrid_dispatch.py:182`. Five owner calls are listed. Nothing was applied.

## 5. The mechanism, unchanged

Freeze shape, oracle discipline and L-2a/L-2b validation are as described in
`handover-2026-08-23-metanarrative-v5.md` §§2–4 and last session's close. Commit 1 of a freeze
carries the oracle and its command id and **is** the `starting_commit`; commit 2 carries the packet
and reference patch. Coordinator workspace is `/tmp/v5-coordinator` on `devbox-agent`, a git
worktree of that host's `/projects/dev/agentops`.

Dispatch from `/tmp/v5-coordinator` with `SPRINTCTL_BACKEND=served` and the **devbox** profile
(`devbox-agent-vuoro-shared.json`); the workstation uses `workstation-vuoro-shared.json` and the
wrong one fails with "cannot stat the configured credential file".

```
python3 templates/dispatch/scripts/hybrid_dispatch.py validate --packet <packet>
python3 templates/dispatch/scripts/dispatch_release.py <packet> --repo-root /tmp/v5-coordinator --agentops-root /tmp/v5-coordinator
```

`dispatch_release.py` takes its packet **positionally**.

## 6. Traps

The previous handover's §7 all still holds. These are the ones this session paid for:

- **Never run a dispatch through a foreground ssh pipe.** A driver killed mid-run leaves
  `/tmp/agentops-hybrid/worktrees/agentops/<task>` behind, and the next `prepare` refuses with
  "already exists; never dispatch two workers into one workspace" — which is the guard working.
  Launch it `setsid nohup … > /tmp/<task>-dispatch.log` and poll. The leftover workspace is a
  **clone, not a git worktree**, so `git worktree list` does not show it and plain `rm -rf` is the
  correct cleanup.
- **A killed worker may already have written its file.** The first V6-E attempt had produced
  `churn_metrics.py` before it was killed. It was discarded, not reused: work that never passed a
  gate is not evidence. Re-dispatching cost one run and produced an independent second
  implementation that agreed with the first on everything but where `failed_mutation_runs`
  increments — genuinely useful corpus evidence for `#2017`.
- **V6-E's first attempt produced an empty diff** — the worker did nothing at all, gate red on
  `diff-nonempty`. The L-4 retry, with the gate output appended to the purpose, went green. This is
  the first observed instance of that failure mode; the two later rows were first-attempt green.
- **Do not rewrite a protected JSON file with `json.dumps`.** It expands every compact array and
  turns a one-line change into a 96-line reformat. Edit those files as text.
- **`strace` is not on the workstation**, so `validate` fails closed there with an oracle fault.
  Use `--allow-untraced-oracle` locally (it records `skipped:untraced`, never `true`) or validate on
  devbox, which has it.
- **Merging the worker's PR still loses the packet.** Commit 2 is not in it. Every row this session
  cherry-picked commit 2 onto main as a separate PR (#116, #119, #122). **Settled 2026-08-26 — see
  §10. Merge the freeze branch; do not cherry-pick.** The trap is recorded here for why, not as a
  live choice.

## 7. Open debt

`docs/evidence/scorecards/v5-m-series.json` → `debt_for_v5_9`. Two more resolved today (§3), so the
open list is shorter. The one still needing an **owner rather than an engineer** is unchanged:
`mechanical_bulk` is both a hybrid route and an action class.

## 8. Added after the fact — criterion 3 and the corpus

The last two criteria were closed after §4 above was first written, so read §3a and §4 as current.

- **Criterion 3 needed no new containment machinery.** `build_overlay` already denies every bash
  call that is not character-for-character a registered command (`{"*": "deny"}` plus one exact
  `allow` per granted id). Nothing had ever read whether it *held*. It did, on all four rows:
  each ran its granted command exactly, and three also attempted a foreign `ls` the harness refused.
  The work was reading the evidence, not building the boundary — worth remembering before designing
  a probe for something that may already be observable.
- **An ungranted command that *completed* is now a `containment_breach`, exit 3** — the same door
  and exit code as a write outside the disposable worktree. A *denied* foreign call is the opposite:
  the boundary holding, recorded as an attempt that did not complete.
- **`stream_events()`** now names the JSON-lines parse once. `dispatch_worker` parses live so churn
  can stop a circling worker mid-run; gate-side readers have only captured stdout. Two parses of one
  stream is how two readers drift apart.

## 9. Final state of this session

- main at `1c17227` or later, **1368 tests green**, tree clean, no reservation held (claims 30, 31
  and 32 were all released).
- **Five worker rows** landed: V6-E, V6-F, V6-G, V6-H, V6-I. Four first-attempt green; V6-E needed
  one retry.
- `agentops#2046`: **all six criteria met, awaiting human acceptance.** I did not mark the item done.
- Corpus: **23 receipts, first-pass 0.9565**, `command_evidence` on 1, `churn_metrics` on 4. Growing
  by construction now.

### Two corrections this session made to its own earlier work

- The `#124` scan fix was **incomplete**. A transcript is escaped *twice* by the time it reaches the
  receipt text; one decode pass left the false positive standing. Completed in #133, which also
  documents the trade it makes — after two levels of escaping, "a literal backslash then n" and "a
  doubly-escaped newline" are indistinguishable, and the scanner now reads them as a newline.
- The first corpus document said **five** rows were missing and estimated 23/24. Both wrong: it is
  fifteen packets without a receipt, three receipts without a packet, and the measured rate moved
  from 1.0 to 0.9545 once the failing row was returned. Corrected in place with a §0 that says so.

### A trap worth carrying

**A packet's own `protected_paths` can forbid the file it is meant to write.** V6-I failed `validate`
with "intersects a protected path" even though the manifest does not protect `schema_check.py` — the
packet's list, inherited by copying an earlier packet, did. Check `protected_paths` against
`writable_patch_paths` when deriving a packet from another. `templates/dispatch/tests/**` staying
protected is deliberate and must not be relaxed: it is what stops a worker editing its own oracle.

---

## 10. Settled 2026-08-26 — the freeze branch is merged, not cherry-picked

This closes the half of debt #8 that was never a cleanup.

**The decision.** When a worker row lands, **merge its freeze branch.** Do not merge the worker's PR
alone and cherry-pick commit 2 after it. One merge carries both commits — the oracle at commit 1 and
the packet plus reference patch at commit 2 — and an orphaned packet becomes structurally impossible
rather than something a closing evidence pass has to remember.

**Why the old way had to go.** It cost one extra PR per row and it did not actually remove the loss
mode, only narrowed the window: #116, #119, #122, #128 and #135 were five PRs doing nothing but
carrying five commit-2s that the merge should have brought with it. Between merging the worker's PR
and remembering the cherry-pick, the packet is still only reachable from a branch someone is about
to delete. Three packets were lost in exactly that window.

**The three that were lost are back, and provably the right ones.** `V5-M13-retry-branch` came from
`origin/v5-m13-freeze` (`9882638`); `V6-B-build-scorecard-iterable` and `V6-C-audit-schema` came from
unreferenced objects (`3f6df37`, `f90336e`) — `git fsck --lost-found` finds them, they are not gone
until gc runs.

Do not accept a recovered packet on the strength of its filename. Each one was re-serialised exactly
the way `_receipt` does it (`hybrid_dispatch.py:2156` — `sort_keys=True`, `separators=(",",":")`) and
its SHA-256 checked against the `inputs.packet_hash` the receipt already carried. All three matched
byte-for-byte at `attempt: 1`, so every `execution_id` re-links to the packet it was really
dispatched from. **That check is the reason to believe the corpus, and it is cheap — do it.**

Every receipt in `docs/evidence/receipts/` now has its packet. The corpus document's §2 no longer
records an unexplained asymmetry; the fifteen packets with no receipt remain, declared lost, for the
separate and benign reason that they predate receipt capture.

**Reference patches are gitignored — `git add -f` them.** That trap is what makes a recovery look
complete when only half of it committed. Note that until 2026-08-26 this advice was only true on
*this machine*: the rule lived in `.git/info/exclude`, which is clone-local and uncommitted, so a
fresh clone had no such rule and the instruction would have read as false. It is now in the tracked
`.gitignore`, with the reason recorded beside it. Already-tracked patches are unaffected — a
`.gitignore` rule does not untrack anything.
