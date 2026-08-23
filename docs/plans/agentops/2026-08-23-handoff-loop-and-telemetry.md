# Hand-off loop and workflow telemetry backlog

Status: draft hand-off (2026-08-23). Pathway: vuoro `docs/plans/2026-08-23-requirements-pathway-v5-v7.md`
G3.1 (R3.1.1–3), G4 (R4.1–4.3), decisions D-8, D-9. Owner: agentops (loop) + dev-env hooks
(telemetry). Consumer: the orchestration-planning session.

Two tracks. Track T (telemetry) ships first and has no gate dependency; Track L (loop) is v7
work but its first packet (L-1) is wanted during v5 so the scorecard has something to read.

## What exists (do not rebuild)

- Implementer loop: `templates/dispatch/scripts/hybrid_dispatch.py` — `validate | overlay |
  prepare | run | gate | receipt`; `candidate` needs an independent review JSON (`:995`);
  never touches main-worktree git history (`:18`).
- Packet contract: `agentops-task/v2`, `templates/dispatch/hybrid/task-packet.schema.json`;
  worked example `hostproto/docs/plans/2026-08-22-wave1-orchestration.md:125-175`.
- Per-repo routing: `*.dispatch.json` (`action_classes`, `risk_surfaces.required_on_change`).
- Gates: actionq `verification/run_round_checks.py`, `tests/test_falsifier_coverage.py`,
  `validate_release_contract.py`; hostproto ordered gate list.
- Cost telemetry: `agentops/templates/dispatch/hooks/log-session-cost.sh` (symlinked from
  `/projects/dev/.claude/hooks/`) → `.claude/session-costs.jsonl`, read by cockpit
  (`apps/web/lib/cockpit/costs.js`). **Landed 2026-08-23 (T-1..T-5):** the hook set moved into
  the repo — it was in no git repository at all, so no packet could have patched it — and
  Stop + PostToolUse are now registered in `/projects/dev`, actionq, agentops, appservice,
  homelab-analytics, kctl and sprintctl; root `AGENTS.md` corrected. (Before the move,
  registration was homelab-analytics, appservice, sprintctl **and kctl** — four repos, not the
  three recorded here.)
- Sink for everything else: `auditctl add --type <free-form> --metadata <json>` (CLI contract
  `auditctl/docs/contracts/publisher-subprocess.md`).
- Running units: only `session-mechanization-{reconcile,scribe}` timers and
  `completion-alert-consumer`. `sprintctl-orchestrator`, `_orchestration`,
  `vuoro-unattended-promotion.md` are dead/superseded — do not revive.

## Track T — telemetry (v4.1)

