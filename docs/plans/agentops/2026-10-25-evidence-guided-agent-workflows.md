---
doc_id: agentops-evidence-guided-agent-workflows-2026-10-25
status: operator-requested-implementation-plan
effective: 2026-10-25
supersedes: []
---

# Evidence-guided agent work: capture, judgment, completion, and reuse

**Scope:** implementation packages with owner-specific acceptance, not an active
deployment, approval of new authorities, or a new backlog database. This is the
October 25 extension of [the estate evolution plan](2026-10-17-estate-evolution-plan.md),
[portable agent workflows](2026-10-24-portable-agent-workflows.md), and
[accepted-outcome measurement](2026-10-22-opportunistic-follow-through/outcome-measurement.md).
The [September target state](../2026-09-17-target-state.md), amended on October 15,
wins if an older design or tool guide disagrees. The October 21
[EC-00 decision](../../architecture/2026-10-21-ec00-contract-stack-adr.md)
selects TypeSpec to OpenAPI / JSON Schema for estate-owned interface contracts;
EC-00 qualification and migration work must not be presumed finished.

**Instruction:** build a small evidence-to-completion slice first. Use cheap models
as replaceable *interpreters of observations*, not mandatory workflow gates.
A verified completion may settle under the currently effective owner contract
without waiting for a human, narrator, classifier, or audit publisher. An
after-the-fact review is valid; it is not an implicit precondition.

## Baseline, source truth, and exclusions

- Native Claude, Codex and OpenCode harnesses execute and choose models and
  providers. Agentops may provide guidance, fixtures, hooks and evaluation
  instrumentation, **not** an execution host, queue, permanent model router,
  universal transcript proxy or alternative session database.
- Sprintctl is the reference work, revision, Release/Decision and evidence owner.
  Vuoro composes released owner operations and protected-side effect contracts.
  ActionQ federates external execution references; its retired daemon/worker and
  actionq-dispatch do not return. `vuoro-reconciler` is the trusted **effect
  intent** executor, not the proposed work-completion assessor.
- Auditctl's local SQLite/NDJSON record and central observation/decision
  envelope remain distinct from owner acceptance. Existing committed Auditctl
  shards preserve original identities and digests. The S4 evidence-home migration
  is **gated**, not an assumed completed cutover. Kctl is retiring: no new Kctl
  lifecycle. Outctl remains a frozen discovery artifact, not a dependency.
