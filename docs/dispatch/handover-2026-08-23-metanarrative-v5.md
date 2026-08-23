# Handover — metanarrative mode for v5's mechanical remainder

Date: 2026-08-23. From: the coordinating Claude session (owner-attended). To: the planner
session that runs **planner → driver → cheap implementer** and returns to the owner only on
completion or escalation. Owner constraints C-1 (breaking changes allowed), C-2 (hand-off per
gated release), C-3 (move fast, refactor last) apply; see
`vuoro/docs/plans/2026-08-23-requirements-pathway-v5-v7.md` §0.

This document is the whole brief. Read the files it names; do not re-derive them from chat.

## 1. What you are operating

| Piece | Where | State |
|---|---|---|
| Driver | `templates/dispatch/scripts/dispatch_release.py` | prepare → run → gate → receipt → `gh pr create` (dry-run available); never merges |
| Packet engine | `templates/dispatch/scripts/hybrid_dispatch.py` | `validate` (L-2a attainable, L-2b read-trace + `oracle.reference_patch` overlay), `prepare` cold gates, `run` (OpenCode worker, contained), `gate`, `receipt` |
| Packet schema | `templates/dispatch/hybrid/task-packet.schema.json` | `agentops-task/v2`; `oracle.starts_red[]`, `oracle.reference_patch` |
| Manifest | `agentops.dispatch.json` | `mechanical_bulk` is `self_candidate: true` (owner ruling quoted there); commands: `agentops.dispatch.tests`, `agentops.hooks.tests`, `.t1/.t3/.t5`, `agentops.hybrid.validate`, `agentops.session-notes.tests` |
| Worker tier | `opencode-go/deepseek-v4-flash`, route `mechanical_bulk` | qualified 1/5 under D-8 (V5-P1a); proven to write correct code given one outcome, one file, one attainable red oracle |
| Evidence | `docs/evidence/packets/*.json`, `docs/evidence/scorecards/v5-p1-two-way.json`, `docs/evidence/reviews/` | the good packet shape is `V5-P1a-cost-hook-fields.json` |
| Telemetry | `templates/dispatch/hooks/` (symlinked from `/projects/dev/.claude/hooks/`) | Stop hook → `session-costs.jsonl` (max-per-session, never sum) + auditctl `workflow.session`; PostToolUse → gate log; `/friction` skill |
| Work state | sprintctl served backend (`direnv exec .` in agentops); item **agentops#2254**, sprint #428 | reservation 2 active; take your own execution reservation per packet |
| Hosts | coordinator on devbox (`/tmp/v5-coordinator`, user `agent`, has strace + opencode); workstation lacks strace | run `validate` on devbox or pass `--allow-untraced-oracle` and accept `skipped:untraced` in the record |

## 2. The rules that decide edge cases

1. **One packet = one outcome, one writable file (or one tight glob), one `starts_red` command
   the coordinator wrote first.** Every loop failure on 2026-08-23 that was not harness-side
   was a packet that broke this (5 defects, 0 in the model; scorecard has the table).
2. **`oracle.reference_patch` is mandatory on `mechanical_bulk` packets from now on.** The
   coordinator writes a throwaway solution confined to `writable_patch_paths`; `validate` must
   report `oracle_attainable: true`, `oracle_satisfiable_within_paths: true`, and (on devbox)
   `oracle_reads_within_paths: true`. A packet that fails any of these is not dispatched — fix
   the packet, never widen the paths to make it pass.
3. **Already-green is a refusal, not a pass.** If L-2a says the oracle already passes, the work
   is done; record the packet as "refused: already green" and move on (T-3/T-5 precedent).
4. **Human review is perpendicular.** Do not ask the owner to review a packet diff. Owner
   touchpoints are: release boundary (a PR that closes a backlog row), freeze amendments,
   anything the admission policy names coordinator-only (oracle design, authority plane,
   migration, recovery), and the v5.9 refactor pass.
5. **No actor is the sole attester of its own change.** Oracles for code you wrote are written
   by a fresh author (a subagent with no access to your implementation — give it the spec row
   only). Gate evidence + `self_candidate` covers the rest.
