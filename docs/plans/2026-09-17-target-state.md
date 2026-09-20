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
- `accepted-operator`: taken directly by the operator on the date cited, outside the
  2026-09-14 delegation.
- `superseded`: replaced, with the successor named.

## Target claims

| id | Claim | Status | Source |
|---|---|---|---|
| TS-1 | Vuoro owns release, evidence and decision semantics inside sprintctl's served authority. It is not a runner, queue, model router or worker supervisor. | accepted-delegated | owner-decisions D1; dossier §3, §5 |
| TS-2 | Execution, sandboxing and model choice stay native to the harness (Claude Code, Codex, OpenCode) and are excluded from Vuoro and agentops. Vuoro records only the observed profile digest. TS-16 does not change this: the published
surface carries read, coordinate, record and propose, and no execution. | accepted-delegated | dossier §5 Externalizes "EXCLUDE"; §13 kills PLAN T8 (both dispatch paths retire) |
| TS-3 | Role and skills are observed, not compiled: instruction and skill digests are recorded at session start (S6). No compiled profile, skill lock or role preset. | accepted-delegated | dossier §3 table "observed profile digest", §5 "instruction digests are observed, not compiled", §11 S6 |
| TS-4 | Two harness hooks carry Vuoro semantics: session start (binding plus profile digest) and stop (cost snapshot). Local guard hooks (sandbox, NFS, bounded read, forge credential) stay as operator enforcement. All hooks live outside `templates/dispatch`. | accepted-delegated (Vuoro hooks); proposed (guard hooks) | dossier §5 Owns, §10 L2 |
| TS-5 | Accept, reject, withdraw, supersede and revise are one Decision object, bound to a Release digest and evidence digests. It is the only writer of terminal status (S3). No parallel acceptance records. | accepted-delegated | dossier §4 Decision row; §11 S3 |
| TS-6 | Evidence is append-only and has one home (S4). Until the S4 import, auditctl shards committed in repos are authoritative evidence and must not be rewritten. A run that cannot reach that home has no path to it today, so TS-6 holds for activity inside the perimeter only; evidence from a hosted runtime is absent rather than late until TS-16's record path exists. | accepted-delegated | dossier §8 Migration row ("auditctl authored rows keep their digests"), §10 L1.4, §11 S4 |
| TS-7 | Cost per release and profile comparison are derived queries: the newest cumulative snapshot per session, joined through the binding. No settlement writer, no hand deduplication. | accepted-delegated | dossier §4 Derived, §7 capabilities 8-9, §11 S6 |
| TS-8 | Continuation works across session, host, model and harness through a handoff checkpoint: handoff/v1 files now, ledger evidence from S6. Harnesses without SessionStart (Codex) need an explicit launch path. TS-16's surface is a second route to the same property, not a replacement: a hosted session that can read, claim and record continues from the ledger directly, while the checkpoint stays the route for runtimes that cannot reach a surface at all. | accepted-delegated (checkpoint); proposed (Codex launch path, since Codex is live: 71 sessions 2026-09-01..15) | dossier §8 Recovery row, §11 S6 |
| TS-9 | Resumability and successor export are proven by rehearsal (S8), not asserted. The rehearsal covers runs that can reach the evidence home; a hosted run cannot, so until TS-16's paths exist S8 proves the property for perimeter runs only and must not be read as covering the estate. | accepted-delegated | dossier §10 L1.7, §11 S8; direction §13 falsifier 1 |
| TS-10 | Legacy direct-DSN writers are fenced by mechanism at S5. Until then the fence is a check that no shared profile or `.envrc` selects a direct PostgreSQL backend. Both rest on writers being able to reach an internal database, which is the assumption TS-16 attacks: revoking the DSN does not give a hosted writer a write path, and does not remove the need for one. | accepted-delegated (S5); proposed (interim check) | dossier §9 "Legacy writers unfenced", §11 S5 |
| TS-11 | Dispatch manifests are not an authority (0 manifests as authority). `review_required` becomes the Release acceptance-contract default. Manifests and their schema retire once S3 contracts and S6 digests replace their remaining inputs (skill selection, verification routes). | accepted-delegated (end); proposed (retirement point) | dossier §5 Absorbs, §6.3 |
| TS-12 | Declared contracts are measured for producers before a new one is added and before one is retired. Machinery with zero outcomes for six months is deleted. | accepted-delegated (trigger 7); proposed (producer instrument until S5 catalog queries) | dossier §15 trigger 7; direction §13 falsifier 11; `/projects/dev/AGENTS.md` measure-before-declaring |
| TS-13 | Metanarrative claims, observations and kctl knowledge become Evidence kinds (claim, lesson) plus Decisions at S4, when kctl retires. `agentops metanarrative` stays until then. | proposed | dossier §5 Absorbs (kctl data as lesson evidence), §11 S4 |
| TS-14 | Project-instance folders (`_projects/*`) are derived work folders, never a store. `materialize_project.py` stays keep-narrow until S6 ledger checkpoints cover cross-host resume, then gets re-decided against trigger 7. | proposed | dossier §6.3 (local stores 7 to 3), §8 Recovery row; disposition-register `project-instance-runtime-envelope` |
| TS-15 | Native harness telemetry is emit-only observation (OTel to Langfuse under the accepted harness-evidence policy). Its attribute allowlist must exist and be checked in CI before the exporter is enabled. | accepted-delegated (policy 2026-09-14) | `agentops/docs/architecture/harness-evidence-policy.md:3,196-210`; dossier §5 telemetry DEPEND emit-only |
| TS-16 | The record covers automated activity wherever it runs, not only inside the perimeter. The control question is what proportion of automated activity is reconstructable; for hosted runtimes today it is zero. Two reachability paths are in the target state: a narrow **public** MCP surface for interactive runtimes (Cowork, claude.ai, mobile, Routines, cloud sessions, OpenAI Responses), and the Managed Agents self-hosted worker for unattended runs. The boundary is binding: intent, coordination and evidence may cross to a runtime the operator does not host; effects and credentials may not. Every tool on the published surface classifies as read, coordinate, record or propose, and there is deliberately no effect-apply scope — that absence is a design decision, written down here so a later session does not helpfully add one. A hosted runtime's maximum achievable outcome is an unmergeable branch and a queued intent: the homelab-side reconciler signs, not the cloud session, so the property obtained is a verifiable chain from a signed commit back to a run record naming runtime, model and profile revision. That is recorded and reconstructable, **not** attested, and must not be described as attestation. | accepted-operator (both paths, public surface first; boundary; no effect-apply scope); proposed (tool set, auth mode, E0-E4 shape) | operator DECISION 1, 2026-09-20; edge doc §3 boundary, §5 EffectGrant scope, §7 signing, §8 worker option |

