---
doc_id: subscription-cross-harness-pilot.agentops.v1
status: approved-experiment-plan
approved_at: 2026-10-25
supersedes: []
---

# Subscription-backed cross-harness pilot: Decimal Iron

**Approved decision, 2026-10-25.** Qualify a small, real, workstation-off
engineering programme consisting of **two Claude Projects cloud issue
threads** and **one cheap subscription-backed coding agent on the NixOS
devbox**. Deliberately interrupt one attempt, reconcile its evidence and
continue that *goal* through a **different harness/provider**. Compare the
evidence trails reconstructed from Vuoro, not just the generated PRs.

This is a bounded experiment under the
[portable-agent-workflows programme](2026-10-24-portable-agent-workflows.md),
especially PW-01/PW-04/PW-05/PW-07/PW-08. The
[estate target state](../2026-09-17-target-state.md) and the Sovite, Vuoro,
Sprintctl and ActionQ owner contracts remain authoritative. This plan does
**not** claim a deployed feature, account eligibility or successful execution.

## Hard constraints and owner boundaries

- **Subscriptions, not API credits.** Claude Projects runs must count against
  the user's Claude subscription; devbox runs must use a verified supported
  subscription login to a native harness (Codex, Claude Code, or separately
  qualified OpenCode Go). No GitHub Actions, metered API fallback, browser
  cookie reuse or undocumented subscription-token extraction. A requested
  subscription route is not proof of actual billing.
- **Primary workstation may be off.** Execution, launch and later inspection
  are tested through native cloud/remote interfaces independently of the
  primary Arch workstation. The devbox remains a supplementary host.
- **Do not invent a dispatcher.** Sprintctl owns eligible work, revisions,
  dependencies and advisory reservations; Vuoro exposes owner-backed context
  and evidence; Sovite admits the exact authorized execution binding and
  owns attempts where its released contract applies; ActionQ federates
  native-execution references; provider harnesses own process, context and
  conversation. Agentops owns shared planning and diagnostics. No new queue,
  scheduler, execution daemon, universal transcript proxy or ActionQ dispatcher.
- **Native interaction after launch.** Store provider-issued task/session IDs
  and actual open/attach links. Follow-up, approve, cancel or resume via a
  capability verified for that specific provider. Never simulate unsupported
  native operations or migrate private conversation histories.
- **Switch at attempt boundaries.** A change of model, runtime, billing
  route, provider or data boundary starts a newly authorized, correlated
  attempt after reconciling the predecessor. No silent fallback. A prior
  attempt's source references provide context, not authority.
- **Cloud scope is public synthetic Decimal Iron only.** Do not provide cloud
  threads Forgejo-only sources, private coordinator notes, production
  infrastructure material, appservice credentials or served Sprintctl tokens.
  Remote devbox retains its dedicated agent UID, scoped PAT and egress rules.

## Preflight: actual capabilities, credentials and backlog

