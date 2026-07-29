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
- Materialize or synchronize a derived multi-repository project folder:
  ```bash
  python templates/dispatch/scripts/materialize_project.py setup --project /projects/dev/<home-repo>/project.toml --folder <derived-folder>
  python templates/dispatch/scripts/materialize_project.py sync --project /projects/dev/<home-repo>/project.toml --folder <derived-folder>
  ```
  The folder must be outside every member repository and is never a Git or
  dispatch authority. Sync fast-forwards only clean project worktrees; it
  reports dirty, ahead, diverged, detached, or unexpected branches without
  resolving them.
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

## Saved Dispatch Workflows

- `.claude/workflows/vuoro-dispatch-build.js` — claim → build → independent verify → optional
  publish → close pipeline for sprintctl items. Callers may group related items with `unit`;
  same-repo units use separate accountable build contexts but stay sequential, while independent
  repos dispatch in parallel. Routes by boundedness/uncertainty (`bounded` / `standard` / `hard`,
  with legacy `mechanical` accepted as `bounded`) instead of diff size. Verification runs once per
  reasoning unit in fresh context, with foreground timeouts and explicit command evidence. A shared
  constraint trips a same-repo circuit breaker. The build agent never closes or pushes; `push=true`
  publishes only after the entire built repo batch clears independent verification.
- `.claude/workflows/vuoro-dispatch-verify.js` — independent verification pass, usable as
  the pre-close gate above (`mode: "gate"`) or as a standalone retroactive audit of work
  already merged (`mode: "audit"`, files a triage note instead of closing anything). Gate mode
  takes claim IDs and reads proof from mode-0600 workflow records (or sprintctl's local-backend
  recovery record as fallback); claim tokens must not be passed through workflow args or results.
- Both invoke via `Workflow({scriptPath: "/projects/dev/agentops/.claude/workflows/<name>.js"}, {args: {...}})`
  — see each file's `meta.whenToUse` for the exact args shape. Their provider-specific tiers mirror
  the `clerical` / `fast-build` / `standard-build` / `hard-build` aliases in
  `templates/dispatch/model-routing.json`; keep them in sync by hand (workflow scripts have no
  filesystem access to read the routing file at run time). See
  `docs/dispatch/workflow-topology.md` for the reasoning-unit and escalation policy.

## Choosing Hybrid Mode

Hybrid mode delegates one mechanically specified implementation loop to a cheap OpenCode Go
worker while a Claude or Codex coordinator keeps every decision. The operator
chooses it per task, before any work starts. Contract:
`templates/dispatch/hybrid/hybrid-dispatch.v1.json`; runbook:
`docs/runbooks/hybrid-dispatch.md`.

**Choose hybrid when all of these hold.** Any "no" means coordinator-only:

1. The repository's `*.dispatch.json` has `hybrid.enabled: true` and a
   `worker_routes` entry for the route you want.
2. Architecture, interface, acceptance semantics, and the test oracle are
   already decided — the task is "implement this", not "work out what correct
   means".
3. The writable paths are inside `scope.allowed_path_roots` and touch no
   `hybrid.protected_paths`.
4. A registered command in `hybrid.commands` can actually falsify every
   relevant requirement, and the packet states which incorrect behaviour each
   acceptance property detects.
   Without a gate that fails on a wrong answer, a cheap worker's output is
   unreviewable at a glance and costs more to check than to write.
5. The change is big enough that freezing a packet is cheaper than typing it.

**Never hybrid**, regardless of the above: test-oracle or parity-fixture
construction, tests as the primary deliverable, cross-layer behavioural proof,
unresolved architecture or
ownership, cross-repository sequencing, security, credential, authority,
compatibility, or migration semantics, sprint or release decisions, and
anything rejected once unless a coordinator supplies a materially revised
packet. Packet contradiction or a missing oracle is a task defect, not an
escalation trigger.

**What the operator does, and what stays theirs.** Claim the sprintctl item as
the coordinator, freeze the packet at an exact commit, then run the driver
stages. The worker never holds Git, sprintctl, deployment, or acceptance
authority; sprint state is coordinator-only and acceptance is human. A
`gate` result is a *candidate*, never a merge.

```bash
D=/projects/dev/agentops/templates/dispatch/scripts/hybrid_dispatch.py
python "$D" --repo-root . --packet packets/<TASK>.json validate
python "$D" --repo-root . --packet packets/<TASK>.json overlay   # inspect before dispatch
python "$D" --repo-root . --packet packets/<TASK>.json prepare   # worktree + cold gates
python "$D" --repo-root . --packet packets/<TASK>.json run       # one bounded worker loop
python "$D" --repo-root . --packet packets/<TASK>.json gate      # cold post-gates
```

On devbox-agent the deployed `hybrid-dispatch` wrapper does the same against
pinned `/etc/agentops` policy. Queue-driven work uses the actionq
`hybrid-bulk-*` actions instead; there the dispatcher owns the worktree, the
claim, and the gate command.

**This repository's own scope.** `agentops` enables the `mechanical_bulk` route only, and
the dispatch contract itself — `templates/dispatch/hybrid/**`,
`model-routing.json`, `manifest.schema.json`, `hybrid_dispatch.py`,
`agentops.dispatch.json` — is protected. A worker must never edit the policy
that bounds it.

**Qualification is narrow.** Only the named Vuoro `mechanical_bulk` pilot is
admitted, and only where the coordinator supplies the semantic oracle and
discriminating executable gates. Kimi K2.7 is experimental, GLM 5.2 is
available-unqualified with no escalation role, and Kimi K3 is benchmark-only.
Availability is not qualification and a passing smoke run promotes nothing.

## Documentation Quality

- Keep policy, current implementation, shipped history, and future plans
  distinct. Mark superseded decisions instead of silently editing history into
  current guidance.
- Treat model IDs and provider capabilities as data in
  `templates/dispatch/model-routing.json`; do not make unverified provider
  syntax executable policy.

<!-- agentops-environment-pointer:start -->
See `.agents/environment.generated.md` for the active Vuoro environment's constraints and runbooks (agentops-managed; do not hand-edit).
<!-- agentops-environment-pointer:end -->
