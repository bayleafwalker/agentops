## Recommendation

Use a **hybrid split**:

1. **Keep `sprintctl` as its own repo**
2. **Keep `kctl` as its own repo**
3. **Create `auditctl` as its own repo**
4. **Create/keep `actionq` as its own repo**
5. **Create `agentops` as the cross-repo planning and cockpit repo**
6. **Deploy everything through `appservice`**
7. **Do not create a shared library repo yet**

That gives you clean operational seams without turning this into Enterprise Java: The Homelab Edition.

Your plan already has the right architectural split: sprint state in `sprintctl`, audit as repo-local NDJSON/sqlite, session lifecycle in `actionq`, and cockpit as an operator surface reading from pg + /projects/dev/_artifacts artifacts .

---

# Naming

## Repositories

| Repo                         |                             Purpose | Keep separate? | Why                                                            |
| ---------------------------- | ----------------------------------: | -------------: | -------------------------------------------------------------- |
| `sprintctl`                  | Sprint/work-item/state coordination |            Yes | Core tool, now has local/remote modes and migration logic      |
| `kctl`                       |      Knowledge extraction/rendering |            Yes | Existing companion tool, same family but different domain      |
| `auditctl`                   |       Repo-local audit/event ledger |            Yes | New but conceptually stable; should remain boring and portable |
| `actionq`                    | Queue + daemon + dispatch lifecycle |            Yes | Service/daemon boundary, not just a CLI                        |
| `agentops`                   |      Cross-repo plans + operator UI |            Yes | Product surface and coordination docs, without owning substrate state |
| `appservice`                 |        Kubernetes deployment/GitOps |    Already yes | CNPG, actionq, cockpit manifests belong here                   |
| `homelab-analytics`          |                      Pilot consumer |    Already yes | Should consume tools, not contain them                         |

My preferred names:

```text
sprintctl
kctl
auditctl
actionq
agentops
appservice
```

Use **`agentops`** for the repo and **`agent-cockpit`** for the app/service surface inside it. That keeps the repo broad enough to own cross-repo plans and runbooks while keeping the UI name descriptive.

For the whole family, use an informal umbrella name in docs:

```text
agent-ops substrate
```

or, slightly more yours:

```text
workbench substrate
```

But do **not** turn `agentops` into a mega-repo. The substrate implementations stay in their state-owning repos.

---

# Package / command naming

Keep the command names short and Unix-y:

```text
sprintctl
kctl
auditctl
actionq
actionq-daemon
agent-cockpit
```

Inside `actionq`, split binaries like this:

```text
actionq          # CLI: enqueue, inspect, cancel, resume
actionq-server   # cluster service/API
actionq-daemon   # devbox runner
```

Do not call the cluster component `actionq-cluster` as the binary. That is a deployment role, not a command. In code/docs it can be the “cluster service”; on disk it should be `actionq-server`.

Recommended service names:

```text
actionq-server
actionq-daemon
agent-cockpit-web
sprintctl-pg
```

For Kubernetes objects:

```text
sprintctl-postgres
actionq-server
agent-cockpit
```

Avoid `sprintctld-pg` unless you actually build a daemon. Your plan leans toward direct pg access, which I agree with; naming a non-daemon `sprintctld` will lie to future-you, and future-you has logs.

---

# What belongs together

## 1. `sprintctl`

Contains:

```text
sprintctl/
  src/sprintctl/
    cli/
    local_store/       # sqlite implementation
    remote_store/      # postgres implementation
    events/
    migrate/
  migrations/
    sqlite/
    postgres/
  docs/
    decisions/
    runbooks/
  tests/
```

Responsibilities:

* local sqlite mode
* remote pg mode
* `migrate-to-remote`
* sprint/work item/event model
* takeup/release event model
* pg schema migrations
* NDJSON export/import for migration

Do **not** put cockpit queries here except maybe as tested SQL fixtures. `sprintctl` should expose enough state that cockpit can read; it should not become “the backend for the UI.”

## 2. `auditctl`

Contains:

```text
auditctl/
  src/auditctl/
    cli.py
    store.py
    ndjson.py
    lock.py
    hooks/
  hook-templates/
    post-commit
    post-merge
  docs/
  tests/
```

Responsibilities:

* sqlite audit index
* NDJSON append/rebuild
* git hook templates
* manual audit events
* stable event schema

I would make this its own repo, not a package inside `kctl`. The plan explicitly says audit is not a sprint event store, not a knowledge graph, and not centralized . Separate repo reinforces that.

## 3. `kctl`

Keep as-is, but add a follow-up integration:

```text
kctl render --format ndjson
kctl publish-artifacts
```

Target path:

```text
<nfs-root>/_artifacts/<repo_id>/knowledge/
```

Do not merge `kctl` and `auditctl`. They are siblings. Same family, different blood pressure.

## 4. `actionq`

Contains both cluster service and daemon:

```text
actionq/
  src/actionq/
    cli/
    server/
    daemon/
    scheduler/
    harnesses/
      claude.py
      codex.py
      copilot_cli.py
      opencode.py
    protocol/
    audit/
    sprintctl/
  deploy/
    examples/
  docs/
  tests/
```

Responsibilities:

