# Target state: agent tooling and dispatch estate (2026-09-17)

**This is a target-state record, not a description of current behaviour.** Every claim
below is where the estate is meant to end up. Current behaviour lives in `AGENTS.md`,
runbooks and specs.

**Why this file exists.** The accepted end state for Vuoro and the agent tooling around it
is the far-future walk, adopted as owner decision D1 on 2026-09-14 under delegation. It
lives only in unversioned artifacts:
- `/projects/dev/_artifacts/agentops/session-notes/2026-09-12-vuoro-planning/DOSSIER-far-future-architecture.md`
  (§3 end state, §5 ownership, §11 critical path S0-S8, §13 kills, §15 triggers);
- `/projects/dev/_artifacts/agentops/session-notes/2026-09-14-owner-decisions.md` (D1-D4).

S2 item 6 then deleted tooling using "no outside consumer", which is not the criterion. The
operator directive (relayed 2026-09-17 by the S2 coordinator session) is that deployment,
deprecation and retirement follow from the goal state. This file carries the part of the goal
state that decides the agent tooling, in a repository.

**Status vocabulary:**
- `accepted-delegated`: adopted under the owner's 2026-09-14 delegation, with the source cited.
- `proposed`: derived by the oracle session on 2026-09-17 and not yet accepted.
- `superseded`: replaced, with the successor named.

## Target claims

| id | Claim | Status | Source |
|---|---|---|---|
| TS-1 | Vuoro owns release, evidence and decision semantics inside sprintctl's served authority. It is not a runner, queue, model router or worker supervisor. | accepted-delegated | owner-decisions D1; dossier §3, §5 |
| TS-2 | Execution, sandboxing and model choice stay native to the harness (Claude Code, Codex, OpenCode) and are excluded from Vuoro and agentops. Vuoro records only the observed profile digest. | accepted-delegated | dossier §5 Externalizes "EXCLUDE"; §13 kills PLAN T8 (both dispatch paths retire) |
| TS-3 | Role and skills are observed, not compiled: instruction and skill digests are recorded at session start (S6). No compiled profile, skill lock or role preset. | accepted-delegated | dossier §3 table "observed profile digest", §5 "instruction digests are observed, not compiled", §11 S6 |
| TS-4 | Two harness hooks carry Vuoro semantics: session start (binding plus profile digest) and stop (cost snapshot). Local guard hooks (sandbox, NFS, bounded read, forge credential) stay as operator enforcement. All hooks live outside `templates/dispatch`. | accepted-delegated (Vuoro hooks); proposed (guard hooks) | dossier §5 Owns, §10 L2 |
| TS-5 | Accept, reject, withdraw, supersede and revise are one Decision object, bound to a Release digest and evidence digests. It is the only writer of terminal status (S3). No parallel acceptance records. | accepted-delegated | dossier §4 Decision row; §11 S3 |
| TS-6 | Evidence is append-only and has one home (S4). Until the S4 import, auditctl shards committed in repos are authoritative evidence and must not be rewritten. | accepted-delegated | dossier §8 Migration row ("auditctl authored rows keep their digests"), §10 L1.4, §11 S4 |
| TS-7 | Cost per release and profile comparison are derived queries: the newest cumulative snapshot per session, joined through the binding. No settlement writer, no hand deduplication. | accepted-delegated | dossier §4 Derived, §7 capabilities 8-9, §11 S6 |
| TS-8 | Continuation works across session, host, model and harness through a handoff checkpoint: handoff/v1 files now, ledger evidence from S6. Harnesses without SessionStart (Codex) need an explicit launch path. | accepted-delegated (checkpoint); proposed (Codex launch path, since Codex is live: 71 sessions 2026-09-01..15) | dossier §8 Recovery row, §11 S6 |
| TS-9 | Resumability and successor export are proven by rehearsal (S8), not asserted. | accepted-delegated | dossier §10 L1.7, §11 S8; direction §13 falsifier 1 |
| TS-10 | Legacy direct-DSN writers are fenced by mechanism at S5. Until then the fence is a check that no shared profile or `.envrc` selects a direct PostgreSQL backend. | accepted-delegated (S5); proposed (interim check) | dossier §9 "Legacy writers unfenced", §11 S5 |
| TS-11 | Dispatch manifests are not an authority (0 manifests as authority). `review_required` becomes the Release acceptance-contract default. Manifests and their schema retire once S3 contracts and S6 digests replace their remaining inputs (skill selection, verification routes). | accepted-delegated (end); proposed (retirement point) | dossier §5 Absorbs, §6.3 |
| TS-12 | Declared contracts are measured for producers before a new one is added and before one is retired. Machinery with zero outcomes for six months is deleted. | accepted-delegated (trigger 7); proposed (producer instrument until S5 catalog queries) | dossier §15 trigger 7; direction §13 falsifier 11; `/projects/dev/AGENTS.md` measure-before-declaring |
| TS-13 | Metanarrative claims, observations and kctl knowledge become Evidence kinds (claim, lesson) plus Decisions at S4, when kctl retires. `agentops metanarrative` stays until then. | proposed | dossier §5 Absorbs (kctl data as lesson evidence), §11 S4 |
| TS-14 | Project-instance folders (`_projects/*`) are derived work folders, never a store. `materialize_project.py` stays keep-narrow until S6 ledger checkpoints cover cross-host resume, then gets re-decided against trigger 7. | proposed | dossier §6.3 (local stores 7 to 3), §8 Recovery row; disposition-register `project-instance-runtime-envelope` |
| TS-15 | Native harness telemetry is emit-only observation (OTel to Langfuse under the accepted harness-evidence policy). Its attribute allowlist must exist and be checked in CI before the exporter is enabled. | accepted-delegated (policy 2026-09-14) | `agentops/docs/architecture/harness-evidence-policy.md:3,196-210`; dossier §5 telemetry DEPEND emit-only |

