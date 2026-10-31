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

## Hook wiring

Run `/projects/dev/agentops/bin/agentops check-hook-wiring` to check workspace,
project and user configurations for Claude and Codex. The scan includes ignored
settings files, executable hook paths and the relative decision-telemetry library.
Exit 1 means wiring is incomplete; exit 0 means every inspected command resolves.
This is a wiring check, not proof that a runtime dispatched a hook.

Run the same command with `--apply` to restore missing aliases to the canonical
`agentops/hooks/` scripts and their `lib/` directory. It preserves existing custom
scripts and never changes command text or guard policy. It also removes redundant
project Stop registrations when the identical cost hook already runs globally.
The global registration and other project settings stay intact.

Workstation Codex user hooks are a Home Manager out-of-store link to that canonical
directory. Workspace aliases under `/projects/dev/.codex/hooks/` and
`/projects/dev/.claude/hooks/` are host-persistent; the scripts and repair tool are
cross-host-replicated in Git. Repair on each host separately. A configured script
that is missing can produce exit 127; a present but non-executable script produces
exit 126. Keep the SessionStart context hooks and their dependencies together.

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

## Audit shards

auditctl hooks append NDJSON shards at `_artifacts/<repo>/audit/events-YYYY-MM-DD.ndjson`
inside each checkout under `/projects/dev`. The Stop hook records into the repository the
session is working in (the event's `cwd`, a worktree mapping to its main checkout), not the
one it was launched in: when that differs, it drops the launch checkout's direnv
`AUDITCTL_DB` / `AUDITCTL_ARTIFACTS_ROOT` pins for that write (agentops#2547).

An existing workspace ledger also supplies a capture scope when it declares
its identity in `.auditctl-id` and `.auditctl/auditctl.db` has a SQLite file header.
For `/projects/dev` the declared identity is `dev`, preserving the historical
scope. The identity file is host-persistent workspace configuration; it does not
turn the parent folder into a Git repository. Workspace observations drop
inherited pins for nested checkouts even when the hook runs in the workspace
and `DIRENV_DIR` is absent. Pins outside the launch/workspace trees remain
explicit overrides. Empty `.git` directories, empty index files, invalid event
paths and uninitialized folders do not opt into routing. This prevents sessions
at `/projects/dev` from filing their observations into `agentops` while leaving
the `dev` ledger stale. Historical observations keep their original identity
and location; this changes future capture only.

**Shards are no longer committed to repositories.** On 2026-09-30 the operator replaced
the hourly `audit-shards-commit` timer with an independent archive (gitops-nixos
`docs/runbooks/audit-persistence.md`, `modules/home/bayleaf/audit-shards.nix`): the
`audit-shards-collect` timer copies every checkout's shards into
`~/.local/state/agentops/audit-recovery` by file glob, without Git, and
`audit-shards-publish` replicates them to the private Forgejo repository
`bayleaf/audit-archive`. That archive is the successor to the repository-shard interim
arrangement of TS-6 until the S4 import (agentops#2485). Shards committed before the
cutover remain authoritative historical records and must not be rewritten; CI's
`check_append_only_shards.py` still guards them. New shards are gitignored here
(`/_artifacts/agentops/audit/`), as they are in every repository that used to commit them.

Do not commit shards by hand, and never inside an unrelated commit. A shard committed while
its UTC day is still open leaves the checkout modified as soon as the next event is
appended; that was the recurring dirty-tree symptom. To close a tracked shard that has grown
since its last commit, wait until its UTC day has ended and run the retained manual command
from gitops-nixos, which wraps `scripts/commit_audit_shards.py` and commits inside the
checkout the hooks write into:

```sh
commit-audit-shards --only <checkout> --dry-run
commit-audit-shards --only <checkout>
```

It commits only shard paths (`git commit --only`), only on the default branch, fast-forwards
first, never force-pushes, and lands through a pull request when the default branch is
protected. Its summary is `~/.local/state/agentops/audit-shards/last-run.json`. Run it in
the checkout itself: a shard committed from another clone or worktree leaves an
untracked or modified twin that makes the next `git pull --ff-only` abort.