* queue state
* dispatch policy
* daemon/server protocol
* harness execution
* session lifecycle
* heartbeat/TTL semantics
* usage-limit pause/resume later
* emits audit events
* calls `sprintctl takeup/release`

The plan says heartbeats and TTL belong to `actionq`, not `sprintctl`, because `actionq` owns the actual session lifecycle . That should be reflected in repo ownership.

Implementation detail: start with `actionq-daemon` runnable without `actionq-server`, because your own plan calls out daemon-only as a shippable intermediate step .

## 5. `agentops`

Contains:

```text
agentops/
  docs/
    plans/
    runbooks/
  apps/
    web/              # agent-cockpit frontend
      src/
        data/
          sprintctl_pg/
          audit_ndjson/
          actionq_api/
        components/
        pages/
      tests/
```

Responsibilities:

* cross-repo substrate planning docs
* operator runbooks
* read-only operator UI
* reads sprint state from pg
* reads audit/knowledge artifacts from `/projects/dev/_artifacts`
* reads session state from `actionq`
* dispatch composer calls `actionq-server`

No direct writes to sprintctl pg. No direct writes to `/projects/dev/_artifacts`. No “just this once” shortcuts, because that is how frontend demos become cursed infrastructure.

---

# Deployment ownership

Use `appservice` for live manifests:

```text
appservice/
  clusters/
    main/
      kubernetes/
        apps/
          actionq-db/          # current CNPG actionq database
          sprintctl-postgres/  # target
          actionq-server/      # target, if/when service API exists
          agent-cockpit/       # target
  secrets/
    external-secrets-or-sops/
  docs/runbooks/
```

Tool repos may include example manifests, but the real deployment source of truth should remain `appservice`.

That matches your existing GitOps model and avoids each tool repo trying to become a tiny platform repo.

---

# Shared code: resist it for now

Do **not** create this yet:

```text
agentops-common
```

Tempting, but too early.

Instead, duplicate a little:

* marker-file traversal
* repo-id resolution
* timestamp helpers
* NDJSON writer
* ULID generation
* env var loading

Once the third tool repeats the same thing painfully, extract a package. Until then, shared libraries are where simple tools go to become committees with import paths.

A future shared package could be:

```text
repoctx
```

or:

```text
agentops-core
```

But I would only create it after `auditctl` and `sprintctl remote` are both working.

---

# Config conventions

Use consistent marker/config files:

```text
.sprintctl.toml
.kctl.toml
.auditctl.toml
.actionq.toml
```

Example:

```toml
# .auditctl.toml
repo_id = "homelab-analytics"
artifacts_root = "/projects/dev"  # writes under /projects/dev/_artifacts/<repo_id>/
db = ".auditctl/audit.db"
```

For sprintctl remote mode:

```toml
# .sprintctl.toml
backend = "remote"
repo_id_source = "directory-name"
```

Then allow env override:

```bash
SPRINTCTL_BACKEND=remote
SPRINTCTL_URL=postgresql://...
AUDITCTL_ARTIFACTS_ROOT=/projects/dev
```

I would prefer config file first, env override second. Direnv remains useful, but the repo should still declare its intended mode so old tools fail loudly instead of scribbling into the wrong sqlite file.

---

# Artifact layout

Use this exactly:

```text
/projects/dev/
  homelab-analytics/
  sprintctl/
  kctl/
  actionq/
  actionq-dispatcher/
  appservice/
  auditctl/          # target
  agentops/         # plans + future agent-cockpit surface
  _artifacts/
    homelab-analytics/
      audit/
        events-2026-04-26.ndjson
      knowledge/
        knowledge-2026-04-26.ndjson
    sprintctl/
      audit/
      knowledge/
```

This matches the actual flat `/projects/dev` workspace. The `_artifacts/` directory is a sibling of the repos, not committed inside any repo. In the current workspace it may be absent until auditctl or kctl artifact publishing creates it.

---

# Suggested first sprint names

Use boring semantic names for repos/tools, and three-word codenames for sprint slices.

I’d use:

```text
audit-ledger-foundation
pg-cutover-bridge
daemon-bridge-runner
cockpit-source-realign
```

Or if you want the slightly more whimsical sprintctl style:

```text
ledger-river-anchor      # auditctl minimum
postgres-bridge-lantern  # sprintctl remote
daemon-harness-gate      # actionq daemon
cockpit-pane-compass     # cockpit realignment
```

Recommendation: keep whimsy at the sprint level, not repo names. A repo named `ledger-river-anchor` will feel charming for 12 minutes and then become archaeology.

---

# Final repo boundary decision

Do this:

```text
sprintctl          # existing; add pg/remote/migration
kctl               # existing; later add artifact publishing symmetry
auditctl           # new repo-local audit CLI
actionq            # new/continued service + daemon + CLI
agentops           # cross-repo plans + operator UI
appservice         # deployment only
```

And this is the key rule:

> **State ownership decides repo ownership.**

* Sprint state → `sprintctl`
* Knowledge artifacts → `kctl`
* Audit/event ledger → `auditctl`
* Session lifecycle → `actionq`
* Operator view → `agentops` (`agent-cockpit` app)
* Runtime deployment → `appservice`

That split is boring in the best possible way.
