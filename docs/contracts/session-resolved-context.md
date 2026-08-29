# Contract: the four objects and the resolved-context invariant

**Status:** v0, file-backed. Nothing here is promoted into a served schema.
**Date:** 2026-08-29

## What this fixes

Today, `auditctl` resolved the two halves of a write independently:
`resolve_paths` derives the index and `repo_id` by walking up from the CWD, while
`require_artifacts_root` reads only `AUDITCTL_ARTIFACTS_ROOT`, and `shard_path`
joins them. A shared hook supplied a root naming one repository, so every session
in every repo indexed at its own root and appended under `agentops`. Thirteen events
were misrouted — 11 recovered in agentops `5757779`, 2 more in `a44f01d`, none lost.

The containment fix made the hook mirror auditctl's resolution order. That is not
durable, and the reason is the point of this document: **two independent
resolutions that happen to agree are not one resolution.** Agreement by imitation
breaks whenever either side changes, and it already broke once during the repair —
the first fix stopped at the nearest `.git` and re-created the same defect one
directory higher, in `appservice`.

The general form of the defect is that every tool rediscovers *where am I* on its
own. `auditctl`, `sprintctl`, the hooks and the render scripts each walk the tree
with slightly different rules. The fix is not better rules. It is one resolution,
performed once, consumed by all of them.

## The four objects

These are **not new**. Three are already implemented, partially and implicitly,
which is why the vocabulary is worth fixing before more is built on it.

| Object | Meaning | What implements it today |
|---|---|---|
| **Project** | Durable logical work scope, may span repositories | `agentops/project.toml` — immutable `project_id`, `role_presets`, `[[members]]` |
| **Workspace** | One materialized project instance on a host | `/projects/dev/_projects/<name>/`, described by `project.context.json` |
| **Environment** | Host identity, capabilities, executor baseline | `templates/dispatch/environment-record/*.json` |
| **Session** | An agent/harness/role binding within a workspace | **nothing** |

`project.context.json` already does more than it is credited for: it pins
`canonical_project`, and each `context_sources[]` entry carries `kind`, `scope`
(`environment` or `project`), `sha256`, `source_commit` and `applies_to`, under an
aggregate `context_bundle_sha256`. Scoped, digested context already exists. A new
contract must extend it, not duplicate it.

`environment-record.schema.json` likewise already carries `environment_class`,
`capabilities`, `constraints`, `roles` and `identity_bindings`.

**Session is the object that is never *produced*.** Fragments of it already exist —
`materialize_project.py:_lease_identity` records host, pid and `runtime_session_id`;
every audit event already carries `runtime_session_id`; and
`templates/dispatch/session-mechanization/session-capsule.schema.json` already binds
repo, harness, model, actor and target. That schema has never emitted an instance.

So the gap is production and consumption, not conception. Nothing binds
`role_presets` (Project) and `identity_bindings` (Environment) to a concrete
workspace path on a concrete host at a concrete revision, and so each tool
re-derives its own answer.

### Why one object cannot serve for another

A single "workspace root descriptor" collapses immediately under conditions that
already exist here:

- **Concurrent sessions** in one workspace need distinct identities but share a path.
- **Git worktrees** are one repo, many paths, one project — and they do not all follow
  the `*.worktrees/` convention. Live agentops worktrees sit under
  `_projects/<name>/members/` and under `$HOME`, which is finding 2 below.
- **Two harness identities on one executor** — devbox runs both `agent` and `dev`
  with deliberately different settings; converging them is forbidden by the
  `$comment` in their own config.
- **A project spanning repos with differing access** — `project.toml` records
  per-member `access`, so authority is not a workspace-level property.
- **Remote pickup**, where a session resumes against a different materialization.

## The resolved-context invariant

An earlier draft of this section said *session creation resolves paths and
identities once and emits an immutable context*. **That is wrong for path
attribution, and an independent review caught it before it was built.** A session
here routinely crosses repositories — this one worked in `agentops`, `auditctl` and
`/projects/dev` — and per-write CWD attribution is what routes each event to the
right repo. A path context frozen at session creation would attribute every event
to the starting repository: the defect this document exists to end, re-created by
its own remedy.

