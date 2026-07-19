# Agentops Agent Guidance

> Shared environment guidance lives in `/projects/dev/AGENTS.md`.

## Ownership

`agentops` is the canonical source for reusable dispatch skills, manifest and
verification schemas, synchronization utilities, cross-repo guidance, and the
agent-cockpit application. It does not own sprint state, queue state, knowledge
state, audit state, or Kubernetes desired state.

- `templates/dispatch/` owns shared skills, schemas, examples, model-routing
  data, and repository-safe validation scripts.
- `docs/` owns cross-repo decisions and ecosystem guidance.
- `apps/web/` owns cockpit application code; `appservice` owns its deployment.
- `../sprintctl`, `../kctl`, `../auditctl`, `../actionq`, and
  `../actionq-dispatcher` own their respective runtime behavior.

## Dispatch Template Rules

- Repositories select shared skills through one root `*.dispatch.json` and put
  domain-specific constraints in `.agents/overlays/`.
- Keep reusable behavior canonical. Do not hand-copy full skill bodies into
  consumers when an overlay can express the actual difference.
- Use the synchronization tool conservatively:
  ```bash
  python templates/dispatch/scripts/sync_skills.py check --repo <repo>
  python templates/dispatch/scripts/sync_skills.py check --repo <repo> --apply
  ```
  `--apply` intentionally refuses dirty selected skill paths. Preserve
  repository-local documentation and overlays rather than treating them as
  template drift.
- Run the dependency-free gate from an opted-in consumer root:
  ```bash
  python /projects/dev/agentops/templates/dispatch/scripts/validate_verification_artifacts.py --root .
  ```
- Check or render a canonical project binding from its home repository:
  ```bash
  python templates/dispatch/scripts/render_project.py check --project /projects/dev/<home-repo>/project.toml
  python templates/dispatch/scripts/render_project.py check --project /projects/dev/<home-repo>/project.toml --apply
  ```
  `--apply` refuses dirty project inputs, member overrides, `AGENTS.md`, and
  generated outputs. Commit authored source changes before rendering and keep
  each member repository's generated output in a separate `chore(render)`
  commit.
- Inspect declared `risk_surfaces` before changing queue, claim, lease, retry,
  recovery, projection, publication, reconciliation, or backend-parity paths.
  `full` is a sequence, not blanket authority to repair or mutate production.

## Cockpit And Deployment

- Validate web changes from `apps/web/` with `npm test` and `npm run build` as
  appropriate.
- Keep browser-facing cockpit writes mediated through the documented API and
  owning domain contracts. Do not add raw database write paths or mutate the
  read-only workspace mount.
- Do not run Flux, kubectl, image pushes, deployment changes, or cluster
  reconciliation from this repository unless that operational work is separately
  authorized in `appservice`.

## Documentation Quality

- Keep policy, current implementation, shipped history, and future plans
  distinct. Mark superseded decisions instead of silently editing history into
  current guidance.
- Treat model IDs and provider capabilities as data in
  `templates/dispatch/model-routing.json`; do not make unverified provider
  syntax executable policy.
