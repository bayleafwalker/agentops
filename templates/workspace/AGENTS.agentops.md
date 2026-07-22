## Agentops repository contracts

## Workstation workspace storage

On the workstation, `/projects/dev` is local Btrfs storage. TrueNAS NFS is
only a migration and emergency-recovery source, never a writable live Git
workspace. The initial local recovery policy retains seven daily and four
weekly read-only Btrfs snapshots. devbox-vm and the legacy pod have independent
workspace trees; do not assume ignored state, tool installations, cost logs, or
Git worktrees propagate between environments.

`/projects/dev/agentops` is the canonical source for shared dispatch skills,
manifest schemas, state-protocol context/result schemas, and the dependency-free
repository gate.

- Repositories opt in with one root `*.dispatch.json` and repository-specific overlays under `.agents/overlays/`.
- Reusable verification intent belongs in data-only `verification/contexts/*.json`; executable tests and production logic remain in the owning repository.
- Inspect declared `risk_surfaces` before changing queue, claim, lease, retry, recovery, projection, publication, reconciliation, or backend-parity paths.
- Run `python /projects/dev/agentops/templates/dispatch/scripts/validate_verification_artifacts.py --root .` from an opted-in repository.
- `full` is a sequence, not blanket repair authority. Repair and production mutation remain separately authorized.
