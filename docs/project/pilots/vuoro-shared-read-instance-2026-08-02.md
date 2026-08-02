# Vuoro enforced shared-read instance pilot — 2026-08-02

## Scope

This pilot exercised the v2 project materializer on devbox-vm using its local
ZFS-backed repository clones. It created the derived instance at:

```text
/projects/dev/_projects/vuoro-read-pilot
```

The instance identity is `read-pilot-20260802`, mode `shared-read`, with
filesystem enforcement enabled. It carries no sprint, queue, deployment, or
Git authority.

## Initial safe failure

The first setup attempt stopped before context completion. The clean devbox
anchor binding at `cfaddb5e25fc17635ac4e7a224efb24582b94a4d` declared five
members, while the fetched `origin/main` home worktree contained a newer
binding that added `auditctl`. Loading that newer binding failed because no
matching member worktree had been created.

The partial instance passed `destroy --check` and was removed through the
materializer's Git-native destroy path. No uncommitted member state existed and
no raw recursive deletion was used.

The resulting invariant is now executable and regression-tested: setup seeds
the home member from the exact selected canonical binding commit, validates its
logical binding shape, and never advances the home binding implicitly during
legacy `sync`. A newer remote home revision is reported as `behind`.

## Successful rerun

The corrected setup completed with these recorded revisions:

| Member | Revision | State |
| --- | --- | --- |
| `agentops` | `cfaddb5e25fc17635ac4e7a224efb24582b94a4d` | pinned; behind `origin/main` |
| `vuoro` | `08f83013b1b9f9042598b5468e8655aa7ba72d09` | current |
| `sprintctl` | `80379b394e9be7e5e1d1e3d6ebe268f439a1f964` | current |
| `kctl` | `3b355de41358da74542170a80b8b5fa15d692ff1` | current |
| `actionq` | `1b92f7ce5f8be3050cd8c5725d53e015dae4302f` | current |

The persisted context bundle digest was:

```text
d7da020804d438a673ddaac59c5d92a0a8e663b925ad241fed15891d85c1336d
```

`validate_project_workspace.py` passed canonical cleanliness, marker/context
identity, every source digest, the recomputed bundle digest, all worktree
registrations/common Git directories, member effective modes, and root direnv
absence. Member directory/file modes demonstrated enforcement (`dr-xr-sr-x`
and `-r--r--r--` for the sampled Actionq paths).

The local lease acquire → heartbeat → release cycle also completed with exact
holder identity, leaving no active lease.

## Harness evidence

An ephemeral Codex v0.145.0 session ran from the project root with a read-only
sandbox and no Git-root assumption. It correctly reported:

- logical project `vuoro`;
- instance `read-pilot-20260802`, enforced `shared-read` mode;
- the five pinned members above;
- sprint/cross-project planning owned through Agentops/Sprintctl, queue
  execution owned by Actionq, and deployment overlays owned by Appservice;
- prohibitions on raw cross-tool database transactions, project-scope
  deployment/reconciliation, and hand-editing generated guidance.

This proves Codex instruction discovery for this instance. It does not prove
Claude Code or OpenCode discovery; those remain separate harness checks.

## Storage-policy evidence and limitation

`/projects/dev/_projects` now exists on the workstation and devbox. The legacy
workspace Restic exclusion policy in Appservice names `_projects`, and its
targeted Kustomize build passes. Parent Btrfs snapshots and block-level devbox
zvol snapshots cannot honor a path exclusion; excluding derived instances from
those layers requires separate backing storage or snapshot topology.

The successful devbox instance remains available for read-oriented sessions
and is deliberately unleased.