| # | Item | Gate |
|---|---|---|
| T-1 | **DONE.** `log-session-cost.sh` emits `turns`, `assistant_msgs`, `tool_calls`, `duration_s`, all derived from the transcript (the Stop payload carries none of them) | cockpit summary still renders; old rows unaffected — verified against `cost-summary.sh` and `costs.js`, both field-selective |
| T-2 | **DONE.** Stop + PostToolUse registered in `/projects/dev`, actionq, agentops, appservice, homelab-analytics, kctl, sprintctl; root `AGENTS.md` §"Session workflow telemetry" rewritten | a session in actionq produces a cost row |
| T-3 | **DONE.** `gate-log.sh` (PostToolUse, matcher `Bash`) appends `{ts, cmd, exit, signal, ok}` to `$AGENTOPS_GATE_LOG_DIR/gates-<session>.jsonl`. **Correction:** the Bash tool result carries **no exit code** (verified across transcripts), so each row records which signal decided its verdict — `exit_code`, `is_error`, `interrupted` or `heuristic` — and a consumer needing certainty reads `signal`, not `ok` | file populated in a gated session |
| T-4 | **DONE.** Stop hook drains T-3 → `auditctl add --type workflow.session --source claude-hook --actor claude-hook --summary … --metadata {session,turns,cost_usd,gates[],rework_rounds,…}`; `rework_rounds` = red gate followed by a later retry of the same cmd. **Two corrections:** `--actor` and `--summary` are *required* by the CLI, and `--ref session:<id>` is **rejected** (only `wi:`/`ka:`/`ad:`/`sha:`/`pr:`/`sprint:`/`capsule:` prefixes are allowed), so the session id travels in the metadata. The hook also defaults `AUDITCTL_ARTIFACTS_ROOT=/projects/dev`, since a Stop hook inherits no direnv | auditctl row present — **observed**: `ad:01M0PSA6TX8KD9XB3A9MJ8JRA8`, `rework_rounds: 1` from a red-then-retry pair |
| T-5 | **DONE.** `/friction` skill at `templates/dispatch/skills/friction/`, symlinked into `~/.claude/skills/` so it is invocable from every repo | one note recorded |
| T-6 | `scripts/release_scorecard.py <tag-range>`: frontier turns, cost, cheap-tier first-pass rate, escalations, rework, per release; writes `docs/evidence/scorecards/<release>.json`. **Two sources, not one:** the frontier/coordinator side comes from the hook sink, the worker side from the receipt's `worker_spend` (OpenCode's own accounting, with `cost_reported` distinguishing "free" from "did not say") — the Claude Code hooks never see an OpenCode worker, so a loop run scored from the hook sink alone undercounts itself. **Must also reduce to the newest row/event per session before aggregating — take the max, not the sum**, breaking `ts` ties by magnitude since the snapshots are monotonic and `ts` has one-second resolution — `Stop` fires per turn and each record is a cumulative snapshot, so summing rows over-counts roughly quadratically (measured: $56,485 vs $3,825 actual over 97 sessions). `cost-summary.sh` had this bug and is fixed | v5 scorecard produced from hook data alone; a synthetic multi-stop session aggregates to one session |
| T-7 | "Worse" detector in T-6: flags rework↑ or escalations↑ or turns-flat-cost↑ for two consecutive releases | unit test on synthetic series |

Deferred: OTel receiver on the existing Alloy release + `CLAUDE_CODE_ENABLE_TELEMETRY` — only
when a Grafana consumer exists (pathway E4.4). Cross-host fragmentation of the jsonl/auditctl
sinks is accepted for v4.1; `sync-devbox.sh` dedups cost rows already.

## Track L — unattended hand-off loop (v7, L-1 early)

