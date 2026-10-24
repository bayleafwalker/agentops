---
doc_id: portable-agent-workflows.agentops.v1
status: proposed
supersedes: []
---

# Portable, long-running agent work across hosts

Status: investigated implementation plan, 2026-10-24. This document proposes
work; it does not certify a deployed runtime, ratify an owner API, or authorize
infrastructure changes. The user requested durable plans after the cloud-dispatch
and Mars Founder investigations. TS-1 through TS-15 in
[the target state](../2026-09-17-target-state.md) remain governing direction.

## Outcome and decision

An operator should select a backlog and an eligible environment, authorize a
bounded programme, close the workstation, and return to independently verifiable
candidates with clear next actions. Another permitted host should be able to
continue that programme without recovering the first host's private directory.
Useful implementation scope, with permission to plan and realign dependencies,
is the goal; keeping a process alive for thirty hours is not success.

Build the missing integration around the existing native harnesses and Sovite
execution plane. Start the repository-editing execution capability in Sovite;
do not create another queue or a general dispatcher in agentops or Vuoro. A
host-side package may later be extracted if reuse justifies it, without moving
domain authority. Native harnesses retain planning, model choice, compaction,
and continuation. Sovite admits an exact authorized binding and manages its
execution attempt. Vuoro coordinates and records. Agentops owns shared guidance,
contracts and diagnostics. These are responsibilities, not a new monolithic
runner.

## What the investigation established

| Observation | Consequence |
|---|---|
| A cloud bootstrap referred to a workstation-only file; the remote task could not find it. | Bootstrap from committed or explicitly delivered content, with source and access provenance. |
| The installed Cloud command exposed legacy environments while the user had published a new Cloud environment. | Discover capabilities in the actual caller and distinguish product generations; a published environment is not a launch API. |
| A task URL was supplied, but its startup was not independently readable by the coordinator. | Record submitted, acknowledged and started separately. A URL is not startup evidence. |
| Git mirrors and canonical Forgejo source had different revisions. | Verify the intended commit and source authority before launch; record mirror lag. |
| Mars Founder's overnight prototype uses local files, log matching, process-name checks and direct main pushes. | Migrate incrementally with operation handles, explicit attempts, isolated workers and canonical landing receipts. |
| Agentops host-adapter, Vuoro Managed Agents integration and Sovite execution workers already exist. | Extend and qualify these boundaries; the gap is not absence of all dispatch machinery. |
| Sovite's connector explicitly implements inference-only traffic. | Do not use that protocol as worker enrollment or reverse execution control. |
| The NixOS host-adapter already separates the immutable launcher and worker identities. | Assemble the reusable worker host from existing modules and test the remaining exposure paths. |

Source inspection establishes implementation shape, not deployed qualification.
The pinned survey below is the basis for these findings. Mars local-runtime
failures reported in the handoff are motivations; they are not fresh production
reproductions. No provider credentials or private handoff bytes belong in a
portable task packet.

A later source-only PW-01 inventory of the integrated candidate branches is
recorded in the [portable workflow contract inventory](../../evidence/2026-10-24-portable-workflow-contract-inventory.md).
It identifies existing owner records, schema revisions, and unqualified
cross-host histories without ratifying a new API or changing the survey pins.
Its EC-00 source recheck records partial TypeSpec/OpenAPI tool pins from the
separate Vuoro contract-foundation candidate at
`3db3e34a142f0cb1e7ad773fcdcc1948082ea731`; it leaves the MCP projection and
other EC-00 acceptance conditions open.
The Vuoro candidate now also has Python JSON complexity commits
`1d50efb1f3801afe36c29ee040b31086cd9431e6` and
`08d50726fce210754a8a48e94c18f526487886e1`; the latter bounds structural scans
before decoding, with independent source review but no test run in this pass.
The Appservice AS-PW3 source inventory is recorded on candidate branch
`cloud/20261024/programme-08-integration-appservice-exact` at
`docs/evidence/2026-10-24-portable-workflow-landing-policy-inventory.md`; it
distinguishes tracked workflow configuration and dated settings evidence from
current effective host rules, which remain unverified.
Its AS-PW3 inventory remains on the same candidate branch at commit
`7871d6d50a63e2e8406e279b2b0d2bffb2e9851e` in
`docs/evidence/2026-10-24-portable-workflow-landing-policy-inventory.md`; it
maps tracked workflow settings without claiming current effective host rules.
The AS-PW1 inventory was refreshed at commit
`4da4a4ccda922f69ddee7341fa3036d02f716a58` in
`docs/evidence/2026-10-24-portable-workflow-onboarding-inventory.md`. Its sync
script hardening is in commits `1b359878`, `a1a63336`, and `753e5544`: it skips
target-only bindings, rejects ambiguous/missing binding scope and duplicate
desired names before database/API calls, and marks the old Forgejo count as
historical. Existing integrations are still compared by name only; no claim or
effective-scope verification, cross-owner onboarding receipt, or live Forgejo
recheck is claimed.
The AS-PW5 source and artifact reachability inventory is on that branch at
commit `54f2e1a56153053010698dcdc24449a810371864`, at
`docs/evidence/2026-10-24-portable-workflow-source-reachability-inventory.md`;
it maps the Appservice canonical/mirror decision and narrow service-release
path without claiming generic worker transfer support.
The AS-PW4 observability inventory was added to the same candidate branch at
commit `2d7bce4e89c12ce5ce4fa866ff6cce45e5c3d747` in
`docs/evidence/2026-10-24-portable-workflow-observability-inventory.md`. It
maps existing harness and telemetry evidence while leaving portable run/attempt
correlation, progress/heartbeat and usage coverage dependent on released owner
interfaces.