| Gate | Observable requirement | Fail/hold behaviour |
| --- | --- | --- |
| Work selection | Check current Decimal Iron issues, PRs, main SHA, dependencies, ownership and revision. **As checked 2026-10-25, PR [#9](https://github.com/bayleafwalker/decimal-iron/pull/9) is open and proposes closing issues #1–#8.** Do not blindly allocate those issues while the PR is unresolved. Choose or shape three follow-on bounded issues after disposition, with separate work identities and acceptance oracles. | Hold selection; never duplicate #9's work |
| Claude Projects | Verify this account can access Projects beta, provision two cloud issue threads, fix and observe their actual Claude model/effort, access GitHub, open native session URLs and accept follow-ups. Beta eligibility is **not assumed**. | Mark cloud lane unavailable; do not substitute metered Managed Agents or claim the comparison passed |
| Claude routines | If launching via routine API, use the per-routine token from native web UI and verify the fired execution belongs to the intended Project and returns a native handle/URL; inspect current endpoint/header contract. A manual launch is useful baseline evidence, **not** an unattended launcher qualification. | Record manual-only/unsupported until an external launch is proven |
| Cloud billing | Inspect cloud environment credential precedence (notably `ANTHROPIC_API_KEY`) and account usage/billing evidence. Do not expose environment variable values or routine bearer. Record entitlement/quota stop separately from model failures. | Proven API-billed attempt fails; unclear billing stays unknown, not subscription-verified |
| Devbox login | Check real CLI version, headless auth and active credential method (`codex login status`, `claude auth status`, environment overrides); qualify OpenCode Go sign-in and allowed terms before relying on it. Verify native session IDs and attach/recovery after disconnect. | Refuse unverified billing route or unsupported interaction |
| Host and authority | Verify isolated Git worktrees, repo grants, dedicated UID, egress, permitted inputs, current owner revisions, real owner APIs and readback. Cloud worker may emit public-safe Git/PR evidence without owner credentials; a trusted caller imports/verifies it. | Missing owner ingest remains an explicit blocker, not a fabricated Vuoro record |

Run this preflight without depending on the workstation's uncommitted files.
Distinguish configured environment, submitted request, acknowledged launch,
observed activity and verified session identity. A published Cloud environment
alone is not a callable launch API.

## Work allocation: 3 issues, 4+ attempts

| Lane | Initial target | Work selection | Output |
| --- | --- | --- | --- |
| H1 | Claude Projects cloud, thread 1 | First high-judgment issue and independent acceptance oracle | Native thread, branch/PR, tested commit and verified result |
| H2 | Claude Projects cloud, thread 2 | Second high-judgment issue, independent work identity | Same, separate native handle |
| V1 | Native cheap devbox harness | Third bounded issue in isolated worktree; predict one limited interface overlap with H1/H2 | Native session, actual subscription model, checkpoint and candidate |

Hold the two initial Project threads at a **fixed, recorded model and effort**
to make the comparison meaningful. Claude Projects is not a mixed-harness
worker pool; cheap parallelism belongs on the devbox or other native runtimes.

**Deliberate failed-handoff test.** Stop/interfere with V1 *after* it has
published an intentionally incomplete but durable checkpoint (exact commit,
branch and bounded findings). Record whether it is stopped, stale, alive or
unknown; never infer termination from a dead terminal. Reconcile the attempt
and authorize a successor with a different harness/provider — **Claude
Projects cloud, H3, if eligible** — from an explicit, allowed Git transfer.
The successor receives current work/decision revisions, candidate refs and
remaining criteria, **not a copied conversation**. Preserve old-attempt
evidence. If launch/transfer/stop state is ambiguous, refuse duplicate
execution and record the failed/blocked cross-harness test honestly.

This creates **three initial sessions plus at least one successor attempt**.
A third Claude cloud session for the successor is counted explicitly.
Reservations expose overlaps; they are neither exclusive locks nor execution
fences. Never force a destructive branch conflict merely to collect a metric.

## Cross-harness attempt receipt — field checklist, not a new authority

Use currently released owner schemas and operations. Where a field is
missing, capture a PW-01/PW-05 owner-contract gap rather than launching a
shadow session database. Each observation includes source/authority, recorded
time, freshness and unknown or refusal as applicable:

```yaml
work:
  ref: "github:bayleafwalker/decimal-iron#<issue>"
  sprintctl_ref: "<existing owner binding, if any>"
  work_revision: "<current revision>"
  base_commit: "<immutable canonical SHA>"
  dependencies: "<revisioned refs>"
  access_class: public
attempt:
  id: "<stable attempt correlation>"
  predecessor: "<attempt ID or null>"
  harness: "<native name/version>"
  provider: "<observed>"
  runtime: "<Claude Project or devbox instance>"
  binding_revision: "<authorized binding/grant>"
  requested_model: "<model>"
  observed_model: "<model or unknown>"
  observed_effort: "<effort or unknown>"
  billing_requested: subscription
  billing_observed: "<subscription | api | unknown>"
  billing_evidence: "<source/reference>"
native:
  launch_operation: "<correlation/uncertainty>"
  session_id: "<provider-issued ID or unknown>"
  open_url: "<provider-issued URL if supported>"
  supported_interactions: ["<observed modes>"]
result:
  phase: "<source-qualified phase>"
  branch: "<branch or null>"
  candidate_commit: "<SHA or null>"
  pr: "<URL or null>"
  verification: "<checks + exact tested SHA or unknown>"
  acceptance: "<owner disposition or pending>"
  landing: "<canonical merge receipt or pending>"
  deployment: not_attempted
```

Separate **submitted / acknowledged / started / useful progress /
candidate / independently verified / owner-accepted / landed / deployed**.
A provider's successful return is not acceptance. Source-verified Git
artifacts and an authorized current-revision owner transition matter more
than a worker's narrative.

A cloud worker can publish its evidence in the Git branch/PR. An authorized
reconciler verifies the evidence against native/Git/owner records before
persisting it in the existing Sprintctl/Vuoro/ActionQ/Auditctl boundaries.
Do **not** grant cloud threads forge or served-state credentials to make
them write authoritative `sprintctl` events directly; their event proposals
remain untrusted until owner-verified.

**Lost routine-fire reply:** no launch idempotency is assumed. Write a
durable launch-intent correlation before firing; discover the provider run
if supported; otherwise mark the launch ambiguous and stop. Never blindly
re-fire into a potentially active environment. A routine-fire bearer
is trigger-only, not a session-read authorization.

## Procedure and required observations

1. **Baseline:** Resolve PR #9, pin canonical main, issue revisions and
   independent work surfaces. Record intentionally predicted interface
   overlap, eligible bindings, concurrency/time/quota bounds, and current
   advisory reservations.
2. **Qualify both runtimes:** Prove account eligibility, cloud routine/native
   launch, actual subscription billing, devbox native headless session and
   external inspection/reattachment. No automatic credential/provider
   fallback.
3. **Launch with the workstation unavailable:** H1/H2/V1 start through
   supported native surfaces and produce independent launch/start evidence.
   Manual cloud launch is reported as manual, not automated.
4. **Collect candidates:** Exact candidate and tested head, PR and review
   evidence, touched files/interfaces, subscription usage signals, waiting
   time and verified disposition. In this **first trial only**, hold
   automatic merging to observe the integration gate; existing
   coordinator-reviewed automated merges remain the normal estate path.
5. **Inject V1 failure + H3 continuation:** Capture the incomplete candidate,
   reconcile old attempt, create a separately authorized cross-harness
   successor, and verify superseded/stale results cannot settle or land.
6. **Reconstruct:** From an independent client with the workstation off,
   reconstruct current goal, native references, each attempt's known/unknown
   outcome, decisions, candidate/tests, acceptance and remaining work from
   Vuoro's owner-backed evidence. Open provider-native sessions only for
   subsequent **interaction**, not to recover mandatory settlement facts.

## Metrics: log numerator, denominator and source

| Measure | Definition |
| --- | --- |
| Evidence completeness | Launch intents with owner-retrievable provenance, native handle or explicit ambiguity, candidate/verification/disposition or explicit unknown **/ all launch intents**. Also count actually observed starts separately. Target 100% explainable, not 100% successful. |
| Route / billing correctness | Started attempts with verified correct runtime, model/binding, access class and subscription-backed billing **/ all started attempts**. Any proven API-credit leak or unauthorized route fails. |
| Merge conflict rate | Git merge conflicts requiring resolution **/ all attempted PR integrations**. Record semantic integration conflicts/rework with the same denominator separately. Record touched-file overlap without equating overlap to conflict. |
| Review bottleneck | Candidate-ready → accepted/rejected latency and actual coordinator review minutes per candidate. |
| Effective throughput | Owner-accepted issue outcomes per elapsed programme day, alongside candidates produced/rejected and rework. |
| Continuation quality | One injected predecessor interruption and one different-harness successor: ability to continue from authorized artifacts without a duplicate/stale authoritative transition. Failures/ambiguity count; no synthetic success. |
| Capacity | Started sessions by harness/model, quota stops, wait time, duration, observed subscription usage and telemetry coverage; no invented cost for missing samples. |

The three-lane sample **cannot** statistically establish a conflict rate or
prove a 10–20-worker fleet. It establishes that integration conflicts,
human review and subscription pressure can be measured. Scale only when
accepted throughput and integration/review capacity justify it.

## Acceptance, failure and recovery

**Bounded pilot passes** only if both Claude Project initial issue threads
and one cheap devbox agent run against verified subscriptions; launch and
native handles are grounded; the workstation-off external-launch claim is
verified rather than assumed; every launch intent is explainable from owner
evidence (including failures and unknowns); every verified candidate names
its exact head; no unauthorized effects, silent fallback or stale settlement
occur; and conflicts plus review time are measured. **The cross-provider
continuation gate passes only when H3 actually proceeds on the resumed goal
from the authorized checkpoint.** If that fails, retain results but do not
claim the cross-provider capability is qualified.

Hold or fail on inaccessible Projects beta, unsupported routine API into a
Project, unverified/metered billing, credential leakage, missing source
transfer authority, lost native identity, ambiguous duplicate submission,
or attempted settlement of a stale head. Never disguise a manual Cloud
launch as a programmatic launch.

Rollback/stop: revoke or disable the trial routine and bearer, stop new
launches, cancel exact native attempts where supported, preserve all Git
WIP/PRs and existing owner evidence, reconcile ambiguous launches, and
return issue selection to the prior approved policy. Do not reset dirty
worktrees, delete history, auto-merge, or assume cancellation reverses Git.

**Ownership:** Agentops owns programme comparison and diagnostics;
Sprintctl/Vuoro/ActionQ/Auditctl own their existing work/evidence operations;
Sovite/devbox owns only the qualified native execution binding/attempts;
Claude owns its native cloud sessions. Implementation, infrastructure
changes, deployment, live qualification and PR acceptance are **not**
claimed or implicitly approved by committing this plan.
