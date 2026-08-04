# Handover — Plan 1 migration program, 2026-08-03

**generated_at:** 2026-08-03T18:05Z (workstation)
**status:** Cutover candidate qualified. Pre-`#2080` preflight **FAILED** on a
production baseline divergence. Nothing deployed, migrated, or reconciled.

> Per agentops#2101: this document does **not** outrank live state. Every claim
> below is tied to a basis revision or an artifact hash. Re-verify against the
> live tracker before acting. Volatile observations (claims, sessions, pods,
> clocks) expired 2026-08-03T23:50Z and **must be re-taken**.

## Basis revisions (origin/main at generation)

| Repo | SHA |
| --- | --- |
| sprintctl | `c9725d39f6e2dc45b3c9934b43bfb2510d4b1e63` |
| actionq | `e82d7bfe87eef847d1814124e0aa45543e82d539` |
| vuoro | `10cb208b6ee9b34e0158e68f14f831eb4d3ef3da` |
| appservice | `76a6a741b675a64fb61e9c8227550110bf02020e` |
| agentops | `95de345d7aa8fbd9a49987653bb0edb0c4879d3b` |

## STOP — read this before doing anything with `#2080`

The live `vuoro-shared` work ledger is **schema 5 with ZERO maintenance
relations**. The schema-5 maintenance bridge is **not staged in production**.

Every qualification of the candidate built state 1 as "work 5 **+ staged**
maintenance extension". Tested against real production parity (schema 5, bridge
not staged) the candidate **fails to start**:

```
CompositionError: runtime compatibility failed for: work
```

Deploying the candidate against the current live ledger **would crashloop** —
the same class of outage as v0.1.33.