6. **Stop conditions** (until L-2 encodes them, you enforce them): gate red twice on one packet
   → escalate, do not retry a third time; any command outside `allowed_command_ids`; any
   touched path outside `writable_patch_paths`; a packet that would cross a release boundary.
   Escalation = auditctl `workflow.escalation` + a line in the scorecard + stop.
7. **Every packet carries a `debt:` line** if it defers a refactor. Under C-3 that is expected,
   not a smell; the list feeds v5.9.
8. **Never merge from the loop.** The driver opens PRs; you merge them only after the gate set
   in §4 is green on `main` after the merge-preview, and only PRs whose packet is a closed
   backlog row. One PR per packet.

9. **Cheap-tier packets are additive** (added 2026-08-23 after M-2): a new function, branch,
   fixture or field. If the reference patch rewrites more than it adds, the packet is coordinator
   work — the tier emits whole-file rewrites and hits the output cap before a write lands
   (V5-M2 attempt 1, `finish_reason: length` at 131k). M-1 (additive, same size) went green first
   attempt; that is the control.
10. **The reference patch is never committed at `starting_commit`** (M-1's first run was void
    because it was). It is mandatory while the class is off and becomes SHOULD once the class is
    on — its cost (~8.5 min + 12 frontier turns per usable implementation vs $0.13 worker spend)
    is not a labour saving; its value is diagnostic.

## 3a. Outcome of the first sequence (2026-08-23) and the re-authorized order

