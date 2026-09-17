# Agentops Agent Guidance

Shared environment guidance: `/projects/dev/AGENTS.md`. agentops is a **public** repo.

## Ownership

Canonical source for dispatch skills, manifest/verification schemas, sync utilities,
and cross-repo guidance (`docs/`). It does not own sprint, queue, knowledge, audit or
Kubernetes state. The agent-cockpit app (`apps/web/`) was retired and deleted in 2026-09.
`actionq-dispatcher` is only a tombstone.

## Commands

```bash
python scripts/sync_skills.py check --repo <repo> [--apply]    # --apply refuses dirty skill paths
python /projects/dev/agentops/scripts/validate_verification_artifacts.py --root .
python scripts/render_project.py check --project <home-repo>/project.toml [--apply]
python scripts/materialize_project.py setup|sync --project <home-repo>/project.toml --folder <dir>  # dir outside every member repo
```

- Consumers opt in with one root `*.dispatch.json` plus `.agents/overlays/`; express
  differences as overlays, never copied skill bodies.
- Commit authored changes before `render_project --apply`; generated output goes in a
  separate `chore(render)` commit per member repo.
- Inspect declared `risk_surfaces` before touching queue, claim, lease, retry, recovery,
  projection, publication, reconciliation or backend-parity paths. `full` is a sequence,
  not repair authority.
- Cockpit writes go through the documented API; no raw database writes.

## Dispatch

- `docs/plans/2026-09-17-target-state.md` is the current agent-tooling and
  Vuoro direction: the target claims (TS-1..TS-15) that decide deployment,
  deprecation and retirement for this repo and its dispatch tooling. Read it
  before changing dispatch, model-routing, or project-workspace behaviour.
- The saved `.claude/workflows/vuoro-dispatch-*.js` still assume ActionQ transport: do not
  use them for new work until migrated
  (`docs/plans/agentops/native-runtime-federation-realignment-2026-08-20.md`).
- Hybrid mode (cheap worker, coordinator keeps decisions) is retired as of S2 item 6
  (2026-09-17); its policy and driver were deleted with `templates/dispatch`. See
  `docs/runbooks/hybrid-dispatch.md` for the historical record.
- Model IDs and qualification are data in `model-routing.json`.

## Documentation

Keep policy, current implementation, history and plans distinct; mark superseded decisions
rather than editing history into guidance.

<!-- agentops-environment-pointer:start -->
See `.agents/environment.generated.md` for the active Vuoro environment's constraints and runbooks (agentops-managed; do not hand-edit).
<!-- agentops-environment-pointer:end -->
