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
Summary: `agentops/hooks/cost-summary.sh [project]`.

## Evidence and durability background

Rationale for the durability table in the workspace `AGENTS.md`:
`docs/plans/agentops/operative-position-durability-2026-08-29.md`. The shard append-only
check was retired with `templates/dispatch` on 2026-09-17 (S2 item 6) and restored
under TS-6 at `scripts/check_append_only_shards.py`, run by
`.github/workflows/protected-paths.yml`. The producer inventory instrument
(`check_producers.py`) is restored at `scripts/check_producers.py` per TS-12 of
`docs/plans/2026-09-17-target-state.md`: it now scans the top-level contract
directories (`schemas/`, `model/`, `session-mechanization/`, `environment-record/`,
and any other top-level directory holding a `*.schema.json` file) and stays until
the S5 catalog query replaces it.

## Committing audit shards

auditctl hooks append NDJSON shards at `_artifacts/<repo>/audit/events-YYYY-MM-DD.ndjson`
inside each checkout under `/projects/dev`. Under TS-6 the committed shards are the
authoritative evidence until the S4 import, so they must reach each repository's
default branch.

`scripts/commit_audit_shards.py` does this unattended and **replaces the Stop hook**
that used to commit "chore(audit): append today's shard" (it never fired in headless
runs, and shards were committed by hand from 2026-08-30). A systemd user timer on the
workstation runs it 10 minutes after login and hourly after that (gitops-nixos
`modules/home/bayleaf/audit-shards.nix`, unit `audit-shards-commit`). Per checkout it
commits only shard paths (`git commit --only`), inside the checkout the hooks write into,
and only on the default branch; it fast-forwards first, pushes without force, and retries
a lost push race. It skips and reports a checkout that is on a feature branch, cannot
fast-forward, carries unpushed non-shard commits, or holds a rewritten shard.

When the default branch is protected (the push is refused with a protected-branch
message, as on Forgejo `bayleaf/cred-broker`), the commit lands by pull request: it is
pushed without force to `audit/shards-<date>` (or fast-forwards the open shard PR's
branch), a PR is opened with `fj pr create` or `gh pr create`, the PR diff is checked to
be shard appends only, and once every check has passed it is merged at the exact head
(`credctl merge --style fast-forward-only` on Forgejo, `gh pr merge --match-head-commit`
on GitHub) and the checkout is fast-forwarded. Checks still running after `--ci-wait`
(300 s) leave the PR open (`pr-open`) for the next hourly run; a failed check, a refused
merge or a non-shard diff is reported as `needs-operator` with the PR URL, and so is a
PR still waiting after a day (`pr-stale`). Forgejo PR and status reads use the REST API
anonymously (`$FORGEJO_TOKEN` if set). `--protected <checkout>` skips the direct push.

Where to look: `journalctl --user -u audit-shards-commit` (one JSON line per repo) and
`~/.local/state/agentops/audit-shards/last-run.json`. A skip that leaves shards
uncommitted fails the unit, so it appears in the failed-user-unit notification and the
shell's `failed user units:` line. A checkout parked on a feature branch while its hooks
write shards keeps the unit failed on every run until it returns to the default branch. Commit by hand only for a skipped checkout, in that
checkout, with `git commit --only -- <shard paths>`: a shard committed from another
clone or worktree leaves an untracked twin that makes the next `git pull --ff-only`
abort. Dry run: `python3 scripts/commit_audit_shards.py --dry-run`.
