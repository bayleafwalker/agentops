# Vuoro first project-scoped work window

Date: 2026-07-19

This note records the first migration window for the canonical `vuoro`
binding. It is implementation and acceptance evidence, not a new project
contract; the governing policy remains `project-binding-spec.md`.

## Instantiated state

- Project UUID: `981b2073-d7af-4c28-bff3-3cf807495fba`, matching the existing
  append-only `agentops.toml` registry entry.
- Canonical binding and sources: agentops commit `7b19b8d`.
- Render fan-out: sprintctl `8c970b3`, kctl `3e75084`, actionq `b9a443a`.
- Derived folder: `/projects/dev/vuoro`, containing clean linked worktrees at
  those four pushed revisions. The folder is rebuildable and is not committed
  project truth.

The first render check reported `generated=missing; pointer=missing` for all
three `render = "full"` members. Applying before project truth was committed
was refused by the dirty-input guard. After the home sources were committed,
apply produced in-sync output and a second check was clean. This is the pilot's
drift-check-fire evidence.

## Representative session

The session ran from `members/agentops` in the derived folder with path-free
`--project` resolution:

```bash
sprintctl usage --context --project --json
sprintctl next-work --project --json --explain
sprintctl item list --project --status active --json
```

Observed union:

| Origin repo | Selected backlog | Ready at observation |
|---|---:|---:|
| agentops | 380 | 2 |
| sprintctl | 407 | 2 |
| kctl | 381 | 1 |
| actionq | 383 | 6 |

The context view returned 64 items across four repositories. The active-item
view attributed the pilot itself to agentops and the other active work to
actionq. This exercised the home-repo convention: the cross-cutting migration
remained item `#1181` in the agentops backlog while commits landed in each
owning repository.

During this representative window, three union reads replaced twelve
equivalent per-repository invocations; no per-repository status call was needed
to decide or attribute the work.

## Synchronization and standalone checks

Two consecutive `sync` runs reported every member `current` and every render
`in-sync`. Their derived `AGENTS.md` and `project.context.json` hashes were
stable on the second run (`094d1d...` and `43f970...`, respectively).

Standalone reads were spot-checked in two non-members:

- auditctl: 9 items, no `origin_repo` fields without `--project`;
- aligned-equity: 42 items, no `origin_repo` fields without `--project`.

Neither repository had a `project.toml`, and neither worktree changed. This
confirms that the vuoro binding did not activate outside its explicit scope.

## Guidance observation

The rendered member guidance covered the project-as-projection rule, home-repo
convention, origin attribution, ownership boundaries, drift workflow, and the
ban on implicit deployment authority. No missing domain constraint was needed
during the work window.

One navigation gap did surface: the materialized folder root is deliberately
not a Git repository, while remote sprintctl startup still requires a concrete
repository identity. Project reads therefore begin in a member worktree. The
folder generator and `project-folder.md` now state that explicitly and provide
the home-member command. This is operator guidance, not a project database or
new runtime authority.