| # | Item | Gate |
|---|---|---|
| L-1 | Driver `dispatch_release.py <packet>`: prepare → run → gate → receipt, then **`gh pr create`** with the receipt as body, then stop. Never merges. | dry-run on a docs-only packet opens a PR in a sandbox repo |
| L-2a | **DONE 2026-08-23.** Freeze-time oracle attainability: each `starts_red` command is run at `starting_commit` in a throwaway checkout and must be red for a reason other than absence (127 = missing, not failing) and not already green. Killed the exact defect that cost two dispatches | verified on both real packets: fit at `8b1c8b9`, unfit at `775ce5f` |
| L-2b | **DONE 2026-08-23 — both halves.** *Reference-overlay half:* packet `oracle.reference_patch` (optional, repo-relative path to a unified diff under `docs/evidence/packets/` or similar). At `validate`, in the throwaway checkout at `starting_commit`: `git apply --check`, reject if any touched file (from `git apply --numstat`) is outside `writable_patch_paths`, apply, then run each `starts_red` command and require GREEN. Report field `oracle_satisfiable_within_paths: true | false | "skipped:no-reference"` plus `red_after_reference: [ids]`; absent reference → skipped (never true) and a stderr warning. Rule: **a packet for a cheap-tier route SHOULD carry `reference_patch`; mandatory once L-3 `self_candidate` is on for the class.** Closes defects 3 and 4 that the read-trace half could not. *Read-trace half* (earlier the same day): verified on devbox with real strace: V5-P1a → fit; but the original over-broad V5-P1 at 775ce5f is *also* fit, so read-trace catches absent oracles (defect 5) and out-of-path reads, **not** "oracle demands an unstated seam" (defect 3) or "oracle covers the whole T-set" (defect 4) — hence the overlay half. `validate` runs each `starts_red` command at `starting_commit` under `strace -f -e trace=openat,open,stat,readlink`; every file successfully opened for reading inside the checkout must match `readable_context_paths ∪ writable_patch_paths` (exempt: `.git/`, `__pycache__/`, `.venv/`, runner config files, and the test files the command names — one constant, `ORACLE_READ_TRACE_EXEMPT_*`). No `strace` fails closed unless `--allow-untraced-oracle`, which records `"read_trace": "skipped:untraced"`, never `true`. Report field `oracle_reads_within_paths` plus `reads_outside_declared_paths`. Original spec:  prove the failure is caused only by files the packet may write — overlay a reference solution if one exists, else assert every file the failing test reads is inside `readable_context_paths ∪ writable_patch_paths`. Kills the "oracle demands an unstated seam" and "oracle covers three items" defects | a packet whose oracle reads outside its declared paths is rejected at freeze; overlay passes → true, patch outside writable → rejected, overlay applied but command still red → rejected with the id, no reference → skipped marker (all four are unit fixtures) |
| L-1b | **DONE 2026-08-23.** Worker transcript capture: after `run`, `opencode export <session_id>` is written to `<worktree-parent>/<task_id>.worker-session.json` beside the receipt; path and sha256 recorded under `worker_session` in the run receipt and carried into the final receipt / PR body by `dispatch_release.py`. Export failure is recorded as `worker_session.error` and never fails the step | stubbed `opencode` on PATH: success recorded with sha256; failure recorded, run still exits 0 |
| L-2 | Encoded stop conditions: gate red twice on one packet; release-boundary crossing; command outside `allowed_command_ids`; path outside `writable_patch_paths`; escalation record written to auditctl `workflow.escalation` | each condition has a failing fixture |
| L-3 | **DONE 2026-08-23.** `manifest.schema.json` `routing.action_classes[].self_candidate: boolean` (default false) + `self_candidate_ruling` provenance string. `gate`: when the packet's route names a class with `self_candidate: true` **and** every evidence gate passes, disposition is `candidate` with no review record; receipt records `"independent_review": {"mode": "self_candidate", "class": ..., "basis": "manifest"}`. Any red gate, or any class not flipped, keeps the existing review-record requirement unchanged. `validate_hybrid_dispatch.py` rejects a flip that is not enabled, not a hybrid worker route, or has no ruling. `mechanical_bulk` flipped in `agentops.dispatch.json` per owner ruling 2026-08-23: human approval is perpendicular (release / architecture / style boundaries, not per mechanical packet); D-8's ≥5-green rule governs which further classes qualify. **Note:** `mechanical_bulk` was a hybrid *route* and not previously an `action_classes` entry; it is now both, which is the seam the spec left open | schema test + gate fixtures: self_candidate+green → candidate (no record); self_candidate+red → not candidate; other class → record still required |
| L-4 | Retry policy: one cheap retry with the gate output appended to the packet; second red → L-2 escalation | fixture |
| L-5 | Release-unit packet template: one packet per pathway sub-release with its gate set (pathway §5) pre-filled | example packet validates |
| L-6 | D-9 pilot design (Restate on appservice; one actionq review round as 4–8 parallel packets) — **design only**, separately authorized before any manifest lands (memory `orchestration-restate-pilot`) | design doc reviewed |

Sequence: T-1..T-5 (**done 2026-08-23**) → L-1 → L-2 → T-6/T-7 → L-5 → L-3/L-4 → L-6.

## Packet notes

Track T `writable_patch_paths`: `templates/dispatch/hooks/**` (the hook set lives there now;
`/projects/dev/.claude/hooks/` holds symlinks and is in no repository, so it can never be a
patch path), `templates/dispatch/skills/friction/**`, `agentops/scripts/`,
`agentops/docs/evidence/scorecards/`. Per-repo `.claude/settings.local.json` is untracked and
outside every worktree — registration stays a hand step, excluded from any packet. Track L:
`templates/dispatch/scripts/`, `templates/dispatch/manifest.schema.json`, `tests/`.