**TS-16's source, and its dependency risk.** The edge doc is `Vuoro at the Edge` (2026-09-19). It
landed as `vuoro docs/plans/2026-09-20-vuoro-at-the-edge.md` (merge c4740f6b); a reader who needs
it can open that file. Its E0-E4 sequence depends on phases of *the first-principles rebuild*
(Phase 0-6, ADR-02, ADR-05), which landed as
`vuoro docs/plans/2026-09-19-agentic-pipeline-first-principles-rebuild.md` — a reader can cite and
open it. That dependency is discharged as of 2026-09-20; no E step is blocked on it being recorded
any longer. The edge doc reverses the rebuild's own §15 "park vuoro.cloud" verdict, on the ground
that the hosted variant serves runtimes the operator does not host rather than external users.

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
7. **E0-E4 (reachability, TS-16).** Runs alongside S3-S8, not after it. Each step names the
   rebuild phases it depends on; those phases are recorded in
   `vuoro docs/plans/2026-09-19-agentic-pipeline-first-principles-rebuild.md` (see above), so no
   E step is blocked on them any longer.
   - **E0.** Harden before exposing anything: evidence chaining, lease expiry with heartbeat,
     rate limiting, endpoint monitoring. *Depends on rebuild Phase 0 and 2.*
   - **E1.** Read-only surface (`list_ready_work`, `describe_work`), one static bearer, dual-era
     protocol support. A day of work, and reversible by deleting the connector. Dual-era support
     is kept because the client protocol-version matrix is third-party and dated July 2026;
     re-check it before dropping `initialize`. Scheduled-task connector bugs have no vendor fix
     confirmation, so Routines is not assumed to work.
   - **E2.** Claims and evidence: `claim_work`, `heartbeat`, `append_evidence`,
     `write_session_note`, `complete_work`, with lease handles, idempotency throughout and
     `(handle, auth_context)` validated per call. *Depends on E0 and rebuild Phase 1.*
   - **E3.** `propose_effect` plus the homelab reconciler, diff-shaped intents only.
     *Depends on E2.*
   - **E4.** Reactive quota failover: `rate_limit_event` as evidence, parked claims on plan
     limits, re-dispatch across families on family limits. *Depends on E2 and rebuild Phase 3
     and 6.*
   - No step adds runtimes for coverage. Codex cloud's lack of MCP support is inferred from
     documentation silence rather than stated, so it is not planned for; if it changes, E1's
     surface works unmodified.

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
- **A month of E1 without the substrate being reached from a hosted runtime.** The need TS-16
  claims is not there; E2-E4 are not built, and the read surface is deleted rather than kept
  warm (edge doc §9 stop condition).
- **A concrete case within six months that genuinely requires an effect-apply scope.** Then the
  "name the imperative class explicitly" clause was hiding a real gap rather than an empty one,
  and TS-16's boundary needs re-deciding rather than reasserting.
