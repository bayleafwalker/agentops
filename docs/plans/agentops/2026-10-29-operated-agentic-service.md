---
doc_id: vuoro-operated-agentic-service-2026-10-29
status: accepted-operator-implementation
effective: 2026-10-29
work_ref: agentops#2866
---

# Operated agentic service: accepted target and implementation programme

The operator accepted the Vuoro Agentic Service Architecture v1 and its review
on 29 October 2026, then directed extended implementation in parallel using
native Luna, Terra and OpenCode DeepSeek Flash sessions. This Git record carries
the governing decisions. The supplied 23-page PDF has SHA256
`7b28b8aef07ae215aa88b8caf0e95b87b596000e5c6c84caa67437caeebea84c`.
The hash identifies the source; the decisions below stand on their own.

## Product and operating decisions

Vuoro has three release layers: independently useful components, a qualified
distribution of components and workflow packages, and the operated vuoro.cloud
service. Cloud takes responsibility for commissioning complete supported
workflows, managed environment and artifact lifecycle, recovery, diagnosis and
support. Success is an accepted useful outcome or a preserved, actionable
stopping point with an exact continuation basis.

The first deployment profile is hybrid: an external hosted substrate, separate
managed execution infrastructure, and a resource-owner-controlled gateway for
named private resources. The self-hosted reference remains a target. Candidate
code does not run alongside public control services. Customer private resource
authority does not transfer to Cloud. These decisions extend the earlier
customer-operated execution/storage boundary; they retain the four portable
contract domains, supplier provisioning, native harness mechanics and narrow
domain ownership.

The first managed backend uses ordinary isolated VMs with pinned environment
definitions. Workbench, task, acceptance and preview are distinct purposes with
different state, network, credential and retention rules. A workspace VM alone
does not isolate attempts or reviewers. Select a concrete immutable VM image and
provider configuration before installation; no backend becomes qualified by
being listed here. Provisioning source may be built before billable resources
are commissioned.

The gateway target is an independently recoverable infrastructure VM with no
application-cluster bootstrap, DNS, journal or credential-recovery dependency.
Verify those dependencies under an application-cluster outage; a separate VM
name alone establishes no independent failure domain. The initial catalog is
cluster observation, one named LAN API and one approved disposable lab template.
Broader protocol proxying follows operation-specific qualification.

Routine operation uses commissioned capabilities and standing authorization.
Administration changes enrollment, trust, policy, infrastructure or recovery
authority in a separate identity/session/credential/network lane. No new
universal human confirmation gate is introduced. Existing release signing and
resource-owner admission requirements continue at their actual boundaries.

## Ownership and implementation boundaries

| Owner | Responsibility |
| --- | --- |
| Sprintctl | Work identity, current basis, requirements, evidence and settlement. |
| Sovite | Admitted bindings, execution attempts, leases, fences, cancellation and execution-owner receipts. |
| Native harness | Agent/session loop, tools, provider process and native resume. |
| AgentOps project adapter | Repository-delivery consumer using shared scheduling/process mechanics; project eligibility, trusted acceptance, bounded repair and integration hooks. |
| Vuoro | Portable contracts, released composition, distribution manifest, owner-backed views and qualification correlation. |
| Workspace / knowledge resolver | Artifact/knowledge lifecycle and exact authorized source resolution; Git remains repository-document authority. |
| Protected resource executor | Local admission, durable operation identity, target invocation and reconciliation. Extend the existing protected executor before creating a new journal. |
| Credential broker | Scoped credential mediation; it does not become work, execution or resource-effect authority. |
| Cloud | Tenant-scoped service experience, isolated execution provisioning, storage, lifecycle, support and operated qualification. |
| Infrastructure owners | Worker/gateway placement, enforced network/isolation, backups and independent administration. |

The gateway is an execution boundary, not an account tunnel or second work
ledger. Use typed catalog operations, local current policy, exact content and
stable operation identities. Existing protected-runtime journal and currentness
contracts are the reuse starting point; new target adapters must prove their
own reconciliation. A signature, work acceptance, reservation or model response
cannot supply local resource authority. Unknown effects are reconciled before
retry. Target-specific ambiguity remains visible where fencing is unavailable.