## Path (agent-tooling moves only)

1. **Now (S2 remainder).**
   - Restore the tools whose target role is live: TS-6, TS-8, TS-10, TS-12, TS-15, and the schemas that kept producers still reference.
   - PR-B deletes `templates/dispatch/hooks`, including `lifecycle-adapters.v1.json`.
2. **S3.** Decision and Release land. The sprintctl capability-receipt record types are folded
   into Decision and legacy evidence in the same migration.
3. **S4.** One evidence home. Retire the append-only shard check, session mechanization,
   kctl and the metanarrative stores.
4. **S5.** DSN revocation. Retire the interim DSN check and the producer instrument, which
   becomes a catalog query.
5. **S6.** Session binding records instruction and skill digests; cost and profile queries
   are derived; ledger handoff checkpoints replace handoff/v1 files. Retire dispatch manifests,
   their schema and `sync_skills.py`.
6. **S8.** Rehearsed export and import, reusing the resume probe's scenario.

## Tripwires (evidence that this target is wrong)

- **Increment 0 re-run at 18 or more of 20 answerable.** The kernel is unnecessary and S3-S8
  do not run; tooling kept "until S6" must be re-decided on its own evidence (dossier §15
  trigger 1).
- **Observed digests can't distinguish outcomes after S6.** If profile comparison (capability 8)
  can't separate first-pass acceptance by observed profile digest over a quarter, then "observed,
  not compiled" (TS-3) is wrong, and compiled profiles (AgentProfileRevision, skill lock) come back
  into scope.
- **Sustained concurrency above 5 workers,** or harness-native subagents failing the maintenance
  lane's cost per accepted item. TS-2 is wrong for bulk work; durable execution by DEPEND is the
  preserved option (dossier §15). Do not revive hybrid dispatch.
- **A Codex or OpenCode session can't continue a Claude handoff (or the reverse) from the
  checkpoint alone.** TS-8 is unmet.
- **Six months with zero hits from a restored interim tool.** Delete it (trigger 7 applied to
  this file).
