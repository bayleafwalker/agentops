# Session close, 2026-08-25 — resume from here

Written for a cold session. Read §1 and §2 before touching anything; §7 is the list of traps that
cost time today.

## 1. State as of this handoff

- `agentops` main at **`b336224`**, working tree clean, **1168 tests, green** (15 skipped, all
  deliberate flip-guards in `test_schema_check.py`).
- **No reservation is held** on `agentops#2254`. Take a fresh one before any dispatch.
- Merged today: **#98 – #112**.
- Every `*.dispatch.json` in `/projects/dev` validates — 18 of 18.
- One agent may still be running: an oracle author for the first row of `agentops#2046`, writing
  `templates/dispatch/tests/test_churn_metrics.py`. If that file is present and uncommitted, §4
  says what to do with it. If it is absent, the row was never started and nothing is lost.

## 2. Where the work stands

**Closed today:** the v5.9 refactor pass (C-3), the V6 visibility tract, and `agentops#2053`.
Track T and Track L of `docs/plans/agentops/2026-08-23-handoff-loop-and-telemetry.md` are complete
— every row including L-6, whose design is at
`docs/plans/agentops/2026-08-25-l6-d9-restate-pilot-design.md`.

**Open and started:** `agentops#2046` (p1, `hybrid-dispatch`). It is a **tract, not a packet** —
five acceptance criteria. Measured against the code today:

| Criterion | State |
|---|---|
| `context_churn` enforced | **Built** — `churn_verdict`, `hybrid_dispatch.py:1565` |
| Receipts expose churn metrics | **Not built** — this is the row that was starting; see §4 |
| Exact registered-command execution proven inside the worker | Partly — `allowed_command_ids` is granted and the driver stops on a command outside it; nothing proves it from inside the worker |
| Gate stratification (fast falsifiers / focused / one full suite) | **Not built** — no `tier`/`stratif` anywhere |
| Defect-seeded acceptance cases | **Not built** |
| Corpus comparison attached to `#2017` | Not done |