M-7 done (#55). M-1 green first attempt (#56). **M-2 red twice → stopped; withdrawn as a loop
packet** (restructuring; and `prepare` refuses a second worker into an existing workspace, so
L-4 is the packet that would unblock its own retry). M-3/M-4 never freezable: `hybrid_dispatch.py`
is protected. D-8 = **2**. Scorecard: `docs/evidence/scorecards/v5-m-series.json`.

**Owner-authorized coordinator hand-pass (one PR, protected scope):** read-trace fd-relative
`openat` false positive (`parse_strace_reads`); `-e trace=%file`; export timeout from
`packet.limits`; `mechanical_bulk.max_attempts: 2`; `task-packet.schema.json` admits
`release_boundary`; **L-4 retry** in `prepare`/driver (one retry, gate tails appended under
`retry_context`, `attempt: 2`). Oracles by a fresh author. Merge when §4 step 6 is green.

**Then the readiness test restarts:** M-5 (frozen, fit, ready) → **M-8 driver PR step** (add the
coordinator's `origin` remote to the disposable worktree, push the packet branch, `gh pr create
--head`; both M-1 candidates died here). Two consecutive first-attempt greens → class on. Then
M-6 as two packets (one per file, one language each), M-3/M-4 are in the hand-pass.

## 3. Packets to freeze and run, in order

Each row: what the oracle must assert, the writable file, and the spec source. Write the
oracle (via a fresh author) → write the reference patch → `validate` → dispatch.

| # | Packet | Writable | Oracle asserts (from spec, not code) | Spec |
|---|---|---|---|---|
| M-1 | **L-2 stop conditions encoded** in the driver | `templates/dispatch/scripts/dispatch_release.py`, `templates/dispatch/tests/test_dispatch_release.py` | (a) second red gate on the same packet exits non-zero with `workflow.escalation`; (b) touched path outside writable → stop before PR; (c) command id outside allowed → stop; (d) `release_boundary: true` on a packet → stop before run. Each has a failing fixture. | handoff-loop doc row L-2 |
| M-2 | **L-4 retry policy** | same files | exactly one cheap retry after a red gate, with the gate's `stdout_tail`/`stderr_tail` appended to the packet purpose under `retry_context`; second red → M-1's escalation; retry recorded in receipt `attempt: 2` | row L-4 |
| M-3 | strace portable form | `hybrid_dispatch.py` (the trace invocation only) | `-e trace=%file` replaces the explicit syscall list; read-trace test fixtures unchanged and green | debt line, 2026-08-23 |
| M-4 | export timeout into packet limits | `hybrid_dispatch.py` (`export_worker_session`) | timeout read from `packet.limits.timeout_seconds` (bounded ≤ 120 s), not hardcoded | debt line |
| M-5 | T-3 matcher is anchored, not substring | `templates/dispatch/hooks/gate-log.sh` | `echo pytest-is-not-here` produces no row; `pytest -q x` does; existing t3 oracle still green | oracle NOTE in `test-gate-log.sh` |
| M-6 | `AUDITCTL_ARTIFACTS_ROOT` single default | `templates/dispatch/hooks/log-session-cost.sh` + driver | one source of the default (hook sources a shared snippet or the driver passes env); both current tests green | debt line |
| M-7 | review record for V5-P1a into git | `docs/evidence/reviews/` | file present, matches the record at devbox `/tmp/v5-coordinator/docs/evidence/reviews/V5-P1a-cost-hook-fields.review.json` by sha256 | §1 evidence |

M-7 is a copy, not a loop packet — do it by hand first. M-1 and M-2 are the metanarrative
readiness test: **a class is "on" when two consecutive packets frozen without coordinator
hand-inspection pass `validate` and go green first attempt.** Record the outcome in the
scorecard either way.

Not in scope for this mode (stays planner → direct dispatch, owner-attended): appservice
federation-db PR (5.3), vuoro-cloud `principal_epoch` (5.0, D-2/D-3), rule-8 code change
(P-12), 5.4 binding, anything touching a cluster or a credential.

## 4. Gate set per packet (what the driver runs; what you check before merging)

1. `hybrid_dispatch.py validate --packet … ` → `status: fit`, all three oracle fields true
   (or `skipped:untraced` explicitly recorded if run off-devbox).
2. `prepare` cold gates green at `starting_commit` except the declared `starts_red`.
3. `run` → worker exit 0, containment held, under `limits`.
4. `gate` → `diff-nonempty`, `diff-scope-respected`, `protected-paths-untouched`,
   `worktree-state-captured`, `registered-commands-green` all true → `candidate` (self).
5. Receipt + `<task>.worker-session.json` beside it; PR opened with the receipt as body.
6. Before merge: `python -m unittest discover -s templates/dispatch/tests` (482 today),
   `validate_hybrid_dispatch.py`, `bash templates/dispatch/hooks/tests/test-session-telemetry.sh`,
   all green on the merge-preview.

## 5. Measurement you must produce

Per packet, one row in `docs/evidence/scorecards/` (same fields as `v5-p1-two-way.json`):
attempts, first-attempt green (bool), tokens, cost, wall, gate sequence, rework rounds,
escalations, your own frontier turns spent on the packet. Cost rows from the Stop hook are
cumulative snapshots — take the **max per session**, never the sum. Mark "worse" when rework
or escalations rise, or frontier turns stay flat while cost rises, two packets running.

## 6. Known sharp edges

- Hook symlinks point into `/projects/dev/agentops`; do not check out a branch there that lacks
  `templates/dispatch/hooks/` (everything on `main` has it now).
- `SPRINTCTL_BACKEND=local` leaks from some shells; agentops requires served — use `direnv exec .`.
- `/projects/dev/sprintctl` is now at 0.3.2 and current; `sprintctl reservation` is the claim
  API (`claim` no longer exists). Installed tool needs the `[served]` extra.
- `mechanical_bulk` is both a route and an action class since L-3 — a naming debt, not a bug.
- Manifest schema is not machine-enforced (no `jsonschema` on host); the validator holds the
  invariants by hand.
- Worker session store is per-user on devbox; `opencode export` runs as the worker user.

## 7. When to come back to the owner

- M-1 and M-2 both green first attempt → report "class on", continue through M-6 unattended.
- Any packet red twice → stop the sequence, write the escalation, report with the worker
  transcript path and the gate evidence; do not reshape the packet yourself beyond one retry.
- Anything that would require editing a protected path to proceed → stop, report.
- After M-6: full scorecard, the `debt:` list for v5.9, and the reference-patch-mandatory rule's
  cost (how long the coordinator spent writing throwaway solutions per packet — that is the
  number that decides whether the cheap tier pays for itself).
