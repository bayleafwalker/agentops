---
doc_id: agentops-outcome-settlement-qualification-2026-11-06
status: operator-requested-implementation-plan
effective: 2026-11-06
work_binding: unknown
supersedes: []
---

# Qualify one operations outcome across an interrupted attempt

The first result is a reproducible lab workflow: publish one analytics partition,
lose the response after publication, and let a different authorized attempt
reconstruct the result without publishing it again. A fresh reader must explain
what was authorized, what changed, what remains uncertain and why the work owner
accepted or refused the outcome. Useful work with less operator intervention is
the product test; a fault-injection demonstration alone is mechanism evidence.

This is the AgentOps qualification profile for the
[Vuoro outcome-settlement proposal](https://github.com/bayleafwalker/vuoro/blob/main/docs/plans/2026-11-06-outcome-settlement-proposal.md).
The operator requested stronger plans and repository landing on 6 November 2026.
This document defines implementation and qualification work, not completed runs,
new grants, deployment authorization or an accepted change of product strategy.
The connected-work direction, October 29 hosted-service amendment and workspace
C2 requirements remain in scope. The first proof does not use a live Cloud rollout,
credential rotation, production failover or private incident data.

## Compose the existing programme

Source baseline: AgentOps `fb918f787a7626b8f8f9bc24e3973024da9c36de`.
The [estate plan](2026-10-17-estate-evolution-plan.md) and
[KAOS trace](2026-10-18-kaos-2028-roadmap.md) retain their requirements and work
references. This profile narrows a shared qualification case; it does not add
another queue or independently mark those activities complete.

| Existing activity | Contribution of this proof | Still separate |
| --- | --- | --- |
| EE-06 / VU-K02; SP-K01 and SP-K02 | Cold successor, current owner facts, exact artifact and effect reconstruction | Broader installed workflows and accepted-result export/import |
| EE-08 / VU-K06 and VU-K07 | Current authority at the protected effect boundary; refusal of stale or widened attempts | General identity, policy sourcing and all-host qualification |
| EE-09 / AU-K01 | References to original evidence and explicit missing links | Historical S4 import and cutover; no rewritten audit shards |
| EE-10 / VU-K10; AO-K03 | One actual native-harness change with declared capability limits | General supplier replacement or account qualification |
| EE-11 / CL-K01; EE-12 / CL-K04 | A second operator repeats setup, interruption and recovery from retained instructions | Supported distribution, onboarding and service commitments |
| EE-16 / VU-K09; EE-23 / AO-K02 | Accepted, independently checked and actually used outcomes with whole-population burden | Vendor superiority, causal attribution or automatic expansion of autonomy |

Reuse [PW-01/PW-05](2026-10-24-portable-agent-workflows.md),
[AE-01/AE-03](2026-10-25-evidence-guided-agent-workflows.md), the
[capture and export profile](2026-10-30-capture-integrity-and-export.md), and
[AO-K02's outcome-measurement companion](2026-10-22-opportunistic-follow-through/outcome-measurement.md).
The [execution-placement matrix](2026-11-05-execution-placement-qualification.md)
remains source-mapped, with its four owner fixtures unqualified until run. Add
this case to those owners' evidence; do not turn a passing document validator
into a runtime qualification result. Before implementation, reconcile current
served items and pin these governing revisions. `work_binding: unknown` records
that this planning edit did not query or change served work state.

## Responsibilities and decision boundaries

| Owner | Responsibility in the first case |
| --- | --- |
| Sprintctl | Stable work identity, current revision, Release/Decision and outcome acceptance; retain late reports against their originating attempt. See the [owner profile](https://github.com/bayleafwalker/sprintctl/blob/main/docs/plans/2026-11-06-outcome-settlement-owner.md). |
| Sovite | Admit the exact execution binding; manage attempt lifecycle, cancellation and fencing through its owner contract. See the [gateway profile](https://github.com/bayleafwalker/sovite/blob/main/docs/plans/2026-11-06-outcome-settlement-gateway.md). |
| Protected resource gateway and target owner | Authorize the typed publication against current policy, artifact and target revision; perform the effect, retain the destination receipt and reconcile ambiguity. The target owner defines publication and rollback semantics. |
| Native harness/workflow provider | Execute the admitted work using its own session, planning and retry facilities. Provider success, cancellation or session IDs do not establish a target effect or work acceptance. |
| Vuoro / Cloud | Compose released owner capabilities and present permitted requests, status, evidence references and next actions. The public coordination surface acquires no effect-apply scope. |
| AgentOps | Define fixtures, capability observations, independent reconstruction, measurement and repeatable operating instructions; retain references to owner evidence. No execution queue, acceptance writer or credential authority. |

Keep three decisions/facts separate: **permission before the effect**, **target
observations after the attempt**, and **work acceptance against its current
contract**. Standing customer policy may authorize and accept automatically.
The performer cannot grant itself authority by writing an approval-shaped record;
an authorized owner evaluator must enforce the actual policy and separation of
roles. Neither a narrator nor a mandatory human review is added to every action.
Work-currentness snapshots remain read-only (`authorizes_effect: false`); a
successful owner read or work CAS is not an atomic authorization of a later
target write. Qualify the target's actual grant/fence and revision boundary,
including the bounded delay between upstream revocation and target enforcement.
An already committed effect is not undone by revocation or cancellation.

Reusing an existing native execution product is the default. The fixture needs a
typed publication operation and owner adapters, not a new scheduler, privileged
shell endpoint, retired ActionQ worker or transcript database. A stable business
operation reference survives attempt replacement. Changing a transport request ID
must not permit another publication of the same unresolved operation; conflicting
intent for the same partition is checked by the target owner. A changed artifact
is a revised intent with fresh evaluation, not a retry of the old authorization.
Keep canonical business intent and expected partition revision distinct from
per-attempt authorization bindings. A successor's new attempt, grant or policy
revision does not change the business deduplication key or inherit permission.

## Freeze a small, independently checkable case

Use synthetic or explicitly permitted lab data. A named source snapshot and
transformation revision produce an immutable candidate for one partition. For
the first case, a disposable PostgreSQL catalog publishes a pointer/version and
its operation journal receipt in one transaction; the candidate bytes remain in
the authorized immutable artifact store. Verify those bytes before publication
and retain them through the declared recovery horizon. A pointer transaction
does not make the object store and work-owner database one atomic system.

Before running, retain these inputs under their existing owners:

- Work/Release revision, business operation reference, current partition revision,
  source snapshot, transformation and candidate digests, and intended postcondition.
- Target installation/incarnation and retained installed-configuration revision;
  an old operation cannot silently follow an alias to a replacement database.
- Actual installed gateway, target adapter, verifier, owner services and harness
  versions; configured roles, operation allowlist, attempt generation, grant expiry
  and revocation checks. Identifiers and credentials remain separate.
- A verifier selected independently of the candidate: exact expected fixture
  output, schema/row constraints, publication digest and generation, and receipt
  correlation. The worker cannot replace the verifier or its acceptance fixture.
- Recovery contract: authoritative journal lookup, consistency/freshness, retention
  covering retry and restore horizons, and a nonreused restore/fencing epoch held
  outside the reverted state. Prove how previously issued authority is fenced
  after restore. Missing or expired evidence is not evidence of no effect.
- Privacy contract: what the hosted caller may see, where artifacts remain, which
  reader may retrieve them and the current output-release decision. Private bytes,
  credentials and raw transcripts are not incidental status fields.
  The initial fixture is C0. Resource-owner v2 currently supports same-class
  output only; redaction, hashing or coarse status cannot silently declassify a
  private result for Cloud. Cross-class release is a separate qualification.
- A baseline using the existing operator/native workflow for the same task and
  acceptance criteria; expected cases, measurement window and thresholds registered
  by the outcome owner before candidate observations.

The normal operator experience is one bounded request followed by an explanation
of accepted, refused or unresolved work. The gateway may decide under commissioned
policy. Intervention is reserved for a named missing authority, failed criterion
or unresolved target fact; repeated confirmation prompts count as operating cost.

## Decisive interruption and recovery

1. Prepare and verify the exact candidate, then authorize its publication under
   current customer policy and the expected target revision.
2. Commit the publication and destination operation receipt. Inject response loss
   **after that target commit and before the caller receives its acknowledgement**.
   Keep independent fault-injection evidence of this boundary.
3. End or replace the originating attempt. Give its successor only an authorized
   handoff and current owner records, with a new attempt identity and its own grant.
   Do not expose the predecessor's private conversation, raw log or credentials.
4. The successor first queries the target's authoritative operation journal and
   current partition state. Correlate operation, artifact and target generation,
   then append the recovered observation to the existing evidence owner.
5. The work owner applies its current acceptance contract. Prove that exactly one
   publication for this business operation occurred within the lab's observed scope,
   and preserve the late predecessor report without letting it settle newer work.

If step 4 cannot establish whether the effect occurred, its result stays unknown.
The next action is the specific target check or owner reconciliation required to
resolve it. A timeout, weak read, missing receipt beyond retention, or target
restore cannot justify blind reapplication. Work acceptance may remain pending
even when the target effect is known; a known effect may also be an unacceptable
business result. Preserve both facts.

## Required fault matrix

Every row starts **not-run**. Freeze inputs and expected owner observations before
execution; store actual results and counterexamples with the owners, not as a new
status table in this plan. Reuse existing conformance fixtures where they exercise
the same boundary, and distinguish synthetic replay from installed execution.

| Case | Observable pass condition |
| --- | --- |
| Ordinary authorized publication | Exact candidate and postcondition pass the installed independent verifier; one destination receipt and a separate owner acceptance are reconstructible. |
| Candidate changes after verification or authorization | Effect boundary rejects the digest mismatch; old permission cannot authorize the new bytes. |
| Partition advances before effect | Expected target revision fails; no overwrite and no inferred permission for the newer state. |
| Expired/revoked grant or replaced attempt reaches effect boundary | The actual writer refuses before mutation under current authority; an advisory reservation alone is not the fence. |
| Agent attempts direct target write | Its credentials cannot write outside the gate for this operation class. Administrative/controller paths remain separate, named authorities. |
| Duplicate delivery / new request ID for unresolved operation | Same business operation reconciles to the original receipt; conflicting intent is refused or explicitly revised by the owner, with no second publication. |
| Commit succeeds, response is lost | Successor recovers the target receipt and state; one publication is observed, no repeat execution, and owner acceptance is based on recovered evidence. |
| Target lookup unavailable, stale or beyond retention | Unknown remains visible with the missing check; no false success, false absence or automatic retry. |
| Target alias rebound or installed configuration changed | Old operations remain bound to the original incarnation/configuration; a replacement's not-found cannot prove absence at the original target. |
| Target or authority state restored from an older snapshot | Restore generation and revocation/fencing recovery prevent old receipts or grants from silently authorizing new writes; reconciliation is required before resuming. |
| Missing child evidence / failed child hidden by parent success | Expected child remains in the denominator; parent prose cannot satisfy the missing or failed criterion. |
| Late predecessor success after replacement | Original attempt and artifact stay attributable; the report cannot overwrite the current Release/Decision or current effect authority. |
| Target effect exists but independent verifier fails | Record the effect and failed verification separately; work remains unaccepted under the frozen criterion. No success is inferred from a receipt alone. |
| Conditional rollback; then rollback after another writer advances state | A separately authorized inverse restores the prior content pointer only while the target still matches this publication, advancing rather than reusing its revision. A later revision causes refusal; original evidence remains and an old precondition cannot become valid again. |
| Replay original publication after rollback | Lookup returns the original publication and subsequent rollback history; it does not republish the old artifact or treat rollback as deletion of the business operation. |
| Observed change without a gate receipt | Classify as external, unattributed or unresolved according to evidence. Claim bypass only when complete scoped observation and writer attribution establish it. |
| Private artifact or status/export destination mismatch | Unauthorized data release fails closed; permitted status remains minimal, and local execution/owner acceptance follows its existing contract. |
| Fresh reader on another host/harness | Permitted note, owner facts and artifact references yield the exact result and next safe action, or a specific missing prerequisite; no private-chat recovery is needed. |

A valid signature establishes the recorded producer and integrity within its
trust assumptions. It cannot replace the target lookup, verifier or acceptance.
Evidence classes remain report, executor receipt, target acknowledgement,
independent observation and acceptance; copying a report into a new envelope
does not upgrade its class.

## Native capability and evidence package

For each actual harness/build and host, record **launch, attach, observe, collect,
cancel and resume separately**, including observed support, limitation or unknown.
The placement matrix's provider documentation is an input, not proof of an enabled
API or subscription entitlement. Native session resume and a new cross-harness
attempt using owner records are different capabilities. If launch is manual, name
that step and measure it; do not claim unattended execution.

Retain one immutable qualification manifest referencing the existing owner
records: case inventory, installed artifacts, policy/verifier revisions, start
state, fault boundary, attempts, candidate digest, target receipt and observation,
work Decision, source coverage, cost/attention evidence and recovery result.
Use the current verification context/result conventions where applicable. This
manifest is an evidence index, not a new acceptance object or canonical transcript.
Sensitive records stay in authorized private storage; public documentation gets
redacted references and bounded conclusions only.

A fresh authorized reader must answer: what was requested; which exact bytes
were checked; who or which policy authorized the action; what the target confirms;
who accepted the result under which criterion; what could not be observed; and
what can safely happen next. Failed runs, absent hooks and inaccessible artifacts
remain in the declared expected-case and source denominators. Complete capture is
claimed only for the named observable scope. A valid chain with an unknown tail
does not establish estate-wide completeness.

## Delivery, measurement and stopping rules

| Stage | Deliverable and exit | What it permits next |
| --- | --- | --- |
| Contract and fixture | Reconcile current owner implementations and work refs; freeze one partition operation, independent oracle, authority/receipt/recovery contract and privacy boundary | Owner implementation and disposable conformance runs; no live capability claim |
| Installed lab qualification | Exact installed artifacts pass the fault matrix; another harness/host reconstructs the interrupted operation from owner records | The named arrangement is qualified for this lab scope, with limitations |
| Useful repeated work | Named consumer uses the same workflow; baseline/candidate expected cases and AO-K02 evidence show outcome value and total operating burden | Prioritization based on real evidence; no automatic grant expansion |
| Transfer | A second operator repeats setup/recovery; a second bounded operation uses the same contracts with principally an adapter change | A deliberate expansion or product-positioning decision with recorded support cost |

Use the existing ExperimentRecord and AO-K02 companion, including separate
internal acceptance, independent correctness and actual use. Record whole-case
operator review, maintenance, re-explanation and recovery time, failed attempts,
escaped defects, elapsed time and known costs. Report token usage separately from
money; subscription, provider, compute/storage and unobserved costs are distinct.
Never convert absent usage into zero cost or exclude failed cases from the cost
of an accepted result. The comparison remains descriptive unless the design
supports a causal claim; task mix, revisions, sample size and capture limitations
must accompany it.

Pause expansion when the first case needs a new general execution engine, requires
private vendor cooperation that the actual native surface cannot supply, or cannot
enforce its scoped effect boundary. If gate use raises total operator burden or
operators routinely bypass the commissioned route, improve the integration or
reassess the case against the baseline. If a second operation requires rebuilding
the core, revisit the contract before widening the adapter catalogue. If retained
outcomes do not inform any routing, review or operational decision, defer further
comparison features. These are decisions about this investment, not automatic
deletion of useful existing capabilities or cancellation of the wider roadmap.

Rollback disables new admission for this operation and restores the prior native
workflow selection. Reconcile every in-flight or unknown operation before any
retry or inverse. A data rollback is a separate conditional operation under
current authority; never overwrite a later writer's result. Keep all original
receipts, failed checks and decisions. Source merged, released, installed,
operationally qualified and accepted outcomes remain separate in every report.
