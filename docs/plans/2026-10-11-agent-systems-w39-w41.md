# Agent systems W39–W41: Vuoro Cloud and ecosystem adoption

Status: proposed adoption plan, 2026-10-11; requested planning and backlog
intake, not implementation or deployment approval. The supplied W39–W41
reports are inputs, not implementation evidence. Served sprintctl owns item
state; the mapping below is a dated projection of backlog intake.

## Recommendation and ownership

Keep the build boundary: adopt harness capabilities and established protocols;
own durable work semantics, application authority, acceptance and evidence.
This develops TS-1/2/3/5/8/15/16/18 without changing their status. It creates
no Cloud execution service, model router, compiled profile, approval gate,
delegation-token protocol or replacement for retired ActionQ/outctl.

| Destination | Roll in | Owner and boundary |
|---|---|---|
| Vuoro Cloud | Dated MCP compatibility, current access explanations, principal lifecycle, portable onboarding packages | Cloud composes released capabilities; domain authority stays in sprintctl/Vuoro. Execution and customer credentials stay outside Cloud. |
| Vuoro domain/contracts | Session-independent work identity; provider workflow outcomes as observations; exact-artifact acceptance | Extend existing continuation and evidence contracts. Provider success never writes authoritative completion. |
| Local agent ecosystem | Measured advisory routing, adoptable Linux containment, explicit permission settings and denial tests | agentops coordinates; native harness/host configuration owns execution. No production rollout from these investigations. |
| Skills/onboarding | Provenance and content integrity separate from execution permission | agentops owns skill content and observations; host policy grants execution. Cloud distribution grants no new tool authority. |
| Analytics | Linked work, policy, evidence and telemetry identifiers | Existing owner queries and OTLP ingestion; no telemetry-derived acceptance or authoritative accounting. |

Fit check: Cloud's product outcome is keeping work resumable and explaining
which result counts. These changes improve that proof and onboarding, rather
than adding execution to the hosting composition. Read alongside
[target state](2026-09-17-target-state.md),
[split-horizon architecture](../architecture/2026-09-27-agentic-ecosystem-and-split-horizon.md),
[Cloud enablement](2026-09-26-cloud-enablement-plan.md), and
[native skill observation coverage](2026-10-10-native-skill-observation-coverage.md).
Cloud's `00-EXECUTIVE-DECISION.md` and `19-PRODUCT-POSITIONING-AND-PROOF.md`
remain the product intention records; this public plan carries no private
Cloud source, workspace inventory or operational receipts.

## Evidence check and limits

Primary pages checked on 2026-10-11:

