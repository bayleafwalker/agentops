---
status: active
owner: operator-designated coordinator (default-assigned 2026-11-07)
last_verified: 2026-11-07
---

# Decision index

This page records which decisions are in force and which are superseded. It
covers the agentops target state and its amendments, EC-00, shared dispatch
mechanics, and the standing rulings that sit in dated plans. Where documents
conflict, the order is: operator intent, then accepted decisions and
architecture docs, then implementation. A doc that conflicts with intent is
corrected; intent is never bent to fit the doc. Plan documents and their
statuses are listed in the [plan register](../plans/REGISTER.md).

Status words used here:

| Status | Meaning |
|---|---|
| `in force` | Applies now. |
| `in force (scoped)` | Applies, with an amendment narrowing or extending it. |
| `in force, dormant` | Still applies, but nothing currently invokes it. |
| `superseded` | Replaced; the successor is named. |
| `proposed` | Not accepted yet. |

## Target state ([2026-09-17](../plans/2026-09-17-target-state.md)) and amendments

The target state is a record of where the estate should end up, not of current
behaviour. Each claim carries its own status, and later amendments scope
claims without editing them.

| Amendment | Date | Status | Scope |
|---|---|---|---|
| E1 tripwire replaced by operator direction ("assume use") | 2026-09-22 | in force | The month-long E1 deletion clock is superseded. |
| MI-1 delivery | 2026-10-09 | in force | Retires the GitHub Agentic Workflows comparison requirement for MI-1. |
| [Product direction](../plans/2026-09-17-target-state.md#product-direction-amendment-2026-10-15) (accepted-operator) | 2026-10-15 | in force | Scopes TS-1, TS-2, TS-3, TS-5, TS-6, TS-7, TS-15, TS-16, TS-18, TS-19 and TS-20 (below). |
| [Operated agentic service](../plans/agentops/2026-10-29-operated-agentic-service.md) (accepted-operator, agentops#2866) | 2026-10-29 | in force | Three release layers; the operated vuoro.cloud service; a hybrid first deployment profile. Extends the customer-operated execution and storage boundary (TS-16) and keeps the four portable contract domains and native harness mechanics. |
| [Operator ruling: no retirement for low usage](../plans/2026-09-17-target-state.md#operator-ruling-amendment-2026-11-07) (accepted-operator) | 2026-11-07 | in force | Supersedes TS-12's deletion clause and the "six months with zero hits" tripwire. |

| Claim | Status in file | In force? | Amended by |
|---|---|---|---|
| TS-1 Vuoro owns release, evidence and decision semantics; not a runner, queue, model router or worker supervisor | accepted-delegated | in force (scoped) | 2026-10-15: Sprintctl is the reference work provider; a replacement provider is possible after a documented swap |
| TS-2 Execution, sandboxing and model choice native to the harness | accepted-delegated | in force (scoped) | 2026-10-15; 2026-10-25 shared dispatch mechanics (narrow amendment, below) |
| TS-3 Role and skills observed, not compiled; no skill lock or role preset | accepted-delegated | in force (scoped) | 2026-10-15: recipe/profile revision refs and ExperimentRecord return; observed digests stay observed. The manifest `skill_lock` is now validated as an observed digest record, not a lock, and `role_presets` was removed from `agentops.dispatch.json` (2026-11-07) |
| TS-4 Two hooks carry Vuoro semantics; guard hooks stay | accepted-delegated / proposed (guard hooks) | in force | none |
| TS-5 One Decision object writes terminal status | accepted-delegated | in force | 2026-10-15: protected acceptance stays digest-bound |
| TS-6 Evidence append-only, one home at S4 | accepted-delegated | in force | 2026-10-15: no new auditctl evidence home |
| TS-7 Cost per release is a derived query | accepted-delegated | in force (scoped) | 2026-10-15 (ExperimentRecord) |
| TS-8 Cross-harness continuation through handoff checkpoint | accepted-delegated / proposed (Codex path) | in force | none |
| TS-9 Resumability proven by rehearsal | accepted-delegated | in force | none |
| TS-10 Legacy direct-DSN writers fenced at S5 | accepted-delegated / proposed (interim) | in force | none |
| TS-11 Dispatch manifests are not an authority | accepted-delegated (end) / proposed (retirement point) | in force | 2026-11-07: the manifest stays (no retirement date set); its digests are validated for currency and its routing residue is removed |
| TS-12 Producers measured before adding or retiring contracts; zero-outcome deletion | accepted-delegated | in force (scoped) | **2026-11-07: the deletion clause is superseded.** Dormant tools are recorded `held/dormant` |
| TS-13 Metanarrative and kctl knowledge become Evidence kinds at S4 | proposed | proposed | kctl retired under estate plan EE-07 |
| TS-14 `_projects/*` are derived work folders | proposed | proposed | none |
| TS-15 Harness telemetry is emit-only observation | accepted-delegated | in force (scoped) | 2026-10-15 |
| TS-16 Record covers automated activity everywhere | accepted-operator / proposed | in force (scoped) | 2026-10-15 (no inbound effect path); 2026-10-29 (operated service) |
| TS-17 An accepted result is reconstructible from one derived read | proposed | proposed | none |
| TS-18 Provider results imported as Evidence | proposed | proposed (scoped) | 2026-10-15 |
| TS-19 Authority-plane conformance suite in Vuoro | proposed | proposed (scoped) | 2026-10-15 |
| TS-20 Reconstructable proportion measured by failure class | proposed | proposed (scoped) | 2026-10-15 |

## Standing decisions

| Decision | Date | Status | Supersedes or scopes | Successor |
|---|---|---|---|---|
| [EC-00 estate contract stack ADR](../architecture/2026-10-21-ec00-contract-stack-adr.md): TypeSpec to OpenAPI, tracker vuoro#2734 | 2026-10-21 | in force (architecture selected); EC-00 stays open on its outstanding acceptance conditions. Execution reservation #405 is held by another session (handoffs 2026-11-05 and 2026-11-06) | Supersedes the provisional protobuf lead in the [architecture discovery](../plans/agentops/2026-10-18-estate-contract-architecture-discovery.md) | none |
| [Shared dispatch mechanics and governed execution](2026-10-25-shared-dispatch-mechanics.md) | 2026-10-25 | in force | Narrow amendment to TS-2 and to the shared-dispatcher restriction in the [portable workflows plan](../plans/agentops/2026-10-24-portable-agent-workflows.md); domain authority is unchanged | none |
| [Self-candidate ruling for `mechanical_bulk`](2026-08-26-mechanical-bulk-self-candidate-ruling.md) (agentops#2100, Option C) | 2026-08-26, recorded 2026-11-07 | in force, dormant: no live route reaches the class since hybrid dispatch retired | Moved out of `agentops.dispatch.json` prose | none |
| [Open owner decisions](../plans/agentops/2026-08-26-open-owner-decisions.md) (L-3 / D-8) | 2026-08-26 | in force (record of rulings) | Rules on the [mechanical-bulk boundary analysis](../plans/agentops/2026-08-25-mechanical-bulk-boundary-decision.md) | none |
| [Claims demoted to advisory reservations](../plans/v3-claim-semantics-decision.md) | 2026-07-24 | in force | Supersedes the capability-lease framing of sprintctl claims | sprintctl `docs/plans/v3-reservation-model-plan.md` (engineering source) |
| [Native runtime federation realignment](../plans/agentops/native-runtime-federation-realignment-2026-08-20.md) | 2026-08-20 | in force | Supersedes the post-cockpit waved programme, meta-sprint dispatch, ecosystem simplification and boundary-resolution plans | none |
| Hybrid dispatch retired (S2 item 6; AGENTS.md, [model-routing.md](../dispatch/model-routing.md#worker-routes-retired)) | 2026-09-17 | in force | worker routes; `templates/dispatch` | native harness execution (TS-2) |
| [Active dogfood routing practice](../dispatch/model-routing.md#active-dogfood-practice-2026-11-04) (operator-directed) | 2026-11-04 | in force | none; records are kept in [closeouts](../dispatch/closeouts/README.md) | none |
| Programmes complete at "source accepted"; deployment is a separate gate item ([operator gates](../dispatch/operator-gates/README.md)) | 2026-11-07 | in force | Scopes the 2026-10-24 programmes' completion | none |
| Split-horizon decisions, issue #255 (Q1-Q7: coordination without custody, digest-bound acceptance) | 2026-09-27 | in force | none | tracked items agentops#2533, agentops#2535, agentops#2536 (see [silent-drop check](../plans/silent-drop-check.md)) |
| vuoro-cloud decision log D-001..D-047 | various | owned by vuoro-cloud, `17-DECISION-LOG.md` | none | none |
| [Rejected Opus goal-state plan](../plans/archive/2026-11-07-rejected-opus-goal-state-plan.md) | 2026-11-07 | **rejected** by the operator; retained as source material only, never cited as direction | none | none |
| [`orchestration-meta-planning.md`](/projects/dev/orchestration-meta-planning.md): Restate/Temporal as control plane | 2026-08-21 | source material, not adopted. The Restate/Temporal question is a **deferred option** governed by the target-state TS-2 bulk-work tripwire ("durable execution by DEPEND is the preserved option"), not a rejection; the [L-6 Restate pilot design](../plans/agentops/2026-08-25-l6-d9-restate-pilot-design.md) stays design only | none | none |

## Tool status facts (2026-11-07)

These are facts, not rulings. A tool is listed as retired only where an accepted
document declares it retired. Dormant or held tools stay `held/dormant` whatever
their usage (TS-12 as amended 2026-11-07).

| Tool | Purpose | Status | Basis | Owner |
|---|---|---|---|---|
| kctl | Knowledge review over sprintctl events | retired; historical migration input | estate plan EE-07; agentops README | kctl repo |
| outctl | Bounded command-output capture | retired from active Vuoro scope | 2026-08-20 realignment banner in [ecosystem.md](../ecosystem.md) | outctl repo |
| actionq-dispatcher | Former dispatcher | inactive fail-closed tombstone | its own README; ecosystem.md | actionq-dispatcher repo |
| agent cockpit (apps/web) | Former operator UI | retired 2026-09-16 | ecosystem.md | agentops |
| sprintctl-orchestrator | Orchestration design notes above sprintctl | archived 2026-07-14 | its own README banner | sprintctl-orchestrator repo |
| actionq | Federation state, evidence, acceptance, reconciliation | transitional; the queue stays writable until the W5 privilege fence | realignment 2026-08-20; disposition register | actionq repo |
| auditctl | Repo-local audit ledger | active; conditional S4 import | target state TS-6 | auditctl repo |
| knowledge-base | Markdown education and research corpus | held/dormant; successor store undecided | [silent-drop check](../plans/silent-drop-check.md) | operator-designated coordinator (default-assigned 2026-11-07) |
| sprintctl-bootstrap-template | Reference docs and Makefile repo | held/dormant (its README points to agentops guidance) | its own README | sprintctl-bootstrap-template repo |
| hostproto family (hostproto, -semantics, -dap-core, -dap-debugpy, -dap-delve, -mcp-playwright, -a2a-worker) | Host-interaction semantics and reference adapters | held/dormant (frozen) | adapter READMEs | hostproto repos |
| acceptance-lab | Local acceptance-rule prototype | held/dormant | no disposition recorded | acceptance-lab repo |
| bindery-core, bindery-ra2-adapter | Game platform experiments | held/dormant | their own READMEs (experimental) | bindery repos |
| box | Business-in-a-box scaffold (consumer workload) | held/dormant | no disposition recorded | box repo |
| scribectl | Writing-project contract runner (consumer workload) | held/dormant | no disposition recorded | scribectl repo |
| cred-broker-public | Public extraction of cred-broker | held/dormant; sync not scheduled | no disposition recorded | cred-broker repo owner |
| Jev classifier | Advisory routing classifier | advisory only; did not meet its preregistered adoption rule | model-routing.md | agentops |