## Ownership and durable plans

| Repository | Owner plan | Responsibility |
|---|---|---|
| agentops | [plan](https://github.com/bayleafwalker/agentops/blob/main/docs/plans/agentops/2026-10-24-portable-agent-workflows.md) | Shared contract, diagnostics and programme guidance (PW-01) |
| sovite | [plan](https://github.com/bayleafwalker/sovite/blob/main/docs/plans/2026-10-24-portable-agent-workflows.md) | Repository sessions and execution-host integration (PW-04) |
| vuoro | [plan](https://github.com/bayleafwalker/vuoro/blob/main/docs/plans/2026-10-24-portable-agent-workflows.md) | Scoped context and evidence transport (PW-05) |
| sprintctl | [plan](https://github.com/bayleafwalker/sprintctl/blob/main/docs/plans/2026-10-24-portable-agent-workflows.md) | Work authority and portable continuation (PW-05) |
| vuoro-cloud | [plan](https://git.apps.kotona.app/bayleaf/vuoro-cloud/src/branch/main/docs/plans/2026-10-24-portable-agent-workflows.md) | Tenant/environment capability composition (PW-06) |
| gitops-nixos | [plan](https://git.apps.kotona.app/bayleaf/gitops-nixos/src/branch/main/docs/plans/2026-10-24-portable-agent-workflows.md) | Reusable host profile and commissioning (PW-02) |
| cred-broker | [plan](https://git.apps.kotona.app/bayleaf/cred-broker/src/branch/main/docs/plans/2026-10-24-portable-agent-workflows.md) | Canonical onboarding and scoped landing (PW-03) |
| appservice | [plan](https://github.com/bayleafwalker/appservice/blob/main/docs/plans/2026-10-24-portable-agent-workflows.md) | Operational registration, protections and observability (PW-03/07) |
| mars-founder | [plan](https://git.apps.kotona.app/bayleaf/mars-founder/src/branch/main/docs/plan/06-portable-agent-workflow.md) | Pilot and prototype migration (PW-08) |

Work state, advisory reservations and continuation references belong to Sprintctl.
Sovite owns execution leases, fencing, cancellation and attempt journals. The
native provider owns its session/process state. A host journal is a recoverable
cache, not replacement authority. A reservation is not an execution lease or a
credential; work reassignment alone cannot stop an old process.

## Shared contract to shape before implementation (PW-01)

Describe a versioned exchange using existing shared-contract ownership and
release paths. Extend current contracts only where fields or operations are
missing; do not introduce a second repository identity registry or a second
manifest that grants authority. Candidate records need:

- Repository authority ID and canonical locator, immutable base commit, target
  branch, permitted change surfaces, governing item and document revisions,
  dependency snapshot, and access class for each input.
- Inline minimum instructions plus commit/path/digest references or an authorized
  artifact transfer. Resolve relative repository paths after checking out the
  declared source. Missing context must be diagnosed before any worker starts.
- Goal, completion criteria, priority/dependency rules, replanning scope, time and
  spending bounds, concurrency ceiling, checkpoint cadence, stop conditions,
  review/landing policy, and escalation destinations. Runtime-native goals are
  preferred where supported; continuation support must be measured.
- Requested model/harness and allowed alternatives; observed resolved binding,
  version and configuration provenance; caller identity and enrollment reference;
  environment publication/version reference. TS-3 profiles describe observed
  configuration; they do not compile prompts or choose models.
- Idempotent intent/attempt correlation, provider operation/session handle,
  predecessor and transfer references, observed phase, timestamps, freshness,
  authority, redacted evidence links and uncertainty. Handles are not capabilities.
- Candidate commit/artifact digests, verification results and exact tested head,
  independent acceptance, canonical landing and deployment receipts as distinct
  facts. Preserve missing, stale, refused and unknown states explicitly.

Treat submitted -> acknowledged -> started -> useful progress -> candidate ->
verified -> accepted -> landed -> deployed as separate observations and owner
transitions. Execution success does not settle work. A failed connection after
launch is ambiguous: reconcile the same operation before issuing another.

## Delivery sequence and existing backlog

These work packages extend existing programmes, not a parallel backlog. Shape
bounded implementation items under the cited work, with governing document
refs and pinned execution revisions. Do not mark implementation done when this
plan lands. Check live dependencies and reservations before selection.

| Order / package | Owner and scope | Exit evidence |
|---|---|---|
| 1 / PW-01 | agentops + domain owners: capability/state vocabulary, portable packet and threat fixtures; align agentops#2692, agentops#2730 and agentops#2864 | Contract review against TS claims; minimal packet resumes on a clean host without local archive access. |
| 1 / PW-02 | gitops-nixos + agentops: reusable worker host, readiness and drift; align agentops#2733, agentops#2736 and agentops#2742 | Measured runtime/auth/network/isolation evidence; failures explain the actual boundary. |
| 1 / PW-03 | cred-broker + appservice + Vuoro/Sprintctl: idempotent repository onboarding composition | Dry-run reports existing/missing/conflicting registrations; repeat apply makes no duplicate identity or broadened grant. |
| 2 / PW-04 | Sovite: repository session execution through qualified native bindings, using R4/F2 execution-owner work (agentops#2850) | Crash/response-loss/takeover histories fence old attempts; code edits and native resumption work in isolated worktrees. Depends on PW-01/02. |
| 2 / PW-05 | Vuoro + Sprintctl: portable continuation and owner-evidence projections; align vuoro#2725, vuoro#2728, vuoro#2734, vuoro#2735, vuoro#2737 and sprintctl#2738 | Another authorized host reconstructs ready work and sources, without converting advisory metadata into authority. |
| 3 / PW-06 | vuoro-cloud: supported environment/caller capability publication and tenant-scoped integration; align vuoro-cloud#2682, vuoro-cloud#2683, vuoro-cloud#2684 and vuoro-cloud#2741 | Published setup versus caller launch support distinguished; cross-tenant access and stale publication rejected. Depends on PW-04/05 for execution integration. |
| 3 / PW-07 | appservice + owner APIs: heartbeats, completion and usage coverage, canonical landing prerequisites; align agentops#2726 and agentops#2730 | Alerts deduplicate by attempt; uncertain startup and stale progress visible; CI/review receipts bind exact candidate. |
| 4 / PW-08 | mars-founder pilot, then a second repository and another host/provider | Unattended bounded programme, injected interruption and continuation, independent verification and canonical landing; optional deployment remains separately gated. |

PW-01/02/03 can progress independently with explicit interface assumptions.
PW-04 and PW-05 can proceed against reviewed fixtures once PW-01 is stable;
cloud packaging need not wait to improve diagnostics. Cross-repo changes land
through released contracts and pinned consumers, not simultaneous checkout
assumptions. This plan makes no calendar-duration promise.

## Repeatable operator workflow

1. **Prepare and diagnose.** Resolve authority, fetch canonical source, compare
   mirrors, inspect actual caller capabilities, runtime versions, headless auth,
   network policy and storage. Report unable-to-check separately from absent.
2. **Commission once.** A proposed `repo onboard` composition plans manifest
   authority metadata, broker registration/integration, Vuoro binding and the
   shared host helper. Each owner approves/applies its own transition. It resumes
   partial progress and never copies the workstation's identity to another host.
3. **Shape a programme.** Select ready backlog with current refs, authorize broad
   but bounded implementation and replanning, choose independent change surfaces,
   establish budget/deadline and landing gates. A worker may investigate and split
   items within that envelope; it must not invent authorization or ignore blockers.
4. **Dispatch through a qualified surface.** Native provider APIs/CLIs/SDKs must
   expose and prove the required capability. If only manual new-Cloud launch is
   supported, emit a self-contained prompt and record the user launch separately.
5. **Confirm startup.** Capture operation ID and worker-origin receipt containing
   actual source, host/environment, harness/model and first useful activity.
   Timeout produces uncertainty, not an automatic duplicate launch.
6. **Continue.** Checkpoint decisions, current candidate refs, verification and
   next work at item boundaries and bounded intervals; renew execution leases in
   the execution owner. Resume native sessions where qualified, otherwise start
   a linked attempt after reconciling the predecessor and transfer permissions.
7. **Review and land.** Produce PRs/candidates with CI and configured independent
   review; brokered exact-head landing checks canonical state and merge policy.
   Reconcile response loss before retry. Existing authorized automation may land
   when its gates pass; this plan adds no universal human confirmation gate.
8. **Return.** Show accepted, pending review, blocked and uncertain work with
   evidence and next actions. Completion/landing/deployment remain separate.

## Model, permissions and worker boundaries

The native harness chooses a permitted route; Sovite executes the resolved
binding without transparent substitution. Rate limits, auth failures, policy
refusals, exhausted budget and uncertain provider effects have distinct outcomes.
An authorized route change is a new correlated attempt after safe reconciliation.
Do not infer a fallback from a log regex. `fast-build` has no automatic model
substitution; its current Codex model is `gpt-6-luna` under model-routing.json.

Reuse existing UID, immutable launcher, credential and egress modules. Workers
cannot read coordinator state, sibling worktrees, broad home credentials or
project hook configuration that can widen permissions. Enforce filesystem and
process boundaries, not prompt prohibitions. Test headless permission settings
with command-rewriting hooks enabled; never fix an allowlist failure by silently
bypassing checks. Non-Nix hosts need equivalent acceptance evidence before being
advertised as supported. Automatic host deployment is a separate operational
choice, not the default remedy for drift.

## Cloud and reachability

New Codex Cloud and legacy Cloud are distinct capabilities. Official
[Cloud environment documentation](https://learn.chatgpt.com/docs/environments/cloud-environments)
describes published reusable setup and isolated task workspaces. The
[Codex SDK documentation](https://learn.chatgpt.com/docs/codex-sdk) describes
local thread control. Neither establishes that this workstation caller can
programmatically create a task in a particular new-Cloud environment. Qualify
that capability explicitly and keep a manual launch path until it is exposed.
Sources checked 2026-10-24; recheck product support before implementation.

A verified Git mirror or authorized immutable snapshot may supply cloud source;
public Forgejo exposure is not a prerequisite. Private direct access, if later
needed, requires a separately reviewed narrow route and credentials. Do not add
a public tunnel, copy broad tokens, or send private artifacts to public mirrors
as part of workflow assembly. Claude cloud routines retain their documented
GitHub/reporting boundary and the existing routine-authoring rules.

## Acceptance programme

Qualification must include at least these histories, with expected owner state
and evidence after each step:

- Clean unrelated host; missing local archive; stale mirror; wrong repo or tenant;
  stale governing doc; mismatched input digest; revoked enrollment or grant.
- Published environment but unsupported caller; wrong product generation; stale
  runtime/config; missing headless auth; command rewrite that changes permission
  matching; sentinel private coordinator data inaccessible to the worker.
- Submission response lost; no stdout after successful start; process dies during
  edits; expired execution fence; takeover while old worker continues; provider
  handle no longer resolvable. Never repeat an uncertain external effect blindly.
- Replan with changed dependencies or a superseded item; deadline/budget exhausted;
  concurrent sessions with aggregate spending exposure; source-only capacity
  declaration cannot be reported as live capacity.
- Candidate exists but tests fail; check result from another head; stale review;
  merge reply lost; cleanup failure after successful merge; deployment not run.
- Heartbeat stale versus useful progress stalled; notifications retried; cost hook
  absent. Missing usage coverage is unknown, not zero cost.

Pilot first with disposable scopes, then an explicitly authorized real backlog.
Require a Mars Founder and a second-repo demonstration, including host loss and
continuation, before claiming repo-agnostic or thirty-hour reliability.

## Historical guidance and completion

The ActionQ-era session-completion stream and retired cockpit are historical;
new telemetry uses supported owner APIs and the current observability surfaces.
Do not restore actionq-dispatcher or hybrid dispatch. Vuoro Cloud's old connector
proposal must be read alongside its owner plan below, not as a working worker
launch API.

This planning delivery is complete when owner documents are on canonical main
with traceable source pins. Implementation closes only with the qualification
and owner acceptance above; deployment and commercial hosted execution require
their own existing release gates.

## Survey source pins

| Repository | Inspected canonical main |
|---|---|
| agentops | `b760494dea018794231e197e71927b12e14efa53` |
| sovite | `b712d5f69a62e618e66acb6a6beae9dad5e25e56` |
| vuoro | `61df7c27217b1e2818737b19481ebe07e4c9f6bd` |
| sprintctl | `b76bd692060ca9b5f53f78d07ee187918a5d265d` |
| vuoro-cloud | `a237bbdade2528c6769af666bc84c25e3caa1ca3` |
| gitops-nixos | `b554d5e08a4ca0c04ad0f9478c86c123a9104251` |
| cred-broker | `c0bee20e90e4bf41ee8c6ab5f99f97de2656a9bc` |
| appservice | `5ab5e11771a07585457759c0344908d6d0011286` |
| mars-founder | `134396d9fee13b5011b59ba4d8f12b0b7d757cc3` |

Each owner plan names its inspected files. These pins establish investigation
provenance, not rollout status. Reconcile newer source before implementing.
