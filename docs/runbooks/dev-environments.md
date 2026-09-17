# Dev environments: per-host setup

On-demand reference moved out of the always-read workspace `AGENTS.md`. Read it when you
are setting up or repairing a host, not at session start. The legacy vscode-shell pod was retired
(appservice d66d397f, 2026-07-30); its setup notes are in git history.

## devbox-vm

- Plain NixOS VM; `/home/agent` and `/projects/dev` persist. System packages come from
  `gitops-nixos/hosts/devbox/` (no sudo; deploy through the infra path).
- Python tools: `uv tool install 'name[extras] @ /projects/dev/<repo>/'` as `agent`
  (lands in `~/.local/bin`). sprintctl needs the `remote` extra, or it fails with
  "psycopg is not installed".
- No cluster tools and no Talos/TrueNAS reach. Its auto-loaded guidance is
  `templates/workspace/CLAUDE.devbox.md`.
- Shared agent assets: `/projects/dev/.claude/scripts/sync-devbox.sh --dry-run`, then
  `--apply`. It never syncs Git state, source, `.envrc` state, secrets, worktrees or tool
  installs, and never deletes remote files.

## Session telemetry

`log-session-cost.sh` (Stop) appends cumulative per-session snapshots to
`/projects/dev/.claude/session-costs.jsonl`, and `gate-log.sh` (PostToolUse) records gate
commands. Rows supersede: reduce to the newest row per `session` before aggregating.
Summary: `agentops/templates/dispatch/hooks/cost-summary.sh [project]`.

## Evidence and durability background

Rationale for the durability table in the workspace `AGENTS.md`:
`docs/plans/agentops/operative-position-durability-2026-08-29.md`. The shard append-only
check (`check_append_only_shards.py`) was retired 2026-09-17 (S2 item 6) with
`templates/dispatch` and has no top-level successor. The producer inventory instrument
(`check_producers.py`) is restored at `scripts/check_producers.py` per TS-12 of
`docs/plans/2026-09-17-target-state.md`: it now scans the top-level contract
directories (`schemas/`, `model/`, `session-mechanization/`, `environment-record/`,
and any other top-level directory holding a `*.schema.json` file) and stays until
the S5 catalog query replaces it.
