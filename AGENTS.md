# Agentops Agent Guidance

Shared environment guidance: `/projects/dev/AGENTS.md`. agentops is a **public** repo.

## Ownership

Canonical source for dispatch skills, manifest/verification schemas, sync utilities,
cross-repo guidance (`docs/`) and the cockpit app (`apps/web/`). It does not own sprint,
queue, knowledge, audit or Kubernetes state; `appservice` deploys the cockpit.
`actionq-dispatcher` is only a tombstone.

## Commands

```bash
python templates/dispatch/scripts/sync_skills.py check --repo <repo> [--apply]    # --apply refuses dirty skill paths
python /projects/dev/agentops/templates/dispatch/scripts/validate_verification_artifacts.py --root .
python templates/dispatch/scripts/render_project.py check --project <home-repo>/project.toml [--apply]
python templates/dispatch/scripts/materialize_project.py setup|sync --project <home-repo>/project.toml --folder <dir>  # dir outside every member repo
cd apps/web && npm test && npm run build
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

- The saved `.claude/workflows/vuoro-dispatch-*.js` still assume ActionQ transport: do not
  use them for new work until migrated
  (`docs/plans/agentops/native-runtime-federation-realignment-2026-08-20.md`).
- Hybrid mode (cheap worker, coordinator keeps decisions): `docs/runbooks/hybrid-dispatch.md`
  and `templates/dispatch/hybrid/hybrid-dispatch.v1.json`. Only for decided, oracle-gated,
  mechanical work; never for tests-as-deliverable, architecture, security, credentials,
  migrations or cross-repo sequencing. The dispatch policy files are protected paths
  (enforced by `.github/workflows/protected-paths.yml`).
- Model IDs and qualification are data in `templates/dispatch/model-routing.json`.

## Documentation

Keep policy, current implementation, history and plans distinct; mark superseded decisions
rather than editing history into guidance.

<!-- agentops-environment-pointer:start -->
See `.agents/environment.generated.md` for the active Vuoro environment's constraints and runbooks (agentops-managed; do not hand-edit).
<!-- agentops-environment-pointer:end -->
