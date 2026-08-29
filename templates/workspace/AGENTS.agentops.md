## Agentops repository contracts

## Workstation workspace storage

On the workstation, `/projects/dev` is local Btrfs storage. TrueNAS NFS is
only a migration and emergency-recovery source, never a writable live Git
workspace. The initial local recovery policy retains seven daily and four
weekly read-only Btrfs snapshots. devbox-vm has an independent workspace tree;
do not assume ignored state, tool installations, cost logs, or Git worktrees
propagate between environments.

`/projects/dev/agentops` is the canonical source for shared dispatch skills,
manifest schemas, state-protocol context/result schemas, and the dependency-free
repository gate.

Always `git fetch origin` before trusting local repo state. Local `main` silently
falls behind origin between sessions/environments; a commit hash, plan doc, or
item referenced by a handover can look "not found" purely because it hasn't been
fetched yet. Fetch first, then fast-forward or rebase local `main` onto the
fetched remote before starting new work. If a rebase or merge produces conflicts,
resolve them directly (read both sides, merge the actual intent) rather than
aborting or force-picking one side; only stop and flag it to the user if a
conflict can't be resolved confidently.

GitHub CLI access on the workstation is intentionally available outside the
Codex filesystem/network sandbox. A sandboxed `gh auth status`, `gh repo`,
`gh pr`, `gh run`, or other GitHub API failure is therefore inconclusive. Retry
the required `gh` command with sandbox escalation before diagnosing expired
authentication, unavailable networking, or asking the operator to log in. Do
not report GitHub as blocked from sandbox-only evidence. If the escalated retry
fails, report that exact outside-sandbox result. Use the narrowest reusable
`gh` command prefix appropriate to the requested operation.

- Repositories opt in with one root `*.dispatch.json` and repository-specific overlays under `.agents/overlays/`.
- Reusable verification intent belongs in data-only `verification/contexts/*.json`; executable tests and production logic remain in the owning repository.
- Inspect declared `risk_surfaces` before changing queue, claim, lease, retry, recovery, projection, publication, reconciliation, or backend-parity paths.
- Run `python /projects/dev/agentops/templates/dispatch/scripts/validate_verification_artifacts.py --root .` from an opted-in repository.
- `full` is a sequence, not blanket repair authority. Repair and production mutation remain separately authorized.

## ActionQ retirement boundary

ActionQ 0.1.26 removed `actionq-daemon`, its harness/worktree/session execution
plane, and the standalone `actionq-server` source. `actionq-dispatcher` 0.2.0 is
an inactive, fail-closed tombstone: do not install, invoke, or schedule it for
new work. An existing host may upgrade to the tombstone once so a stale
`dispatcher-once` shim fails clearly, then remove it after operator-owned
callers and services are retired.

Repository retirement and running-system retirement are different facts. Do
not claim the appservice server or devbox unit is gone without operator rollout
evidence. The gated order remains appservice phase 1 and health proof, then
phase 2 and health proof, then interactive disablement of the devbox unit and
the separately reviewed NixOS retirement. Do not revive the removed daemon by
bumping its pinned revision.

## Vuoro served-work cutover

Normal shared Sprintctl work is moving to the durable `vuoro-shared` served API.
`vuoro-dev` is ephemeral and is reserved for development-build tests and UX
validation; never select it as a repository's normal Sprintctl authority. Do not obtain,
export, or reuse `SPRINTCTL_URL` / a PostgreSQL URI for workstation or
devbox-vm normal operation. The only approved client selection is a validated
non-secret Vuoro profile plus its local credential-file reference; direct
database commands remain deployment or explicitly marked recovery work.

Before changing a repository profile, follow
`/projects/dev/agentops/docs/runbooks/vuoro-workstation-cutover.md`. Workstation
and devbox-vm have independent checkouts, profile state, credential files, and
tool installations, so a cutover must pass separately on each host. The final
eight-repository scanner and the profile validator in that runbook are required
before database bootstrap access can be revoked.