So the invariant splits by lifetime:

> **Session-scoped** — identity, role, harness, environment, and the pinned
> revisions and digests they resolve against — is resolved **once** at session
> creation and is immutable.
>
> **Write-scoped** — path attribution — is resolved **per write**, but always
> *whole*: never in independently-derived halves, and never silently reconciled.

Both scopes share three obligations:

1. **Atomic.** Resolution yields a whole record or fails. It never yields a
   partially-resolved result that a caller completes by guessing.
2. **Fail closed on contradiction.** When explicit inputs describe incompatible
   roots, resolution errors. It does not silently prefer one — that preference is
   exactly what wrote correct indexes and misplaced shards.
3. **Attributed.** The record names *why* it resolved as it did
   (`resolution_source`), so a wrong answer is diagnosable without re-deriving it,
   which is the thing that produced the wrong answer.

### First instance: `AuditContext` — and what it does not instantiate

Be precise about which half this is. `AuditContext` is **write-scoped**: it is
resolved per invocation from the CWD, not frozen at session start. It instantiates
*atomicity*, *fail-closed* and *attribution*. It does **not** instantiate
session-immutability, and it is not evidence that the session-scoped half works.

Audit attribution is per-workspace-member, not per-session. A future `SessionBinding`
therefore carries identity, role and environment — not a single audit path.

```
AuditContext {
  repo_id           # identity the events are attributed to
  index_path        # sqlite index
  artifacts_root    # root under which shards live
  shard_path        # derived, never independently recomputed
  resolution_source # explicit-db | explicit-root | index-marker | git-marker
}
```

`resolution_source` is one of `explicit-db`, `index-marker`, `git-marker`,
optionally suffixed `+explicit-root` when an explicit root confirmed the resolution.

**The rule is ancestor-or-equal, not equality.** Two conventions are in deliberate
use and both are coherent:

| Convention | Root | Repos |
|---|---|---|
| co-rooted | `root == repo_root` | agentops, vuoro, scribectl |
| pooled | `root` is an **ancestor** of `repo_root` | sprintctl, kctl, cred-broker, bindery-core, auditctl |

Pooling is safe because `repo_id` namespaces the shard directory beneath the shared
root. What is never safe is a root *below* the resolved repository or off its line
entirely — that writes the shard inside another repository's tree while the index
stays put, which is exactly the 2026-08-29 geometry (`repo_id` `dev`, indexed at
`/projects/dev`, root `/projects/dev/agentops`, a descendant).

The first draft of this contract specified equality, which would have failed the
first `add` in five repositories whose `.envrc` is committed and in use — firing
falsifier 4 below on day one. The review that caught it is the reason the rule is
stated as geometry rather than as an instance.

`auditctl` is chosen as first instance because the failure is real and measured,
not because it is easy. It is nonetheless a **partial** test of the invariant: it
exercises path resolution but not identity, role, or harness binding. It must not
be treated as validating the general case.

## Ownership boundary

| Concern | Owner | Not |
|---|---|---|
| Project / EnvironmentClass / SessionBinding definitions | vuoro (coordination contract) | not the config bytes |
| Instruction templates, managed settings fragments | agentops or the producing repo | not vuoro |
| Transport of pinned bundles | git / content-addressed source | not a served endpoint |
| Machine-local effects | one local `bootstrap/apply/check/rollback` | not per-host bespoke scripts |
| Triggers (nix activation, systemd units) | generated from the same definitions | not hand-written per host |
| Conformance observations | auditctl | **not** desired-state authority |

Two boundaries carry most of the weight. **Vuoro defines and resolves; it does not
distribute bytes** — writing into `$HOME` is the machine-local effect its own first
principle forswears, and config that gates bootstrap cannot depend on a served
endpoint being reachable. **auditctl records what was observed; it never states
what should be** — a ledger that also holds desired state can never disagree with
reality, which is the only useful thing a ledger does.

