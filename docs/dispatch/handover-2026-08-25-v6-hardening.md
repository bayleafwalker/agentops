# Session close, 2026-08-25 (second session) — resume from here

Written for a cold session. Read §1 and §2 first; §6 is the list of traps, and two of them are new.

## 1. State as of this handoff

- `agentops` main at **`430f203`**, working tree clean, **1307 tests green** (15 skipped, the same
  deliberate flip-guards in `test_schema_check.py`).
- Merged this session: **#115 – #124**.
- All 18 `*.dispatch.json` in `/projects/dev` validate.
- **No reservation is held.** Claim id **30** (`workstation-vuoro`, `execution`) was taken for this
  session's three dispatches and **released at close**. Take a fresh one before any dispatch.
- Nothing is in flight. No freeze is waiting to dispatch.

## 2. Where the work stands

`agentops#2046` went from **1 of 6 criteria to 5 of 6.**

| Criterion | State |
|---|---|
| `context_churn` enforced | Built (before this session) |
| Receipts expose churn metrics | **Built and wired** — #115 (module), #117 (receipt) |
| Exact registered-command execution proven inside the worker | **Still partial** — the one left |
| Gate stratification (fast / focused / full) | **Built and wired** — #118 (module), #120 (wiring) |
| Defect-seeded acceptance cases | **Built and wired** — #121 (module), #123 (validate) |
| Corpus comparison attached to `#2017` | Not done — needs the criterion above first |

Three worker rows, all `mechanical_bulk`, all landed. Two were first-attempt green; V6-E needed one
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

## 4. The obvious next row

**Criterion 3: prove exact registered-command execution from inside the contained worker.**
`allowed_command_ids` is granted, and the driver stops on a command outside it — but nothing proves
it from *within* the worker. This is not a pure-logic module, so it does not fit the cheap-tier
split cleanly: it needs the worker container and `AGENTOPS_WORKER_USER`. Plan it as a coordinator
row with a containment probe, the way V6-A did.

After it, criterion 6 (the corpus comparison for `#2017`) becomes answerable, and `#2017` unblocks.

Also newly worth doing, and cheap: **`#2100`** (split `mechanical_patch` vs `build_from_spec`) is
still blocked on the `mechanical_bulk` naming decision, which is an **owner call, not a refactor** —
renaming either changes what every existing packet's `route` means.

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
  cherry-picked commit 2 onto main as a separate PR (#116, #119, #122). Keep doing that, or merge
  the freeze branch — but deliberately.

## 7. Open debt

`docs/evidence/scorecards/v5-m-series.json` → `debt_for_v5_9`. Two more resolved today (§3), so the
open list is shorter. The one still needing an **owner rather than an engineer** is unchanged:
`mechanical_bulk` is both a hybrid route and an action class.
