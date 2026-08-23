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
- Cost telemetry: `/projects/dev/.claude/hooks/log-session-cost.sh` → `.claude/session-costs.jsonl`,
  read by cockpit (`apps/web/lib/cockpit/costs.js`). Registered only in homelab-analytics,
  appservice, sprintctl — **not** actionq or agentops (AGENTS.md:167 over-claims).
- Sink for everything else: `auditctl add --type <free-form> --metadata <json>` (CLI contract
  `auditctl/docs/contracts/publisher-subprocess.md`).
- Running units: only `session-mechanization-{reconcile,scribe}` timers and
  `completion-alert-consumer`. `sprintctl-orchestrator`, `_orchestration`,
  `vuoro-unattended-promotion.md` are dead/superseded — do not revive.

## Track T — telemetry (v4.1)

| # | Item | Gate |
|---|---|---|
| T-1 | Extend `log-session-cost.sh` jq object with `turns` (user messages), `assistant_msgs`, `tool_calls`, `duration_s`; keep record backward-compatible for cockpit | cockpit summary still renders; old rows unaffected |
| T-2 | Register the Stop hook in `actionq/.claude/settings.local.json` and `agentops/.claude/settings.local.json`; fix AGENTS.md:167 claim | session in actionq produces a cost row |
| T-3 | `PostToolUse` hook (matcher: pytest / run_round_checks / hybrid_dispatch gate / cargo test) appends `{cmd, exit, ts}` to `$SCRATCH/gates.jsonl` | file populated in a gated session |
| T-4 | Stop hook drains T-3 → `auditctl add --type workflow.session --source claude-hook --ref session:<id> --metadata {turns,cost_usd,gates[],rework_rounds}`; `rework_rounds` = red gate followed by a retry of the same cmd | auditctl row present |
| T-5 | `/friction` skill → `auditctl add --type workflow.friction --summary "<note>"` | one note recorded |
| T-6 | `scripts/release_scorecard.py <tag-range>`: frontier turns, cost, cheap-tier first-pass rate, escalations, rework, per release; writes `docs/evidence/scorecards/<release>.json` | v5 scorecard produced from hook data alone |
| T-7 | "Worse" detector in T-6: flags rework↑ or escalations↑ or turns-flat-cost↑ for two consecutive releases | unit test on synthetic series |

Deferred: OTel receiver on the existing Alloy release + `CLAUDE_CODE_ENABLE_TELEMETRY` — only
when a Grafana consumer exists (pathway E4.4). Cross-host fragmentation of the jsonl/auditctl
sinks is accepted for v4.1; `sync-devbox.sh` dedups cost rows already.

## Track L — unattended hand-off loop (v7, L-1 early)

| # | Item | Gate |
|---|---|---|
| L-1 | Driver `dispatch_release.py <packet>`: prepare → run → gate → receipt, then **`gh pr create`** with the receipt as body, then stop. Never merges. | dry-run on a docs-only packet opens a PR in a sandbox repo |
| L-2 | Encoded stop conditions: gate red twice on one packet; release-boundary crossing; command outside `allowed_command_ids`; path outside `writable_patch_paths`; escalation record written to auditctl `workflow.escalation` | each condition has a failing fixture |
| L-3 | D-8: qualification rule in `manifest.schema.json` — `action_classes[].self_candidate: bool`; cheap-tier review record accepted for `self_candidate` classes only; `hybrid_dispatch.py:995` unchanged for the rest | schema test + one class (`mechanical_bulk`) flipped after ≥5 green first-pass with 0 escalations (read from T-6) |
| L-4 | Retry policy: one cheap retry with the gate output appended to the packet; second red → L-2 escalation | fixture |
| L-5 | Release-unit packet template: one packet per pathway sub-release with its gate set (pathway §5) pre-filled | example packet validates |
| L-6 | D-9 pilot design (Restate on appservice; one actionq review round as 4–8 parallel packets) — **design only**, separately authorized before any manifest lands (memory `orchestration-restate-pilot`) | design doc reviewed |

Sequence: T-1..T-5 (one packet) → L-1 → L-2 → T-6/T-7 → L-5 → L-3/L-4 → L-6.

## Packet notes

Track T `writable_patch_paths`: `/projects/dev/.claude/hooks/`, per-repo
`.claude/settings.local.json` (untracked — the packet must say so, or the untracked-file guard
misreads it), `agentops/scripts/`, `agentops/docs/evidence/scorecards/`. Track L:
`templates/dispatch/scripts/`, `templates/dispatch/manifest.schema.json`, `tests/`.