**Open, unstarted, in this lane:** `#2017` (p3, blocked by #2046), `#2054`/`#2057`/`#2058`
(unblocked today by closing #2053), `#2039` (p1, cockpit network paths — different lane).

## 3. Changes outside agentops — two are committed and NOT pushed

Check these before assuming the tree is clean:

- **`/projects/dev/local-inference`** — `4e6dfff`, *committed, not pushed, and the repo has no
  remote configured* (31 unpushed commits predate today). Its `local-inference.dispatch.json` was
  never a dispatch manifest: five forbidden properties, none of the seven required. It is now a
  real one (`schema_version: 1`, because 2 requires an `instruction_set` there isn't one). The
  prose that had no home in the schema moved verbatim to `docs/09-dispatch-boundaries.md`.
  **The repo also has unrelated uncommitted edits** (`HANDOFF.md`, `docs/06-`, `docs/08-`) that
  are not mine — leave them.
- **`/projects/dev/bindery-core`** — `ba6276d`, *committed, not pushed*, one commit ahead of
  `origin`. Adds `.envrc` and a `.gitignore` entry. Also created `.sprintctl/backend.json`
  (gitignored, local only).

**Filed externally:** `sprintctl#2305` on sprint #539, track `served-catalog` — see §6.

## 4. If `test_churn_metrics.py` exists

The row: `churn_verdict` stops a circling worker but **records nothing when it does not stop**, so
`churn_stop: None` on a healthy run is indistinguishable from a worker that hit four reads of one
path against a limit of four. Sprint item #2046 asks in as many words for receipts to record
enough to detect repeated reads and long no-mutation loops.

The seam given to the oracle author was `templates/dispatch/scripts/churn_metrics.py` exposing
`churn_metrics(events) -> dict` with `tool_events`, `max_steps_without_mutation` (**high-water
mark, not the final value** — that is the most likely wrong implementation),
`max_repeated_reads`, `most_read_path`, `distinct_paths_read`, `completed_mutations`,
`failed_mutation_runs`, `incomplete_tool_events`. It must import `MUTATION_TOOLS` from
`hybrid_dispatch` rather than restating it, and must agree with `churn_verdict` by an iff on the
threshold crossing.

To resume: read the author's report if you have it, run the file, confirm it is red on the absent
module, write the reference, freeze, validate, dispatch. `churn_metrics.py` is a **new file**, so
it is worker-writable — unlike `hybrid_dispatch.py`. Wiring the metrics into the receipt is a
second, coordinator-only row (§7).

If the file is absent, drop it; nothing else depends on it.

## 5. The mechanism, unchanged

Freeze shape, oracle discipline and L-2a/L-2b validation are as described in
`handover-2026-08-23-metanarrative-v5.md` §§2–4. Commit 1 of a freeze carries the oracle and its
command id and **is** the `starting_commit`; commit 2 carries the packet and reference patch.
Coordinator workspace is `/tmp/v5-coordinator` on `devbox-agent` — note it is a **git worktree of
`/projects/dev/agentops`**, not a clone, so it cannot check out a branch that host already has out.

Dispatch, from `/tmp/v5-coordinator`, with `SPRINTCTL_BACKEND=served` and
`SPRINTCTL_VUORO_PROFILE=templates/dispatch/environment-record/profiles/devbox-agent-vuoro-shared.json`,
piping a base64'd script into `bash` because nested quoting eats `cd`:

```
python3 templates/dispatch/scripts/hybrid_dispatch.py validate --packet <packet>
python3 templates/dispatch/scripts/dispatch_release.py <packet> --repo-root /tmp/v5-coordinator --agentops-root /tmp/v5-coordinator
```

`dispatch_release.py` takes its packet **positionally**. The flag form silently sends `--packet`
into passthrough and `prepare` dies on malformed argv.

Today's rate: **eleven worker rows, eleven first-attempt greens.** Nothing needed a retry.

## 6. Reported to sprintctl (#2305) — do not re-diagnose

`work.maintain.check` returns opaque `operation-handler-failed` for any repo with **zero sprints**
(3/3 reproduced: bindery-core, auditctl, outctl) and succeeds where sprints exist (3/3: agentops,
kctl, sprintctl). The same condition surfaces cleanly as `sprint-not-found` through
`work.read.next-work`, so typed rejections propagate in general and this handler is the exception:
`_maintain_check` resolves its sprint inside a `repeatable_read_snapshot` context
(`work_application.py:501`, 529–532) and the typed 404 from `_resolve_sprint` (979–983) is
flattened crossing that boundary.

Separately, `served_routes.py:203` marks `maintain check` `"unavailable"`, so sprintctl's own CLI
refuses an operation its adapter serves (`vuoro_adapter.py:401`). The route table is stale.

**`sprintctl next-work` is broken through the served adapter** (`adapter-result-invalid`) — use
`sprintctl item list` to see the queue. This is a long-standing known observation and is *not*
covered by #2305.

## 7. Traps that cost time today

- **`hybrid_dispatch.py` is protected at the MANIFEST level** (`agentops.dispatch.json` →
  `hybrid.protected_paths`), not merely per packet. No packet can make it writable; `validate`
  refuses with "intersects a protected path". Anything touching it is a coordinator hand-pass. The
  same is true of `manifest.schema.json`, `templates/dispatch/hybrid/**`, `model-routing.json` and
  `.claude/**`. Plan around it by putting new logic in a **new module** the worker may write and
  wiring it in by hand.
- **Parallel freezes collide.** Every freeze registers a command id in `agentops.dispatch.json`;
  three frozen off the same main conflicted on merge. Resolve by taking the **union** of
  `hybrid.commands` — never one side wholesale. This is the fan-out blocker the L-6 design named.
- **Deleting a freeze branch after merging the worker's PR loses the packet.** The worker's PR is
  cut from commit 1; the packet and reference live in commit 2. Three packets were lost this way
  and recovered from unreferenced objects. Restore them in the closing evidence pass, or merge the
  freeze branch — but pick one deliberately.
- **A withheld receipt is invisible to the scorecard.** `worker_totals` reads receipts and cannot
  count one that was never written, so a tract with a withheld receipt is silently short while
  still reporting `cost_reported: true`. V6-D's receipt was withheld on a secret-scanner false
  positive (`TOKEN = re.compile(...)` matched `secret_assignment`).
- **A scorecard generated during the session it measures reports `frontier: 0`.** The Stop hook
  writes per turn; a long single turn has written nothing yet. Read it as "not measured".
- **Reference patches are gitignored** — `git add -f` them.
- **`AGENTOPS_WORKER_USER` decides whether the containment probe runs at all.** Exported in
  devbox's agent shell, unset on the workstation. Both hosts have `agentworker` and working
  passwordless sudo to it. V6-A made the skip visible in the receipt; the variable still governs.

## 8. Open debt

`docs/evidence/scorecards/v5-m-series.json` → `debt_for_v5_9` is the live list: **10 open**,
each with what it is, where it was found, and why it was not fixed. Two entries were marked
resolved in this handoff because the V6 tract closed them the same day they were found — check
that list against the code before trusting it, which is the whole point of C-3.

The one needing an owner rather than an engineer: **`mechanical_bulk` is both a hybrid route and
an action class.** Renaming either changes what every existing packet's `route` means. That is a
boundary decision, not a refactor.