| Report signal | Verified basis | Planning consequence |
|---|---|---|
| Cheap typed judgments | [Decisions guide](https://developers.openai.com/api/docs/guides/decisions) documents beta predicate/choice/score judgments, calibration and input-only pricing | Measure actual routing quality, latency and cost; vendor performance is not our benchmark. |
| Managed harness adoption | [Agents API overview](https://developers.openai.com/api/docs/guides/agents-api/overview) describes managed execution capabilities | Prefer native capabilities. The fetched [SDK overview](https://developers.openai.com/api/docs/guides/agents/sdk) still guides SDK development; it did **not** establish W39's feature-freeze/no-major-features claim. Do not plan an SDK migration on that claim. |
| Containment packaging | [Microsoft announcement](https://blogs.windows.com/windowsdeveloper/2026/10/07/microsoft-execution-containers-policy-driven-containment-for-ai-agents/) describes GA MXC and externally enforced policy | Qualify Linux behavior against existing controls. Entra attribution/Intune controls are described as upcoming, not available acceptance dependencies. |
| Managed workflows | [Claude workflow runs](https://platform.claude.com/docs/en/managed-agents/workflow-runs) documents background programs and completion that can include failed workers | Runtime completion is evidence only; interruption, missing results and uninspectable plans remain explicit unknowns. |
| Browser authentication | [Agents computer use](https://developers.openai.com/api/docs/guides/agents-api/tools/computer-use) separates sign-in input from model input/history | Use as a broker design reference with fake credentials; do not infer that authenticated cookies or all downstream browser content are secret-free. |
| Portable skills | [MCP Skills overview](https://skills.extensions.modelcontextprotocol.io/) and [official SDK host responsibilities](https://py.sdk.modelcontextprotocol.io/advanced/skills/) distinguish integrity, provenance and permission | Authentic distribution does not authorize execution; verify dependencies as well as SKILL.md. |
| Capability packaging | [Agents plugins](https://developers.openai.com/api/docs/guides/agents-api/tools/plugins) packages skills and MCP configuration | Adapt to native vendor packages; do not make a vendor manifest the enterprise authority model. |
| External agent boundary | [Official A2A CLI](https://a2a-protocol.org/latest/blog/2026/10/01/introducing-a2a-cli/) provides discovery and task interaction | Evaluate A2A first at a real independent agent-service boundary; no pilot without that boundary. |
| MCP rollout | [2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28) is published | Test actual client/server builds and negotiated versions; a final spec does not prove peer migration. |
| MCP Events | [SEP-3415](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3415) is an open proposal | Watch only; no event gateway or durable dispatch replacement. |

The remaining report-specific release dates, incident details, Google product
availability, WIMSE draft semantics and exact reference-server migration counts
were not independently qualified in this intake. They motivate questions, not
claims of availability or local defects. Maturity labels are report assessments,
not conformance results. Recheck versions, account access, pricing and retention
terms before any actual adoption.

## Standing design rules to carry into reviews

1. **Session is not work.** A durable work ID and revision survive new sessions,
   provider runs, host changes and harness replacement. A provider workflow/run
   ID is a namespaced reference to an attempt, not work ownership, acceptance or
   effect identity. Reuse current lease/reservation semantics from the owner;
   do not infer execution authority from either. Late detached results keep
   their originating attempt and cannot settle superseded work.
2. **Adopt cognitive orchestration.** Compaction, within-run scheduling,
   steering and recovery belong to the native harness. External retries,
   ownership, accepted results and effects remain owner records. A workflow's
   `completed` outcome can coexist with failed workers and rejected acceptance.
3. **A2A first at independent agent boundaries.** If a component is independently
   deployed and opaque, evaluate A2A discovery, task semantics, supported
   transports and black-box CLI/conformance testing before custom RPC. Record
   an exception when requirements demand another interface. Keep internal
   subagents on native harness interfaces and tools on MCP. Agent Cards and
   task completion neither grant authority nor accept a business result.
4. **Distribution is not execution authority.** Origin, bytes, digest and trust
   classification are observable facts. The execution policy is a separate
   host decision. Remote skill text is untrusted, including permission-widening
   frontmatter. Packaging observes actual content; TS-3 still forbids a compiled
   role/profile or skill lock.
5. **Pin policy behavior explicitly.** Permission mode, filesystem boundaries,
   network policy, tool allowlist and credential policy are explicit host
   settings. Exercise denial after upgrades; inspect resolved settings as well
   as actual effects. Observe settings digests in Vuoro rather than managing
   the runtime from it.
6. **Preserve separate truth.** OTel observes execution; owner records assert
   work lifecycle and cost accounting; policy receipts assert authorization;
   accepted evidence reconstructs the result. Link IDs and revisions, retain
   missing markers, and never promote a trace or a model prediction to authority.
   Delegation representation stays replaceable while ordinary identity and
   deterministic policy remain the current mechanism.

## Bounded new investigations

Each ends in a source-backed recommendation and inspectable evidence. None
requires a new long-lived service. Coordinate in sprint 562's ecosystem track;
implementation remains with the named owner. P denotes native sprintctl priority
(1 highest). Live deployment, protected effects and paid experiments are outside
this intake. Existing local Claude Max/no-paid-Anthropic-comparison constraints
remain; an API benchmark arm requires independently authorized budget/access.

### W41-R1 — Advisory decision-routing comparison (P3)

Owner: agentops, native harness routing only. Freeze 40–60 de-identified real
dispatch cases with labeled lanes, escalation reasons and rubric revision.
Separate calibration from held-out evaluation. Compare deterministic rules,
an already permitted inexpensive model, and Decisions API only where budget
and account use are authorized. Missing API access is an unmeasured arm, not
a reason to substitute another model silently.

Record confusion matrix, false escalations, unsafe under-escalations,
abstention/coverage, p50/p95 latency, actual billed cost and operator correction
effort. Predeclare the baseline, acceptable error bounds and material savings
before looking at held-out results. A 40–60-case sample supports a bounded
decision, not general reliability. Timeout/malformed/uncertain predictions fall
back to existing rules or review, never to broader privileges. Accept adoption
only for measured benefit within those bounds; otherwise retain the baseline.
No classifier writes authority or selects models inside Vuoro. Reuse #2487's
experiment format where available without blocking this on a new eval platform.

### W41-R2 — Linux containment comparison (P3)

Owner: agentops qualification; host changes belong to gitops-nixos/appservice
where applicable. Compare current native sandbox controls with MXC or an
equivalent existing backend using one disposable repository and fake credential
files. Keep policy outside worker-writable paths. Record backend, OS/build,
effective policy and which properties are actually enforced.

Positive case: edit allowed repository and run its allowed test. Negative cases:
read an unrelated fake secret, modify protected configuration, change policy,
escape through child shell/symlink and reach a prohibited test destination
directly or via redirect/proxy. No real secret or production endpoint.
Distinguish process containment from MicroVM isolation; record unsupported
controls and installation/maintenance cost. Demonstrate that removing a tested
control makes its negative test fail in the disposable fixture. Keep the
simpler existing solution if the candidate adds no material enforcement or
maintenance benefit. No new Cloud runner or custom generic sandbox wrapper.

### W41-R3 — Runtime policy and negative-path upgrade acceptance (P2)

Owner: agentops test contract; native host/harness owners enforce it; existing
Vuoro acceptance owner remains separate. Inventory actively used runtimes and
record explicit resolved permission/network/filesystem/tool/credential settings
for exact builds. Unknown settings are reported, not treated as safe defaults.

In disposable fixtures exercise denied tool invocation, headless disabled MCP
startup, forbidden egress via alternate tool/redirect, inaccessible fake secret,
fake completion, changed artifact and interrupted worker with late result.
Check both runtime refusal and actual lack of forbidden effects; owner acceptance
must reject missing evidence or stale artifact regardless of runtime success.
Repeat across one real harness upgrade with the same policy. CI checks settings
drift; record a manual qualification for runtime paths CI cannot exercise. Remove
each guard in a fixture and show the relevant assertion fails. No production
attack simulation or new human approval gate.

### W41-R4 — One skill as a supply-chain artifact (P3)

Owner: agentops. Start with `skills/recording-acceptance/SKILL.md` and its actual
referenced scripts/resources (substitute another existing skill only with a
recorded reason). Record source repository/origin, revision, raw-byte digests,
dependency inventory, publisher/provenance, trust class and observed load path.
Document required environment/tool endpoints without embedded credentials.
Keep host execution policy and its revision separate from distribution metadata.

Prove changed dependency bytes, mismatched digest, missing origin, dynamic or
unverified content, and permission-widening frontmatter cannot inherit prior
execution permission. An unknown digest/coverage is unknown, not trusted or
unused. Reuse native observations and the #2488 coverage design; do not add a
compiled profile, global skill registry or manifest-retirement dependency.
Deliver one small package example and an onboarding checklist; native vendor
adapters are evaluated through #2639 rather than inventing a universal manifest.

### W41-R5 — Managed-workflow responsibility and identity review (P4)

Owner: Vuoro contracts, coordinated in agentops. Review current OpenAI and
Anthropic docs and existing owner schemas; use synthetic event fixtures rather
than starting a paid managed session. Map provider session/thread/workflow IDs
to work, attempts, current ownership, artifact digest, acceptance, effects and
evidence, identifying responsibilities the harness removes and those it cannot.

Cases: completed workflow with failed worker, missing thread evidence,
interruption, detached late result after replacement, duplicate event,
uninspectable workflow program and changed artifact. Every case must leave
owner state correct and gaps explicit. Work identity must survive replacing
the provider session. Reuse #2623 continuation and TS-18 evidence inputs; no
migration, orchestration engine or provider-completion acceptance shortcut.

### W41-R6 — Browser-auth/broker boundary reference (P4)

Owner: cred-broker design; coordinated in agentops. Model one authenticated
task on a local fake site with origin-specific approval and external fake
credential entry/injection. Draw data flow through model, browser, broker,
logs, artifacts and receipt; identify any current unnecessarily exposed material.

Prove the fake secret never appears in model/tool text, captured history, logs
or evidence. Test missing/changed origin, redirect to another origin, replayed
approval and subagent auth request; bind the request to exact origin, action and
current policy. Approval does not prove authentication or accepted work. Cookies
remain browser-held secrets and require containment/redaction checks. Produce a
gap decision, not a browser credential service. TS-16 still forbids homelab
credentials and effects crossing into an unhosted runtime.

## Existing backlog refinements

Record these as additive served notes; retain current owner/status and avoid
overwriting independently active descriptions.

| Existing item | Additive requirement |
|---|---|
| #2623 continuation delta | Explicit session ≠ work acceptance: resume with different provider/session ID and no predecessor transcript; late results remain old-attempt evidence and cannot settle current work. W41-R5 supplies the mapping. |
| #2635 client compatibility | Extend the existing real-client matrix with exact server/client SDK builds, negotiated MCP revision, one modern 2026-07-28 and one legacy client, stateless behavior, reconnect, unsupported-version refusal and graceful extension omission. Test Skills capability advertisement only where actually offered. No parallel compatibility project or registration change. |
| #2639 discovery/publication | Evaluate private capability packaging: skill content + MCP endpoint/configuration + required environment + provenance + separate permissions. Keep vendor package formats as adapters and distinguish package install from OAuth consent and directory approval. Use W41-R4; no publication from this planning task. |
| #2482 identity decision | Distinguish delegating human, persistent agent principal, executing workload and reusable display name. Cover accountable owner, access review, suspend/revoke/offboard and name reissue without inherited authority. Keep delegation representation replaceable; no proprietary chain format. Reconcile live implementation with #2627 access explanation and #2588 epoch refusal rather than assuming old bearer semantics remain current. |
| #2632 coverage/usage | Link observation/run IDs to owner work, policy receipt and accepted evidence; report source/build and unknowns. OTel Development attributes are optional observations, never the workflow store, acceptance source or authoritative billing source. Reuse P4 population/denominator. |

## Delivery order and watch list

First take the routing comparison and containment comparison as small empirical
decisions; begin the denial contract with the same fixtures so both tests expose
their failure cases. Protocol/packaging refinements follow existing onboarding
work. Workflow and browser reviews are documentation/fixture investigations and
do not delay the currently authorized Cloud rollout.

A2A's boundary rule is recorded here, without an implementation item. Revisit
only when an independently deployed agent service exists. SEP-3415 stays watch
only until accepted semantics and a real external-event use case exist; any
future event creates or references work through its owner with replay/idempotency
handling, not by treating delivery as accepted execution. WIMSE proposals and
enterprise agent identities are design inputs, not protocol adoption commitments.

## Served intake receipts

Created and read back on 2026-10-11 in agentops sprint **562**, track
**W39-W41 architecture investigations**. All six are pending; each has the
scope above, a native priority, a plan reference and attributed planning note
(`agent:codex`, `model:gpt-6`, `attempt:1`, `w39-w41`).

| Investigation | Served item | Priority |
|---|---|---|
| W41-R1 routing comparison | agentops#2647 | 3 |
| W41-R2 Linux containment | agentops#2648 | 3 |
| W41-R3 policy/upgrade denial tests | agentops#2649 | 2 |
| W41-R4 skill supply chain | agentops#2650 | 3 |
| W41-R5 workflow/identity review | agentops#2651 | 4 |
| W41-R6 browser/broker reference | agentops#2652 | 4 |

Additive planning notes and plan references were recorded on #2623 (event
#4928), #2635 (#4929), #2639 (#4930), #2482 (#4931) and #2632 (#4932).
Existing descriptions, owner/status and active work were retained. No new
blocking dependency was added. Item IDs identify authoritative served records;
this document does not assert they are implemented or qualified.