- `vuoro_evidence.experiment` already compares supplied owner-observed outcomes:
  missing cases count, unknown cost is not zero, and synthetic tests do not
  establish real-world superiority. See
  [accepted-outcome learning](https://github.com/bayleafwalker/vuoro/blob/main/docs/architecture/accepted-outcome-learning.md).
  Reuse it rather than inventing a second results store.
- Existing harness evidence [policy](../../architecture/harness-evidence-policy.md),
  session-mechanization historical [contracts](../../dispatch/session-mechanization-contracts.md),
  blind review [replay](2026-10-25-blind-code-review-replay.md), and the
  [subscription cross-harness pilot](2026-10-25-subscription-cross-harness-pilot.md)
  are inputs. Their results are *not* a claim of universal hooks or provider
  qualification. Old session capsules/scribes are reference cases, not engines
  to resurrect. Distinguish code merged, release published, deployed, verified
  in target runtime, and accepted outcome.

**Backlog ownership:** AE IDs below are immutable planning/reference IDs, **not
Sprintctl item IDs or GitHub issue statuses**. Before implementation the
authorized owner reconciles each packet against served Sprintctl work and binds
it to existing items (or adds the genuinely missing owner items through Sprintctl
commands). Do not duplicate the writable queue in GitHub, YAML or a new service.
Track each owner result under its authoritative work ref and link this document.
If served access is unavailable, record `work_binding: unknown`; this document
does not make any item ready or claimed.

## Minimal vertical slice: one useful outcome

A named work item and acceptance contract receive a code-bearing session in an
isolated worktree. The native wrapper/harness exports an attributable stop
observation, exact commit and test-result references, not raw transcripts.
A bounded offline consumer derives a proposed semantic finding and retains
the source basis. A work-owner-side evaluator reads **current** requirement,
Release digest, work revision, current owner state and independently obtained
verification. It produces one of:

1. **Complete:** current authoritative evidence satisfies the existing
   contract, so the authorized owner operation records acceptance automatically.
2. **Missing or conflicting:** no completion; request one specific verifier
   result, reacquire stale evidence, or escalate genuinely ambiguous obligations.
3. **Complete with a new finding:** record completion as above and separately
   propose the optional follow-up; do not retroactively make it a gate.
4. **Incidental/no change:** no task transition or manufactured backlog work.

A crash, late report, duplicate source event, disappearing hook, failed audit
upload or model outage must not create duplicate effects, false evidence, false
completions or needless postponement. If a source fact was never captured,
report `unknown` with a coverage denominator rather than claiming absence.
Model conclusions, recorded decisions, policy evaluations, domain owner
Decisions and effect receipts remain distinct.

## Delivery packets and prerequisites

| Packet | Owner and scoped deliverable | Prerequisite | Acceptance / exit |
| --- | --- | --- | --- |
| **AE-01** | Agentops + native harness adapters: inventory and pin event sources, implement minimal session/CI/Git observation envelope and offline replay; no new runner | Existing harness telemetry policy; EC-01 inventory | Two real harness types plus one simulated missing-hook case; full source/observed coverage matrix, privacy, retry, restart and outbox proof |
| **AE-02** | Evidence owner with Auditctl publisher: asynchronous source-linked typed observation and optional cheap scribe | AE-01 fixture; S4 boundary mapped | Deterministic baseline vs cheap extraction, immutable basis/model/profile, supersession on source revision, two distinct downstream consumers, zero raw secret leakage |
| **AE-03** | Sprintctl work/Release owner: acceptance-side deterministic completion assessment and bound follow-up proposals, **not** `vuoro-reconciler` | Existing work Release/Decision; AE-01 evidence; AE-02 optional | Exact current digest/basis, no false completions, no duplicate owner effects, clean completion without scribe, explicit gaps/conflicts and optional post-completion work |
| **AE-04** | Agentops evaluation + existing Accepted-outcome/Acceptance Lab methods: frozen playbook choice benchmark | Existing `jev/eval` and 30–50 representative labeled choices | Rules/current baseline vs local d1/Jev/Clef/Decisions; held-out labels, false-route costs, p50/p95; two-evening initial stop rule |
| **AE-05** | Vuoro evidence learning + native provider evaluators: accepted-case model comparison | Exact `ExperimentRecord` population and owner record imports | DeepSeek baseline vs GLM/Qwen on matched issue set; Gemini only for differentiated long-context/multimodal tasks; no unmeasured provider ranking |
| **AE-06** | Local-inference owner: resident d1-3B GTX 1060 feasibility and safe hosted fallback | AE-04 fixture; current GPU inventory | Q4/Q8 memory/driver/CUDA, warmed p50/p95, cold starts, throughput, power, failure recovery; 3090 contention and fallback explicit |
| **AE-07** | Agentops research only, future independent application owner: read-only persistent personal dispatch/narrative prototype | AE-01 events; AE-02 derived claims optional | One week reconstructed from sources, versioned persona, false-claim review, attention budget, wake/sleep, no grants or automatic writes |
| **AE-08** | Scribectl writing owner: multiple cheap draft/idea alternatives and selective premium editorial synthesis | Writing/canon fixtures, AE-05 measurement method | Blind human preference, voice/canon fidelity, rejected drafts and review cost; no auto-ratification |
| **AE-09** | Frontier Weave asset owner: generation briefs, variants and checks for one approved design brief | Existing asset provenance/art direction and permission | Real asset manifest, rights/consistency/accessibility review, fixed input/review costs; no automatic canon or playable asset promotion |
| **AE-10** | Frontier Weave game owner: *offline* faction-choice replay first; multiplayer/runtime only by later owner decision | AE-04 bounded choice fixture, authored action grammar | Deterministic game authority, reproducible seeds, persona/belief distinction, diverse long-horizon outcomes; first playable remains model-independent |
| **AE-11** | Homelab Analytics: in-process typed signal/analytics experiment | Source/trust/reporting rules; AE-02 fixture optional | Deterministic features first, p95 decision latency and false positives, no actuation or model-backed factual overrides |
| **AE-12** | Homelab Analytics research consumer: out-of-process weekly state-of-systems observations and synthesis | Source/rights inventory, AE-02 multi-consumer finding | Reproducible ingestion and novelty/dedup comparison; sourced report, known missing sources, total cost and premium reasoning saved |

Packets AE-04, AE-05, AE-06 and the domain pilot fixture design can proceed
independently of S4 deployment. AE-02 can replay frozen records before S4 but
cannot silently establish a second hosted evidence authority. AE-03's actual
completion write waits for existing owner contract/release qualification and
remains independent of the optional scribe's availability. Creative and
household-domain pilots do not become Vuoro product features by proximity.

Owner-specific delivery sources:

- [Auditctl: semantic evidence source and async projection](https://github.com/bayleafwalker/auditctl/blob/main/docs/plans/2026-10-25-semantic-evidence-consumers.md)
- [Sprintctl: evidence-guided completion](https://github.com/bayleafwalker/sprintctl/blob/main/docs/plans/2026-10-25-evidence-guided-completion.md)
- [Vuoro: model comparison and learning integration](https://github.com/bayleafwalker/vuoro/blob/main/docs/plans/2026-10-25-model-evaluation-integration.md)
- Local-inference: `docs/plans/2026-10-25-resident-decision-model.md` (owner repo)
- [Scribectl: writer-choice evaluation](https://github.com/bayleafwalker/scribectl/blob/main/docs/plans/2026-10-25-cheap-writing-choices.md)
- [Frontier Weave: asset and faction experiments](https://github.com/bayleafwalker/frontier-weave/blob/main/docs/roadmaps/2026-10-25-small-model-domain-pilots.md)
- [Homelab Analytics: operational/research analysis](https://github.com/bayleafwalker/homelab-analytics/blob/main/docs/plans/2026-10-25-semantic-analytics-pilots.md)

## Evidence, policy and interface invariants

**No observer grants authority.** Session hook, scribe, classifier, independent
model judge, provider success and central audit receipt are observations or
advice. A terminal Release Decision comes from the protected work owner after
its current policy and evidence rules. The public edge never gains
`effect-apply`. The existing trusted-side reconciler alone applies eligible
protected effect intents, which are not the same as task completions.

**No compulsory model at a known-answer branch.** Deterministic acceptance uses
source-qualified facts. If a model or audit enrichment is down, valid owner
acceptance still proceeds. Conversely missing *required* verification cannot
be replaced with a confident summary. Existing reviewer requirements still
apply where the current contract genuinely needs one; do not insert a new
universal human-approval condition for already-qualified work.

**No invisible fallback.** An attempted model/provider/harness change must
start an attributed attempt under the relevant native authority/binding,
record requested vs actual supplier, rate-limit/error type, data boundary and
billed/estimated/subscription/local-cost provenance. No implicit move from
local/private to externally billed remote inference.

**Source-anchored semantics.** A semantic finding is explicitly
`model-inferred`, `deterministic-derived` or `owner-observed`, plus original
source ref/digest, producer, instruction/profile revision, observation time,
input work revision, retention/privacy class and supersession links. It cannot
be promoted to `owner-observed` by republication. Decisions stored with
Auditctl's closed `observation|decision` classes are historical judgments;
current terminal Decisions are owner-issued. Contracts follow the EC-00
TypeSpec/OpenAPI rules and native owner APIs, not an open-ended
`execute(type,payload)` tunnel.

**No raw prompt collection by default.** Opt-in private raw evidence stays
under host-local retention and access. Telemetry has restricted identifiers
and artifact pointers only. Offline producer retries reconcile durable origin,
sequence and content hash; no blind retries after ambiguous writes or effects.
Loss of capture is measured, never converted into fabricated events.

## Replay and measurement protocol

Pre-register case IDs, source rev/digest, work and release snapshots, legal
choices, frozen classifier prompts/decision profiles, independent labels,
failure costs, data-class permissions, time window and budgets. Use a truly
held-out set; a model's own hindsight label is not an acceptance oracle.
In the first **two evenings** of AE-04, allow at most 30–50 clearly labeled
playbook decisions and an existing rules/small-generative baseline. Stop
rather than engineering a new router if a model cannot distinguish itself on
cost-weighted errors or the labels need extensive retrospective invention.

Record for all expected cases, including absent and failed runs:

| Measure | Denominator and disqualifier |
| --- | --- |
| Capture and attribution | All in-scope sessions and event sources by harness/host; unknown/missing separately |
| False completion / critical miss | All cases eligible for a current-revision completion decision; any unsafe closure blocks advancement |
| Follow-up utility | Predeclared needed actions vs unnecessary work/repeated investigations |
| End-to-end cost | All attempts, rejects, retries, caches, review/recovery/operator time; unknown cost explicit |
| Latency | Warm/cold p50/p95 over specified input sizes; source read through judgment and optional action |
| Observation fidelity | Critical source facts retained, unsupported semantic additions, revoked/stale claims |
| Evidence reuse | Count actual independent consumers per source/digest, not theoretical subscribers |
| Accepted outcome | Real owner Release/Decision join plus separate independent verification and actual use |

**AE-02 kill:** no two genuine consumers, significant critical-fact loss,
or processing/maintenance overhead exceeds repeated retrieval cost.
**AE-04 kill:** no predictive advantage over trivial rules on frozen
cost-weighted labels, or classifier integration exceeds the fixed trial.
**AE-06 kill:** insufficient GPU headroom, unacceptable p95 under representative
input, unstable CUDA toolchain or greater fully loaded cost than hosted.
**AE-07 kill:** invented accomplishments, distracting notifications or an
unreconstructible memory update. **Domain pilots:** stop when candidate volume
increases but accepted useful assets/outcomes do not.

## Required adversarial histories for the first slice

1. Complete requirements and checks, but no scribe response: **owner accepts**.
2. Work revision advances after inference: **stale model conclusion ignored**.
3. The same origin event is delivered twice: one durable observation/read effect.
4. Producer crashes after local append or loses central acknowledgement:
   replay reconciles exact source bytes, not a new event identity.
5. Hook missing for one hosted attempt: numerator and denominator name missing
   coverage, rather than "all good".
6. Failed verification and persuasive model prose: **owner rejects completion**.
7. A current accepted result later yields a nonblocking improvement proposal:
   accepted work stays accepted and follow-up deduplicates.
8. Accepted effect intent with no target receipt: completion is not inferred.
9. Permission denied or secret-containing candidate: no remote model call and
   no authority-grant fallback.
10. Scribe changes its verdict after source revision: historical claim remains
    inspectable, current projection invalidates it.
11. Interrupted caller before effect response: protected owner reconciles
    actual target state before any retry.
12. Multiple candidate attempts share one task: ExperimentRecord counts one
    case, not several successes.

## Delivery order and rollback

**D0: source and schema inventory.** Bind owner packets to current served
work refs, check EC-01/EC-00 and S4 gates, freeze safe input/label cohorts.
Exit with exact owner contracts, qualified/unknown observability by runtime,
and a testable fixture. No runtime changes yet.

**D1: read-only vertical slice.** AE-01 deterministic capture fixture,
AE-04 small offline classifier replay and AE-03 completion *assessment only*.
Prove missing-hook, stale, contradictory and no-scribe cases. Keep feature
flags off for real work writes.

**D2: protected path.** Owner-qualified AE-03 may call the *existing* native
work acceptance operation against an exact revision and grant. Audit and
semantic pipelines run asynchronously; no new approval gates. Independently
replay an ambiguous-effect recovery case.

**D3: reuse and independently ready domain studies.** Qualify AE-02 for one
input and two consumers, AE-05 against an owner-authorized accepted-outcome
source, and AE-06 only after its AE-04 fixture and current GPU inventory pass.
Run AE-07 through AE-12 as independently schedulable bounded studies as soon
as each packet's own prerequisites pass; do not make them wait for AE-05 or
AE-06 unless their packet names that dependency. In particular, AE-08 requires
AE-05, AE-10 requires AE-04, and AE-12 requires AE-02's multi-consumer
evidence. A winner becomes an owner-provided optional capability, not a
permanent global model mapping.

**Rollback:** turn off enrichers and model-backed recommendations first,
preserve source records and owner decisions, stop newly generated follow-up
proposals, restore deterministic current contract evaluation, reconcile any
already submitted owner commands by idempotency key, and verify no work or
protected effects regressed. Storage migration/retention rollback is a separate
S4 owner exercise; never delete or rewrite historical shards as cleanup.

## Non-results and review triggers

This planning commit neither creates Sprintctl items nor implements adapters,
inference, scheduled personal agents, deployed profiles, artifact generation,
live gameplay AI or production analytics. The first qualified result is **one
replayed accepted work item** plus an observable, safely failing negative case;
broad ecosystem claims require their own samples.

Revisit only after measured loss/cost or a newly verified native capability.
The entire programme can be smaller than this list if owner baselines already
meet the same outcomes. Retire experiments with no demonstrated consumers,
even when the demo is charming.