The complete source-to-tool-to-model-to-session-to-artifact-to-telemetry path
must satisfy the selected data profile. Restricted output is released before
entering an external model context. Exact content release and current reader
authority are distinct. Import preserves authority history but creates no live
credentials, memberships or executable grants at the destination.

## Delivery sequence and existing work

Planning IDs here are not a second writable queue. Served Sprintctl owns work
state. AS-00 is agentops#2866; Sovite execution foundations extend agentops#2850.
Portable programme PW-01 through PW-08 and Cloud's distribution, capability and
dispatch-console plans retain their existing ownership. A new source slice is
recorded under AS-00 unless an existing owner item is the more precise match.

| Stage | Concrete delivery | Exit evidence |
| --- | --- | --- |
| D0 | Ratified scope, current source/release/installed tuple, owner APIs, first backend and gateway contract. | Per-field evidence/freshness; unknowns remain unknown; exact supported operation contracts. |
| D1 | Provider-managed environment publication and real editing route, retained candidates, authenticated browser/native attachment. | Fresh-browser task and worker replacement without lost candidate; tenant/sibling denial and source/current binding checks. |
| D2 | Outbound resource-owner gateway, scoped cluster read, one LAN API and approved lab. | Allowed operations, denied escape/admin/foreign tenant, restart and response-loss reconciliation. |
| D3 | AgentOps-owned repository workflow consumer, current context, clean trusted verification, bounded repair and integration. | Exact accepted/tested/landed identities; stale predecessor cannot settle or continue resource use. |
| D4 | Combined recovery, restore, revocation, uncertain effects and second-tenant adversarial qualification. | No duplicate effects or revived authority; independently reconstructible records and declared residual ambiguity. |
| D5 | Research/operations profiles, independent export/continuation, external onboarding, support and cost limits. | Same released composition passes lifecycle and user workflows with measured burden and denominators. |

Recovery and isolation tests accompany D1 and D2; D4 proves the combination.
Independent source work can proceed concurrently. Each consumer pins released
owner contracts before installation. Source changes do not prove release,
deployment, physical isolation, real provider authentication or user acceptance.

### Reconciled owner work

Read-only served reconciliation on 29 October found these existing homes for
the remaining delivery. These are references to authoritative work, not a second
queue or a claim that an item is ready. Preserve the owners' current dependency,
requirement and acceptance basis when selecting work.

| Stage | Existing owner work and refinement |
| --- | --- |
| D0 | `agentops#2866` owns this source architecture and foundation batch. Fresh runtime observations and their unknowns are recorded in its served evidence. |
| D1 | `vuoro-cloud#2683`, `#2684` and `#2741` retain composition, enrollment/lifecycle and hosted proof. New `gitops-nixos#2867` owns the previously missing guest image/host commissioning scope; local packet and KVM evidence is only a foundation. Consume `agentops#2850` for Sovite execution ownership. |
| D2 | New `agentops#2869` owns the resource gateway implementation across Sovite adapters and the existing protected-executor contract. Cloud `#2682`, `#2683` and `#2684` retain operated enrollment/composition and owner-accountable proof. The source pod-read seam does not close this stage. Existing AgentOps `#2646`, `#2601` and `#2555` retain tenant traffic, resource-prefix and provisioning-role work. |
| D3 | New `agentops#2868` owns the actual repository-delivery consumer. `agentops#2864` retains implementation-programme coordination; `#2692`, `#2730` and `#2726` retain end-to-end proof and owner-action publication. Current-context contracts remain with `sprintctl#2738` and Vuoro `#2725`, `#2728`, `#2734`, `#2735`, `#2737`. The offline fixture supplies no live acceptance. |
| D4 | AgentOps `#2599`, `#2630`, `#2850`, Vuoro `#2673` and Sprintctl `#1234` retain backup/restore, exit/recovery, execution fences, exact-source/export and atomic recovery work. Combined qualification remains in the end-state demonstration `agentops#2692`. |
| D5 | AgentOps `#2484`, Sprintctl `#2127`, Cloud `#2684`, Vuoro `#2678` and AgentOps `#2692` retain cross-harness departure, external onboarding, support/incident policy, spend characterization and independent-user measures. |