**Required next action:** stage the maintenance bridge on the live schema-5
ledger (`sprintctl remote-schema stage-maintenance-bridge`, the additive
schema-5-safe operation from #2090) with its own rollback position and proof,
**before** rolling the successor image. Requires the operator CLI at 0.2.17.

## Completed and closed

| Item | Result |
| --- | --- |
| actionq **#2091** | v0.1.16 — `e82d7bf`. Also published `vuoro-adapter-v1-e82d7bf` carrying `actionq-contracts` 0.1.1 (registry-unpublished, needed for standalone install) |
| sprintctl **#2090** | 0.2.16 — `380cd8aa`. Trigger-function pinning + privilege-independent fingerprint (catalog fingerprints unchanged) |
| vuoro **#2092** | v0.1.34 — `sha256:463cd409…` **superseded, do not deploy** (pins sprintctl 0.2.16) |
| sprintctl **#2093** | 0.2.17 — `c9725d39`. Database statement time authorizes capability transitions |
| vuoro repin PR #13 | v0.1.35, merge `76551a08` |
| vuoro PR #14 | capability safety gates, merge `10cb208b` |
| agentops **#2104** | audit packet repaired by the devbox session |

## The qualified cutover candidate

```yaml
runtime_candidate:
  image: ghcr.io/bayleafwalker/vuoro-service
  digest: sha256:d23387480772a4d6b41f8fdf1c1d0f43a985a1087f76f4c4e80cc4325c53060e
  tag: vuoro-service-v0.1.35
  composition:
    sprintctl: 0.2.17
    actionq: 0.1.16
    actionq-contracts: 0.1.1
    kctl: 0.1.1
    auditctl: 0.1.0
qualification:
  repin_merge: 76551a089710dfb735f9745d8909c49f149121ee
  safety_merge: 10cb208b6ee9b34e0158e68f14f831eb4d3ef3da
  harness_revision: 10cb208b6ee9b34e0158e68f14f831eb4d3ef3da
```

**Pin the INDEX digest, not the tag.** `podman pull` + `RepoDigests` can return
the *platform* digest (`c7397e91…`), for which `gh attestation verify` 404s.
Take the digest from the publish run's `subject-digest`.

Reproduce the qualification: check out vuoro at `10cb208b`, run
`scripts/verify_pre_migration_startup.py <digest>`. Eight gates, all true.

## Preflight receipt

`/projects/dev/_artifacts/agentops/preflight/pre-2080-preflight-2026-08-03.json`
sha256 `86ead0f2b38eb18a1655a0d5ff5c3194ab8da35ae5a2ccdc97c43e28c40ee2b9`

| Gate | Result |
| --- | --- |
| candidate_identity | pass |
| authority_integrity | pass |
| dispatch_admissibility | pass |
| operation_capability | **warn** |
| production_baseline | **FAIL** |
| clock_coherence | pass (58 ms offset) |

**operation_capability warn:** the operator CLI on this workstation is
**sprintctl 0.2.13** — four releases behind the candidate, predating both the
#2090 bridge and the #2093 fix. Upgrade to 0.2.17 before executing `#2080`.

**Baseline confirmed otherwise:** GitOps pin == live image `sha256:9c1d0e53…`;
known-good `52544abd` is an ancestor of appservice main; 1 ready pod, 1
endpoint; `vuoro-execution-migrate-v6` and `vuoro-execution-v6-quiescence` both
Suspended; PostgreSQL 16.13; execution ledger at 3.

**Continuity already satisfied:** replicas=1 with default RollingUpdate 25%/25%.
Kubernetes floors `maxUnavailable` to 0 and ceils `maxSurge` to 1 at one
replica — the required overlap, no manifest change needed.

## Open items

| Item | Pri | Gate |
| --- | --- | --- |
| sprintctl **#2095** | p1 | next-work is a dependency projection, not a dispatch queue. **Do not infer quiescence from it.** Blocks #2075 |
| sprintctl **#2096** | p1 | **Plan 1 cutover blocker.** Classified host-local; does NOT block #2080 and needs no repin |
| sprintctl **#2097** | p2 | served-mode cross-repo gaps. `--allow-markerless-nonlocal` is acceptable for read-only diagnosis only — **never** for claims, transitions, grants, or safety-gate evidence |
| sprintctl **#2098** | p3 | persist DB decision instant — **after cutover** (changes catalog fingerprint, would invalidate the pin) |
| sprintctl **#2099** | p4 | `prepare()` still uses caller `at` for expiry |
| agentops **#2100** | p2 | split `mechanical_patch` / `build_from_spec`; fix "Vuoro only" runbook drift |
| agentops **#2101** | p3 | handoffs must not outrank live tracker state |
| agentops **#2102** | p4 | worktree-aware cleanup + PAT preflight |
| kctl **#2103** | p3 | candidate-submission authority short of publish |
| sprintctl **#2072** | — | active; close only from live old-state compatibility evidence |
| sprintctl **#2075** → vuoro **#2076** | — | explain path; **after** cutover. Blocked by #2095 |

### #2096 refinement

In 0.2.17 the producer append already writes the record INSERT and
`UPDATE outbox_stream SET next_origin_seq` in **one transaction** with rollback.
The quarantine artifact that motivated the item is dated **2026-07-26**,
predating 0.2.16. Verify reproducibility on 0.2.17 before writing new atomicity
code. The `authority doctor` command is still worth building — this preflight
had to assemble it by hand from sqlite, `stat`, `find -perm`, and
`authority reconcile`.

## Critical path

```
1. Stage the schema-5 maintenance bridge on the live ledger   <-- BLOCKING
   (upgrade operator CLI to 0.2.17 first)
2. Re-run the pre-#2080 preflight; volatile gates must be fresh
3. Appservice #2080 — pin d2338748, migration-role path,
   atomic migration+GRANT proof with failure injection,
   deploy on work5/execution3, preserve rollback, STOP before migration
4. Close #2072 from live evidence
5. Resolve sprintctl#2096 (mandatory before cutover)
6. Plan 1 cutover — technical dispatch/producer fence, direct claim and
   session enumeration, fresh backup, migrations, v6 startup, reconcile,
   explicit promote decision
7. sprintctl#2095 -> #2075 -> #2076 (after cutover)
```

## Working conventions that earned their keep

- **Branch from freshly fetched `origin/main`**, never local `main`, and assert
  `git merge-base HEAD origin/main == git rev-parse origin/main`. A stale local
  `main` in vuoro cost a full duplicated implementation this session.
- **CI is the authoritative gate at release boundaries.** Local failures were
  environmental twice; CI caught a real deterministic failure once.
- **Negative controls before believing a proof.** Reverting the fix must break
  the new tests. This caught a decorative hardcoded assertion.
- Disposable PostgreSQL **16** (production CNPG major); DB name must start with
  `sprintctl_test_`; the harness must revoke runtime write access to each
  domain's migration ledger or every adapter correctly reports incompatible.
- `podman run -i` is load-bearing when piping a script to `python -`.
