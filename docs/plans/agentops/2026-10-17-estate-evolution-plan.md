# Estate evolution: project delivery and operating plan

Status: accepted planning scope from the operator's 2026-10-17 instruction:
“Don't formalise the planning horizons. Land all work including ‘Later,
conditional on demand’ into project plans.”

This plan replaces the calendar buckets and open-ended “later” disposition in
the October 17 estate assessment. All outcomes below belong to the project
plans now. Dependencies determine sequence; there are no delivery dates,
time-box commitments, or demand-dependent admission to the backlog. Demand,
cost and operating burden are work to measure and use in design decisions.

The [accepted target state](../2026-09-17-target-state.md) and
[October 15 product direction](https://github.com/bayleafwalker/vuoro/blob/main/docs/direction/2026-10-15-product-direction.md)
continue to own the product and trust boundaries. This is their delivery
amendment, not a new runtime, queue or writable work-state authority. IDs in
this document identify plan entries, not fabricated Sprintctl items. Sprintctl
remains the work-item authority; implementations should bind these references
to existing owner items before creating duplicates.

## Intended result

One operator or team can carry a purpose across agents, sessions and machines,
retain exact artifacts and authority history, reconcile interrupted effects,
and reconstruct an accepted result without the original conversation. The
household estate remains useful and recoverable with declining operator
effort. Domain projects keep their own purposes and state ownership.

Vuoro builds portable work identity, graded evidence, authority/delegation and
learning contracts. Existing products provide execution, identity, secrets,
telemetry, Git and deployment. Native harnesses execute. Protected-side
consumers evaluate current authority before effects. A public proposal cannot
grant its own execution authority.

## Owning project plans

| Owner | Delivery plan | Responsibility |
| --- | --- | --- |
| Vuoro | [Product delivery](https://github.com/bayleafwalker/vuoro/blob/main/docs/plans/2026-10-17-product-delivery-plan.md) | Reference workflow; portable contracts; knowledge/artifacts; qualification, learning and supported product |
| Vuoro Cloud | [Product distribution](https://github.com/bayleafwalker/vuoro-cloud/blob/main/20-PRODUCT-DISTRIBUTION-PLAN.md) | Hosted composition, onboarding, release/rollback, distribution, support, and tenant/cross-organization design and qualification |
| Appservice | [Platform evolution](https://github.com/bayleafwalker/appservice/blob/main/docs/plans/2026-10-17-platform-evolution-plan.md) | Service truth, deployed compatibility, data recovery, guardrails, storage, safe upgrades and operating effort |
| NixOS estate | [Platform evolution](https://github.com/bayleafwalker/gitops-nixos/blob/main/docs/plans/2026-10-17-platform-evolution-plan.md) | Current host identity/trust, isolated execution, backup-host recovery and reproducible host operations |
| Datacluster | [Platform evolution](https://github.com/bayleafwalker/datacluster/blob/main/docs/plans/2026-10-17-platform-evolution-plan.md) | Actual cloud ownership/resources/access, reproducibility, cost and useful data workload |
| Homelab Analytics | [Household outcome plan](https://github.com/bayleafwalker/homelab-analytics/blob/main/docs/plans/household-outcome-evidence-decision-plan.md) | Source quality → decision → realized household result; reporting and authorization |
| Bindery | [Post-RA2 hardening](https://github.com/bayleafwalker/bindery-core/blob/main/docs/roadmap/post-ra2-hardening.yaml) | Repeatable external-runtime/game proof and honest capture boundaries |
| Frontier Weave | [Core gameplay enablement](https://github.com/bayleafwalker/frontier-weave/blob/main/docs/roadmaps/core-gameplay-enablement.md) | Physical comfort evidence and smallest asymmetric co-op slice |
| Aligned Equity | [Finnish evidence and decision impact](https://github.com/bayleafwalker/aligned-equity/blob/main/docs/plans/finland-first-useful-evidence-and-decision-impact.md) | First decision-useful evidence spine before integration growth |

## Cross-project delivery ledger

All rows are planned. A prerequisite is a concrete result to obtain, not a
calendar horizon or permission inferred from metrics. Close an entry only with
the referenced owner result and its evidence, or an explicit superseding
decision that preserves the requirement it resolves.

| ID | Result and lead owner | Prerequisites | Acceptance |
| --- | --- | --- | --- |
| EE-01 | Current service/host/resource register — Appservice, NixOS, Datacluster | None | For every relevant service: owner, purpose, configuration source/branch, observed revision and time, audience/exposure, data class, dependencies, recovery path and unresolved unknowns. Actual usage is distinguished from configured presence. |
| EE-02 | Reconciled runtime and release composition — Appservice + Cloud | EE-01 | Observed service image, catalog, database schema, identity revision and Cloud hold reasons match or explicitly differ from desired state; compatibility and exact shipped artifacts are recorded. A source pin does not count as rollout evidence. |
| EE-03 | Whole-application recovery and data safety — Appservice + NixOS | EE-01 | Named RPO/RTO, isolated file-plus-database restore, recovery-only credential path, offsite/retention and object cleanup verification, host rebuild time and evidence freshness are recorded. Provider concentration is a deliberate recovery decision. |
| EE-04 | Current, safe operating guidance — platform owners | EE-01 | Superseded workstation migration, telemetry absence and conflicting cloud snapshots are marked as history; current entry points resolve. Completed work is not restarted from stale plans. |
| EE-05 | Safe change and retirement qualification — Appservice + ActionQ + NixOS | EE-01, EE-02 | Upgrade canary/rollback and policy refusal cases are evidenced; ActionQ W5 database privilege fence and any remaining deployed callers are verified; retained historical DBs have a distinct read-only purpose; object deletion is followed by runtime/orphan checks. |
| EE-06 | Repeatable hosted → native → protected publication — Vuoro | EE-02 | A new attempt continues a named task; stale reports cannot settle; exact digest/current authority bind the effect; interrupted publication reconciles without duplication; a fresh reader reconstructs the result without private chat context. |
| EE-07 | Durable knowledge/artifact workflow — Vuoro workspace + vuoro-knowledge | EE-06 contract fixtures; storage/access design can proceed independently | Original bytes and immutable revisions, cited proposals, policy-controlled human publication, stale-write protection, deletion/restore, index rebuild and export/import are qualified. Git hosting and a separate knowledge-product decision are evaluated against a real user need. Kctl is historical migration input only; retirement does not admit new Kctl operations. |
| EE-08 | Authority/delegation and autonomy boundaries — Vuoro + cred-broker | Reference workflow authority model | Principal/attempt/grant/decision relationships, revocation, bounded credentials, independent acceptance and effect reconciliation pass positive and refusal cases. Observed success never silently expands a grant. |
| EE-09 | Evidence, capture and historical import — Vuoro + Auditctl + telemetry owners | EE-06 evidence contract | Agent reports, receipts, target acknowledgements, independent observations and acceptance remain distinct. Coverage has a denominator; missing attribution remains unknown. S4 historical import is verified before moving authority; telemetry is non-authoritative and failure does not block unrelated work. |
| EE-10 | Supplier replacement and portability — Vuoro + HostProto owners | EE-06, EE-08, EE-09 | One provisioned row is actually replaced; work identity, original artifacts, versions, decisions and evidence survive. A fresh participant continues after export/import without hidden session state. Capability/conformance limits are explicit. |
| EE-11 | Independent-user workflow qualification — Vuoro + Cloud | EE-06–EE-10 and applicable recovery checks | Someone besides the operator completes setup, work, review and recovery using documented boundaries; onboarding failures, support effort, capture limits and costs are recorded. This includes self-hosted/customer-controlled protected execution. |
| EE-12 | Supported reference distribution — Vuoro + Cloud | Composition design can proceed now; qualification uses EE-02, EE-03, EE-10, EE-11 | Installation, supported versions, upgrades/migrations, rollback, export, support boundary, diagnostics and lifecycle policy are shipped and exercised. This is planned product work, not an option awaiting a future demand trigger. |
| EE-13 | Onboarding, coherent UX and documentation — Cloud + Agentops | EE-06 reference flow; existing UX/doc plans | One entry path explains work, review, evidence, authority, recovery and provider capabilities across terminal/web. Fresh users complete the flow; documentation follows the shipped composition and avoids duplicate operator surfaces. |
| EE-14 | Tenant and cross-organization product evolution — Cloud + Vuoro | Existing trusted/protected-boundary designs; deployment qualification depends on EE-08, EE-11, EE-12 | Design responsibilities, tenant isolation, enrollment/revocation, delegated authority, data separation, billing/support and recovery are explicit; isolation/refusal/rollback proofs precede exposure. Prior implementation deferral becomes planned design + qualification work, not automatic runtime activation. |
| EE-15 | Supplier sourcing and workload identity decisions — Vuoro | Concrete reference-composition requirements | Resolve policy evaluator and identity/attestation choices through capability, enforcement, cost and failure evidence; configure selected products or record a justified no-component decision. Avoid adding parallel authority or a universal execution runtime. |
| EE-16 | Learning and sustained commitments — Vuoro | EE-07–EE-09 and accepted outcome records | Experiment records relate recipe/profile changes to accepted outcomes, uncertainty, cost and review effort. Longer-lived commitments and maintained knowledge expose freshness, downstream consequences and re-evaluation responsibilities without claiming unsupported causal attribution. |
| EE-17 | Household decision outcome — Homelab Analytics | Source-quality and domain acceptance contract | A chosen energy/cost/reliability question produces a traceable recommendation and measured realized result; missing/freshness/estimation limits are visible. Household data and outcome authority stay in HLA. |
| EE-18 | Domain identity and battery-input reliability — HLA + ha-elisa-kotiakku | EE-17 requirements and existing provider access | Source/tariff snapshots, billing-estimate limits and integration maintenance are tested; local bootstrap and future OIDC/break-glass boundaries are explicit. Read-only battery measurement does not become unauthorized actuation. |
| EE-19 | Bindery / RA2 field proof — Bindery and adapter/protocol owners | Existing ERH-001–005 results | ERH-006 repeats through durable identities, real Windows/spawner acceptance and reconstructable capture. Retail gameplay, simulator/fake clients, broker observations and agent reports are separated. |
| EE-20 | Frontier Weave playable result — Frontier Weave | Existing FW-0101 observation gate | Physical-device/comfort evidence precedes the smallest asymmetric co-op slice; the slice demonstrates consequential interaction/persistence rather than only networking scaffolding. |
| EE-21 | First useful Finnish company evidence — Aligned Equity | Evidence/source inventory and existing spine contracts | A sourced Finland-first dataset supports one explainable decision view; provenance, uncertainty, rights and freshness are explicit; decision impact is evaluated before expanding integrations. |
| EE-22 | Smaller tools and bounded experiments — listed owners below | Named outcome per tool | Each tool receives a concrete maintenance, qualification, integration or closure result. No project is merely left “parked” without its next decision and acceptance. |
| EE-23 | Cost, demand and operator effort — all owners, coordinated here | Baseline definitions; measurements accompany each result | Time to accepted outcome, admin/recovery/re-explanation effort, actual provider/storage/egress cost, independent usage and support burden have denominators and unknowns. Findings adjust scope and sourcing without silently granting authority or removing planned distribution work. |

## Smaller-tool and experiment project entries (EE-22)

These entries are the cross-project plan for associated tools; implementation
remains with their repositories. They are not a new writable tracker.

| Entry | Owner | Planned work and acceptance |
| --- | --- | --- |
| EE-22a | Scribectl | Qualify the vault-writing loop, frozen context packs, append-only records, recovery and human canon ratification on a representative writing project. Preserve its distinct creative purpose; model dispatch must not auto-ratify canon or rewrite unrelated human notes. |
| EE-22b | CV Studio | Exercise a nontechnical user's complete edit/export flow; verify local-only processing and privacy, accessibility and import/export compatibility; maintain release/dependency quality. Public UI publication is not authorization to upload CV data. |
| EE-22c | kotona.app / Operator's Atlas / project guides | Reconcile source and published revisions, update project status from evidence, and provide a coherent public entry path. Keep explanatory demos distinct from qualified operational capability. Maintain domain/mail-policy configuration through its existing owner. |
| EE-22d | HostProto adapters / Browser Workbench | Select a real workflow need, publish capability declarations, and qualify native browser/debugger/agent behavior on the named host/toolchain. Unsupported or experimental backends remain explicit. Conformance integrates with EE-10 rather than becoming a generic coordinator. |
| EE-22e | Acceptance Lab / Counterfactual Ops | Apply one acceptance/uncertainty method to a Vuoro or HLA outcome, compare the resulting decision value and burden, and adopt, integrate or close overlapping surfaces. Preserve the experiment-only boundary; no production scheduler/credential authority is inferred. |
| EE-22f | FlowLab | Complete or explicitly close its measurement campaign. Preserve the three-session result as unmeasurable against its ten-session gate; collect eligible observations or record why the question is closed. Finish with an evidence-backed adopt/integrate/retire decision. |
| EE-22g | Box / templates / fleet composition | Identify the concrete workload or consumer each scaffold serves, establish ownership and actual reconciliation, and prove one reproducible use. Decide reuse, merge or retirement where foundations duplicate existing products. Template presence is not deployed evidence. |
| EE-22h | Rack-parts | Validate a physical print/fit/use case and publish any required part/tolerance revision and assembly guidance. Preserve the stable design when measurement calls for no change. |
| EE-22i | q-spec / unused pilots | Resolve purpose and current content; bind any useful requirement to an existing owner or explicitly close the empty/unused project. Do not invent implementation scope to keep an empty repository busy. |
| EE-22j | Retired cockpit, dispatcher and Outctl lineage | Verify callers/runtime residue, preserve necessary migration/recovery references and remove stale required-dependency guidance. Retired implementations do not become new product requirements. |

Unrelated personal archives and exercises remain outside the delivery scope.
Their appearance in an inventory does not create a requirement to publish or
inspect their contents.

## Execution and completion rules

Source pickup on 2026-10-17 is recorded in the
[owner-register architecture and qualification handoff](../../architecture/2026-10-17-estate-evidence-delivery.md).
The [full-roadmap source progress and qualification map](../../architecture/2026-10-17-estate-roadmap-source-progress.md)
continues that work across product, platform, household, creative and smaller-tool
entries. Ready source PRs may merge under the operator's instruction; actual
deployment is excluded. Source tests, released artifacts, deployment, externally
measured qualification and owner acceptance remain distinct. No estate outcome
is closed solely by this source delivery.

- Use the owning plan's IDs and existing work items. Record a dependency edge
  instead of copying state or opening another writable queue.
- Design/documentation work can proceed before runtime qualification. Exposure,
  data migration and effect execution depend on their concrete owner checks.
- Use current source and dated observations. Distinguish desired, observed,
  claimed, tested and accepted; never close a live gap with a README statement.
- Do not restart completed encrypted-workstation conversion or initial Langfuse
  deployment. Qualify present behavior and supersede stale guidance.
- Keep one coherent user outcome through the dependency chain. Measure operating
  effort and consolidate duplicate surfaces rather than adding management layers.
- Record completion evidence and update the owner plan/index. The report is an
  assessment snapshot; repository plans and owner state are the living work.