The portable programme's PW-02 host commissioning is now explicitly bound to
`gitops-nixos#2867`. The survey also found no specific actual delivery-consumer
or gateway-implementation item; `agentops#2868` and `#2869` now fill those gaps
without replacing the existing programmes. AgentOps `#2733`, `#2736` and `#2742` remain inventory,
contract-toolchain and runtime-integration inputs; they are not substitute guest
commissioning items. Some historical numeric dependency references did not
resolve in the named owner scope during the survey. Reconcile those through
current owner reads instead of treating them as verified blockers or bypassing
them. Append-only refinement notes were recorded on Cloud `#2682`–`#2684`.

### Foundation evidence and its limits

The repository-delivery fixture uses real local Git, exact committed bytes and
clean verification, with a simulated owner. Sovite source now binds execution
to the admitted grant/class/mirror/profile and bounds advertised readiness by
current owner and qualification deadlines. Its resource read seam permits only
a catalog-resolved HTTPS pod observation with current exact-byte output release.
Neither installs a production mutable host or resource gateway.

The disabled guest egress module has two complementary local proofs. Disposable
user/network namespaces on kernel `6.18.58` exercised new and established flows;
four deliberately weakened policies failed their intended checks. A separate
two-guest KVM test on kernel `6.18.59` exercised the booted nftables service,
nonroot candidate probes, positive reachability controls and service restoration.
Both bind module SHA256
`e5af5129e0fe390abe8611b244786d6c2b7f915fab106578af5904614418c822`.
The namespace source-rules serialization hashes to
`4134716d28190f17c8e78ddf50866d24b20add05ed705bdd4b4f265eff6781e7`;
the VM's normalized stateless nft table hashes to
`af75feb71b17b0b646994eb9f912ccdc4be992f24645a21f8a42a51bfd60c0b2`.
These are different representations and test placements. The VM proof does not
cover IPv6 packets; the namespace proof does. Neither qualifies a provider image,
private resource gateway, model account, live workflow, tenant restore or service.

Committed source and PR evidence are cross-host-replicated. Served work records
are durable-authoritative. Local Nix build logs are host-persistent and subject
to garbage collection; temporary transcripts and namespace receipts are
session-local. Preserve required qualification evidence under the release and
evidence owners before using it for a supported service claim.

## First integrated service demonstration

1. Start from a fresh browser without a personal workstation dependency.
2. Commission a workspace and run one small real repository task through the
   declared execution/data/billing profile.
3. Use the gateway for a scoped cluster or LAN observation.
4. Retain the candidate, interrupt the worker and reconcile its operation.
5. Continue on a fresh eligible successor; retain and refuse stale predecessor
   settlement and further resource operations.
6. Verify exact content in a clean acceptance environment using a trusted basis
   outside the candidate's writable scope; integrate under current authority.
7. Reconstruct objective, source, actors, decisions, effect status, verification
   and acceptance without predecessor chat.

A second synthetic tenant attacks the same work, source, artifact, cache,
gateway, notification, support, export and restore paths from the first usable
composition. Provider quotas and aggregate budgets remain explicit and bounded;
unknown usage is not zero. Offline fixture owners are labeled as simulated and
cannot establish service qualification. Measure all eligible cases, including
failed, rejected, interrupted and missing-observation cases.

## Release and qualification

Extend `vuoro/deploy/reference-distribution.toml`; do not create a competing
release registry. Each supported function binds exact component API/schema,
immutable installed composition, workflow revision and environment profile.
The current distribution remains a source-only candidate until its same-release
installation, migration, rollback/forward recovery, restore, export, removal,
isolation and support evidence passes. Cloud mirrors composition pins rather
than choosing independently newer adapters.

No infrastructure mutation, external onboarding or support claim follows from
this planning record alone. Authorized implementation continues through source,
review and CI-gated canonical landing; actual commissioning uses the existing
owner procedures and records observed effects separately.
