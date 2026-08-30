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
changed it (the invariant's lifetime split, and ancestor-or-equal); a third is now
closed. The rest remain open and are **not** addressed by `AuditContext`:

1. ~~**`repo_id` is a directory basename.**~~ **Closed** in auditctl `89abbf5`,
   before the applier, because the applier binds identity and would have propagated
   a basename-derived one into a new layer. Worktrees now resolve to their main
   repository (`worktree-main`), and a repository may declare a stable identity in a
   tracked `.auditctl-id` that travels with it — not in `.auditctl/`, which is
   gitignored, and not in an environment variable, which is the defect class itself.
   The dispatch manifests were rejected as the source: `repo_id` there is a slug for
   four repos and a **UUID** for sprintctl and vuoro, so adopting it would rename
   live shard directories.

   **Correction on the residue.** The review and an earlier revision of this section
   both described the 86 events under
   `_artifacts/{wt-counter,wt-review,wt-m10b,l2b,l2b-overlay,V6-K-human-turns,p3-driver}/`
   as orphaned worktree evidence needing an attribution decision. **That was wrong.**
   Their `metadata.session` values are `sess-a`, `sess-b`, `sess-poison`,
   `no-transcript` and `sess-t1` — fixture names from
   `hooks/tests/test-session-telemetry.sh` and the session reconciler tests. The
   directory names are test scenarios, not checkouts. They were test-suite output
   that landed in the live artifacts tree because the tests did not isolate
   `AUDITCTL_ARTIFACTS_ROOT`.

   So there was no decision to make: 84 `workflow.session` fixtures plus one
   escalation recorded twice, none claimed by any index (0 of 86), and keeping them
   was the only real hazard — a future reconcile would ingest 84 cumulative snapshots
   with fixture session keys and over-count exactly as the telemetry rule warns.
   Removed 2026-08-29 after archiving. The leak is not currently firing; the trees
   were last written 2026-08-23..26 and repeated full test runs since produced none.

   The lesson is the one this document already carries: *pair evidence with its own
   scope before believing what it says about the world.* Seven directories named
   after plausible-sounding worktrees were read as production residue by two
   independent passes, because nobody opened a row until the third.

2. **A wrong-but-coherent pair still passes — measured 2026-08-29, half answered.**
   The claim was reasoned; it is now measured, on a page that also carries a retracted
   finding that was reasoned and wrong. Six writes from one directory, varying only
   the environment (`docs/evidence/measurements/2026-08-29-coherent-context-redirect.md`):

   | `AUDITCTL_DB` | `AUDITCTL_ARTIFACTS_ROOT` | Outcome |
   |---|---|---|
   | unset | unset | correct |
   | **beta** | unset | **accepted, all under beta** |
   | beta | beta | accepted, same |
   | beta | alpha | refused |
   | unset | beta | refused |
   | unset | pooled ancestor | accepted; shard moves, `repo_id` does not |

   0.1.4 took the power to redirect away from `AUDITCTL_ARTIFACTS_ROOT`; rows 4 and 5
   are that fix working. `AUDITCTL_DB` keeps it in full, because it takes the index,
   derives the repo root from it, derives `repo_id` from that root, and defaults the
   artifacts root to the same place — four fields from one input, so all four agree
   and nothing fires. Confirmed in code at `auditctl/paths.py:126-138`.

   **What was missing from this finding:** a coherent redirect is worse than an
   undetected one. August's misrouting was repairable *because* it was incoherent —
   the mismatch between index and shard location was itself the evidence of where
   each event belonged. A coherent one leaves no trace at all: across 1593 events in
   11 stores, no record carried a working directory, a repository, a host, or a
   non-null `runtime_session_id`. A receipt written afterwards cannot reconstruct
   what the write never recorded, which is an ordering constraint on the applier.

   **Half answered.** auditctl now attaches `resolved_context` to every event it
   writes — `repo_id`, `repo_root`, `artifacts_root`, `published_from`,
   `resolution_source` — so a redirected write says so in its own record and the
   misfile is a query rather than an archaeology problem. It is a record and not a
   check, because writing into another store on purpose is legitimate, and it is the
   resolver's rather than the publisher's, because a publisher that could supply it
   could supply the flattering answer.

   **Still open:** the channel itself. Env vars remain writable by shared-scope code,
   and a Stop/SubagentStop hook shell inherits neither direnv nor a login PATH. The
   question the record does not answer is the one that matters for the applier — not
   "do these values agree", which rows 2 and 3 already satisfy, but **"who set this,
   and what entitled them to"**.

2a. **The same shape, twice more** (survey, 2026-08-29).

   - **sprintctl.** `backend.py:332-348` genuinely cross-checks a flag/env/cwd
     `repo_id` against the committed `.sprintctl/backend.json`. But `db.py:316-319`
     reads `SPRINTCTL_DB` with no cross-check against `resolve_repo_identity` at
     either call site: tenant identity walks up from the CWD while the store path
     comes only from the environment, and the two are never compared. `SPRINTCTL_DB`
     is sprintctl's `AUDITCTL_DB`.
   - **The binary half of "where am I" is still open.** Four resolvers, three
     policies: `hooks/auditctl-resolve.sh:43-63` and `hybrid_dispatch.py:2304-2326`
     carry the ELF guard and honour `AUDITCTL_BIN`; `metanarrative.py:84` has
     neither; `dispatch_release.py:1071` accepts a bare name on `shutil.which()`
     alone. Both of the latter swallow failure, so a shared-scope
     `AUDITCTL_BIN=/bin/true` silences telemetry without a trace. This contract
     closed the *root* half of "every tool rediscovers where am I" and left this one.

   The counter-example worth copying is `AGENTOPS_ROOT`: read with a script-relative
   default, passed explicitly to children, and `env.pop`'d before spawning a worker
   (`hybrid_dispatch.py:1987`) precisely so the worker cannot inherit the
   coordinator's checkout. It is the one channel in the stack with an explicit
   anti-leak.

2b. **`.auditctl-id` has zero instances.** The tracked identity declaration added to
   stop identity coming from a directory basename exists in code
   (`auditctl/paths.py:40,76-103`) and is written nowhere: every `repo_id` in the
   fleet is still a basename. The mechanism that would make identity travel with a
   repository is built and unused.

3. **Three resolvers is worse than two — closed 2026-08-29.** After a44f01d there
   was a bash mirror of the walk in `auditctl-resolve.sh`. auditctl 0.1.5 is now what
   runs on every host that publishes (workstation, devbox, and vuoro-shared through
   vuoro-service 0.1.58), so the precondition held and the mirror is retired:
   `auditctl_export_root` is gone, and with it the root-setting in
   `dispatch_release.py`, `hybrid_dispatch.py` and `metanarrative.py`. No caller
   decides the root any more; the publisher does. REQ-025 asserts that no hook or
   driver assigns `AUDITCTL_ARTIFACTS_ROOT`, and REQ-026 publishes from two
   repositories with nothing set and checks each event landed under its own — which
   is also what catches a host downgraded below 0.1.4.

   `artifacts-root.default` survives, narrowed to one consumer that was never
   auditctl's: `metanarrative.py` uses it as the floor for the *model record* store,
   a workspace-scoped artifact with no repository of its own. That is a different
   question from "where do this session's shards go", and conflating the two is what
   put one file in both roles.

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

## Fleet state, measured 2026-08-29

Every audit store, paired with **its own** configured root rather than a guessed one.
The first sweep of this table used `env={}` for all of them and reported five false
index-only stores — the same pairing error, made a third time, which is why the method
is now written down: read each repo's `.envrc`, never assume the default.

| repo_id | index | shards | index-only | convention |
|---|---:|---:|---:|---|
| agentops | 600 | 600 | 0 | co-rooted |
| auditctl | 4 | 4 | 0 | pooled |
| bindery-core | 42 | 42 | 0 | pooled |
| gitops-nixos | 14 | 14 | 0 | co-rooted |
| homelab-analytics | 21 | 4 | **17** | co-rooted |
| scribectl | 53 | 53 | 0 | co-rooted |
| sprintctl | 46 | 46 | 0 | pooled |
| dev | 236 | 236 | 0 | co-rooted |

`gitops-nixos` was repaired by co-rooting (`f7405e1`): its 14 events lived at the
workspace root in no git repository. Declaring the pooled convention in `.envrc` was
the smaller fix and the wrong one — `.envrc` is gitignored there, so the declaration
would have been as host-local as the problem it described.

### `homelab-analytics` is irreducible, and nothing is lost

One stream (`2f71604c`) split across two roots by a same-day convention change:
17 events at the workspace root, 4 in the repository, sequences **interleaved**
(`[1,2,4,7,9-14]` and `[3,5,6,8]`). Together they are complete; every one of the 21 is
on disk.

It cannot be reconciled, and the reason generalises: merging requires mid-file
insertion into a shard that is committed and pushed, which the append-only guard
refuses; moving the other way is a shard deletion, which it also refuses; and reading
both roots fails continuity because shards are read in path order, which interleaved
sequences violate. Rebuilding the index from either half alone would discard real
events — unlike the agentops case, these are not fixtures.

So it stays split and documented. The gate for this one store reports 17 index-only,
and that number means *"two roots"*, not *"lost"*.


## SessionBinding v0 (2026-08-30)

The session-scoped half has a producer. It records, once per session and never again:
harness, actor, host, the **resolved environment record with its revision and digest**,
the workspace and its `project_id`, and — the part this was built for — every settings
layer in effect by path *and content digest*, present or absent.

That last field is the answer to open finding 2's residue. The question was never "do
these values agree", which a coherent redirect already satisfies; it was **"who set
this, and what entitled them to"**. A shared-scope process that changes what a session
may do changes one of those files, and the digest is what makes the change legible
afterwards from the record alone.

Three properties are enforced rather than asserted:

- **Atomic** — written to a temp file and `os.replace`d, so a reader sees a whole
  binding or none.
- **Fail-closed on contradiction** — `SessionStart` fires again on resume, clear and
  compact. The first write wins; a later one is compared field by field and, if any
  immutable field differs, the run exits non-zero naming them and does **not**
  overwrite what is on record.
- **Attributed** — `resolution_source` on the environment (`hostname-match` /
  `unresolved` / `unreadable` / `unparseable`) and on the project (`ancestor-walk` /
  `undeclared` / `unparseable`). A host with no matching record produces a binding that
  says `unresolved` and names why, rather than a guess.

**Resolution is borrowed, not re-derived.** The environment record comes from
`resolve_environment_record` — the same function `render_environment_context` and
`project_release` use, hostname normalization and `.example` exclusion included.
Re-implementing that in the hook's shell would have been the defect this document
exists to end, one layer up.

**It is not `session-capsule/v1`, and two handovers said it was.** The capsule is
*end*-of-session exhaust — git diff, verification results, an end kind — answering
"what did this session do". A binding is written at the start and answers "what is this
session, and what entitled it". Producing capsules would have satisfied the plan item
while leaving the entitlement question exactly as open as it was; that is the third
instance this week of verifying the thing next to the thing.

**What v0 does not do.** No applier — sequencing step 3's second half is untouched, and
`materialize_project.py` plus NixOS activation remain the two appliers that a third must
absorb rather than duplicate (open finding 4). Nothing consumes the binding yet, so the
first falsifier — *a tool can consume the resolved context and still need to walk the
tree itself* — is not yet under test. Cross-host collision (finding 5) is unaddressed:
two hosts produce bindings with the same shape and no host field in the path, though the
binding itself now carries `host.hostname`, which is one input the shard path never had.

**First real instance**, from a headless session on the workstation:
`environment.resolution_source: hostname-match` → `workstation-linux` revision 3;
`workspace.project.resolution_source: undeclared`, honestly, because that session
started outside any project; four settings layers, one present. The schema had 81 test
functions and zero instances for a week. It has instances now.

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
3. File-backed `SessionBinding` v0 + transactional applier. **v0 landed 2026-08-30**
   (`templates/dispatch/scripts/session_binding.py`, `session-binding.schema.json`,
   registered as a `SessionStart` hook on both hosts). The applier is not part of it.
   See §"SessionBinding v0" below.
4. NixOS and Arch/systemd triggers generated from one definition.
5. Test on workstation, devbox, one clean disposable executor.
6. Promote only proven projections.