## v0 is file-backed, deliberately

The choice is not "served schema now" or "machine-by-machine reinvention forever".
A portable file-backed contract with one implementation stops reinvention without
committing unstable concepts to a served schema.

Promote a projection into vuoro's served schema only when it has survived contact:
exercised on the workstation, on devbox, and on one clean disposable executor, with
at least one case where the contract *rejected* something it should have.

## Non-goals

- Not a config-distribution transport. Git already reaches every agent host.
- Not host homogenization. Triggers differ per host; that is cheap and fine.
- Not a replacement for `project.context.json`. This names what that machinery
  already does and adds the object it lacks.

## Open, from the pre-build review

An independent review ran against this contract before it was built. Two findings
changed it (the invariant's lifetime split, and ancestor-or-equal). These remain
open and are **not** addressed by `AuditContext`:

1. **`repo_id` is a directory basename, so identity is an accident of geography.**
   Verified live: a session in the agentops worktree at
   `_projects/vuoro-dispatch-ready/members/agentops` resolves to `repo_id="dev"`,
   because worktrees have no `.auditctl` and the walk exits at the workspace. A
   second agentops worktree under `$HOME` resolves to its own basename, and its
   evidence dies with the checkout. This has already happened —
   `_artifacts/wt-counter/` and `wt-review/` hold orphaned shards named after
   transient worktrees. Identity must come from the repository (`project.toml`
   member `repo_id`, or a declared id), not from the path. `AuditContext` freezes
   this answer earlier rather than fixing it.

2. **A wrong-but-coherent pair still passes.** `AUDITCTL_DB` alone pointing at
   another repo routes both halves there and is internally consistent. The true
   class is config *scoping* — a value correct for one context, installed in a
   shared one — and the contract has no answer yet for how a consumer receives its
   context without walking the tree. Env vars remain writable by shared-scope code,
   and a Stop/SubagentStop hook shell inherits neither direnv nor a login PATH.

3. **Three resolvers is worse than two.** After a44f01d there is a bash mirror of
   the walk in `auditctl-resolve.sh`. Once the root defaults to the resolved repo,
   that export can no longer change an outcome — it can only fail closed when the
   two walks drift. It should be retired for auditctl consumers rather than
   maintained, but only after 0.1.4 is deployed everywhere, since 0.1.3 still
   *requires* the root. The `artifacts-root.default` floor becomes dead in the same
   step.

4. **An applier already exists, twice.** `materialize_project.py` implements
   staging, `_atomic_write`, validation, receipt, lease and drift for the workspace
   case; on NixOS, activation *is* render/validate/atomic-switch/rollback. A third
   applier must absorb or reference these, or it reproduces the duplication this
   contract exists to end. The boundary against gitops-nixos as desired-state owner
   is currently undefined in the ownership table.

5. **Cross-host identity collides silently.** devbox-agent has its own clone at the
   identical path, so the same `repo_id`s address two disjoint indexes and shard
   trees with no host field in the shard path. Events carry `runtime_session_id`,
   but the merge story is unstated. This is the next index-only incident if left.

## Falsifiers

This contract is wrong if:

- A tool can consume the resolved context and still need to walk the tree itself.
- Two concurrent sessions in one workspace cannot be told apart by their contexts.
- An immutable context makes a legitimate mid-session change (a `git pull`, a
  worktree switch) unrepresentable rather than merely explicit.
- Resolution fails closed so often that callers grow a bypass — a fail-closed rule
  people route around is worse than the silent preference it replaced.
- `AuditContext` passes every test while the general case remains unconstrained.

## Sequencing

1. `AuditContext` in auditctl: atomic, fail-closed, attributed. ✅ this change
2. Contradictory-override tests, unrepresentable in the current shape.
3. File-backed `SessionBinding` v0 + transactional applier.
4. NixOS and Arch/systemd triggers generated from one definition.
5. Test on workstation, devbox, one clean disposable executor.
6. Promote only proven projections.
