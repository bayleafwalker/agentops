# vuoro.cloud backlog ideation (2026-09-27)

Status: Revised after operator review 2026-09-27; milestone structure adopted; M1 items filed as agentops#2521-#2525; R4 decisions and the #2520 lease contract decided by the operator 2026-09-27 (see "Status as of 2026-09-27" and R4).

Read-only planning pass. Sources: agentops plans (target state, cloud enablement plan, trusted-service design, options memo), vuoro `origin/main` (758e081, vuoro-service 0.1.76 / mcp-edge 0.1.3), vuoro-cloud `origin/main` (b013e29, generation 47 candidate), sprintctl and cred-broker-public READMEs, and `sprintctl item list --sprint-id 559` (149 items, 27 pending). Nothing was edited or committed.

---

## Revision after operator review (2026-09-27)

This section is the adopted-candidate plan. The operator reviewed PR #253 at 6867424 and directed: retain the proposal, adopt its architectural direction, and replace "the next 10 dispatches" (§4) with three evidence-based milestones before promoting anything into sprintctl. Sections 1-5 below this one are kept unchanged as the record of the ideation pass, except for two in-place annotations (H1-4, H3-3). Where this section and §3-§4 disagree, this section wins.

The operator's second direction shapes how the criteria are written: acceptance criteria say what a *finished* milestone demonstrates and which check we would actually run; they are not entry gates. Work starts, we learn, we adjust. A hard ordering constraint is kept only where skipping it breaks something real, and each such constraint names what it protects (a security invariant, TS-16, or a deploy-ordering break). Every criterion is a test, a command, or an artifact somebody can look at; anything that could not be assessed cheaply was dropped or softened.

Sources verified for this revision (exact quotes cited by line): vuoro-cloud `origin/main` 22cb93f `19-PRODUCT-POSITIONING-AND-PROOF.md` and `00-EXECUTIVE-DECISION.md`; agentops `docs/plans/2026-09-17-target-state.md` (TS-8 L37, TS-16 L45, tripwire L150-155) and `docs/plans/2026-09-26-cloud-enablement-plan.md` (effects L33-42, required-before-slice-1 L50-55); vuoro `origin/main` 3d91256 `docs/plans/2026-09-26-e2-e3-shared-contract.md` and `packages/vuoro-reconciler/README.md`; sprintctl item #2520 (read-only, `item show`).

### Status as of 2026-09-27 (after the second operator review)

This block records what changed after f4c8b57 was written. It overrides the text below where they differ.

- **Appendix A is filed.** A.1-A.5 are agentops **#2521** (M1-1), **#2522** (M1-2), **#2523** (M1-3), **#2524** (M1-4) and **#2525** (M1-5). M1-1..M1-3 are accepted and done (M1-1 agentops#258, M1-2 vuoro#138, M1-3 agentops#259). Do not file Appendix A again.
- **#2520 (E2b exclusive durable lease) shipped** in sprintctl **0.9.0** (sprintctl#98) and vuoro#141, released as **vuoro-service 0.1.77**. It shipped before the operator's lease notes, so it deviates from the normative contract in R4 in known places; see "Conformance of the shipped 0.9.0 lease" in R4. Related agentops follow-ups: **#2528** (an awaiting-verification report does not protect the item, and the report never receives the verifier's decision) and **#2529** (releasing an item to pending leaves its lease active).
- **#2519 replay protection merged** (vuoro#134).
- **Schema 18 is now the lease tables** (`work_lease`, `work_outcome_report`). The effect-intent store (M2-1) goes into a later sprintctl schema, not schema 18. H1-1 and Decision 1 are corrected accordingly.
- **R4 is decided.** The operator decided Decisions 1-4, made the seven lease semantics the normative contract for #2520, and added invariants INV-L1, INV-L2 and INV-E1. M2-1 and the #2520 conformance work can proceed in parallel.
- **The review's acceptor divergence is resolved.** The independent review of f4c8b57 noted that M2 left the acceptor self-asserted until M3-6. Decision 1 now binds acceptance to an authenticated `acceptor_principal` holding the distinct `work.effect.accept` capability, together with the intent revision and canonical digest. M2 therefore delivers authenticated acceptance of the acceptor, not only of the channel, and no separate "Decision 5" is needed. M3-6 adds human (OIDC) sign-in for the admin identity on top of that; it is no longer what authenticates the acceptor.

### R1. Three milestones

| Milestone | Objective | Proves |
|---|---|---|
| **M1 Record and resume real work** | Hosted activity leaves a reconstructable record, and interrupted work is taken over and settled correctly. | TS-16's control metric moves off zero for a *defined* cohort; the product proof contract's differentiated scenario (19-PRODUCT L46-53) runs end to end over the public surface; TS-8's second route exists in minimal form. |
| **M2 Apply one bounded effect reliably** | One diff-shaped intent travels proposed → accepted → applied with a chosen lifecycle owner, survives crashes, and its provenance chain resolves. | TS-16's promised property: "a verifiable chain from a signed commit back to a run record" (target-state L45), produced and resolved, not attested. |
| **M3 Widen proven use** | Effects and access widen only on top of M1/M2 evidence: repository subsets, a narrow auto-accept policy, full external onboarding, then comments and richer operator views. | The executive decision's external-user list (00-EXECUTIVE L7-14) holds without operator assistance; blast radius is bounded by exact repository grants. |

Each milestone below lists: objective, included items (existing ids plus new sub-items, prefixed M1-x/M2-x/M3-x), what a finished milestone demonstrates (the checks we would run), and the ordering constraints that are real.

---

### M1. Record and resume real work

**Objective.** Every hosted run in a known cohort produces a record that can be reconstructed, and work interrupted mid-flight is taken over, verified and settled by the authority, with the stale result kept as evidence. This is "the central investment": prove that work survives interruption and settles correctly before effects and broader access build on it.

**Included items.**

| Id | Item | Origin | Existing tracker ids |
|---|---|---|---|
| M1-1 | Evidence-emitting Routine and Routine-PR conformance check | H1-3 | none (new) |
| M1-2 | Strict-client MCP conformance in vuoro PR CI | H1-5, minus the image build, which shipped in vuoro#135 (merged 2026-09-27) | none (new) |
| M1-3 | Reconstructability coverage metric over a defined cohort | H1-4, corrected per review point 4 | pairs with #2486 |
| M1-4 | Settlement takeover proof with verification and resume | H2-2 promoted per review point 1 | depends on #2520 (E2b lease) |
| M1-5 | Minimal cross-harness continuation: successor run linked to its predecessor | H3-4 minimal proof per review point 5 | pairs with #2484 (S8 cross-harness leg) |
| M1-0 | Tracker hygiene: close or re-scope #2502 and #2479 with evidence; H1-9 is now R4 lease semantics 6 (normative) | H1-10, H1-9 | #2502, #2479, #2520 |

H1-9 (principal in the shared `IdempotencyLedger` protocol) is not a separate item: the contract's §5 amendment already requires each ledger to fold the principal, sprintctl#97's ledger already keys on it, and #2520 builds the next ledger consumer. The filing proposal (Appendix A) asks that #2520's description name the protocol change as part of its scope. **Revised 2026-09-27:** #2520 has shipped and the operator made the shared ledger protocol normative (R4, lease semantics 6). The conformance analysis found the key and digest conform but not the typed `begin` shape or one shared suite; H1-9 is now filed as **#2542** (R4, conformance note).

**What a finished M1 demonstrates (the checks).**

*Record (M1-1, M1-2).*
- A Routine PR in `bayleafwalker/vuoro` carries `Vuoro-Run: <run_id>` in its body, and `describe_run`/`work.read` resolves that id to a run record whose RunManifest fields (`harness_id`, `harness_build`, `model_id`, `recipe_id`, `observed_profile`) are non-null and whose evidence count is ≥ 1. Check: the agentops conformance script run against the PR number exits 0.
- `docs/runbooks/cloud-routine-authoring.md` requires `register_run` at start, `append_evidence` for findings, `write_session_note` at end, and the `Vuoro-Run` trailer; the E1 review Routine follows it. Check: read the runbook diff and one Routine PR.
- vuoro CI fails a PR that changes any MCP envelope field (`resultType`, `cacheScope`, error shape, `tools/list` schema) away from MCP 2026-07-28. Check: a deliberate one-line regression on a throwaway branch turns the `mcp-strict-client` job red; the D-044 isolation test runs in the same job against the image vuoro#135 builds.

*Coverage metric (M1-3).*
- The metric is a funnel over a **defined cohort**, not an inference from MCP exchanges or PRs: **expected invocations** (the Routine schedule and any dispatched cloud sessions, enumerated from the schedule definition and the dispatcher log) → **observed runs** (run records whose binding names the cohort's client and grant) → **evidence-bearing runs** (≥ 1 evidence entry) → **fully resolvable outcomes** (a PR or session note whose `Vuoro-Run` trailer resolves and whose evidence digests match). Each stage reports a count and the ids that dropped out.
- **Unknown coverage is reported explicitly**: invocations expected but never observed (silent failures, sessions that never contacted Vuoro) appear as `unknown: N` with their scheduled times, never as absent. Retries are counted once per expected invocation, so request counts do not inflate the numerator.
- Check: `scripts/reconstructability_coverage.py --since <date>` prints the four stages plus `unknown`; run it once with a Routine deliberately configured to skip `register_run` and confirm that invocation lands in `unknown`, not in `observed`. The weekly lane check-up quotes the funnel.

*Settlement (M1-4).* Two hosted callers, A and B, on the kotona workspace, over the public surface, against #2520's lease. The finished proof is an evidence packet in vuoro `docs/evidence/` showing, with tool-call transcripts and the authority's records:
- A claims work item X and heartbeats; A stops (process killed, not gracefully ended).
- B takes X over by claiming the stale lease on demand; the authority evaluates A's lease as stale and transitions ownership in one CAS (lease semantics 2 in R4). There is no operator reassignment in M1.
- A's late outcome report (`report_outcome`; the shipped operation is `work.lease.complete-v1`) is **rejected as superseded**. Normatively the code is `CLAIM_SUPERSEDED` carrying `claim_id`, `current_generation` and `reported_generation` (lease semantics 3). The shipped 0.9.0 lease returns `lease-superseded` (409) without generations, so on 0.9.0 the check asserts that code, and it asserts `CLAIM_SUPERSEDED` with generations once the conformance follow-up **#2540** lands (R4, conformance note). **A's result is retained as evidence** (disposition `stale`, settlement effect none) on X (visible through `work.read`/`describe_work` evidence list). **A cannot settle**: X's status did not change on A's call.
- **B's result satisfies a named verification profile** from 19-PRODUCT L133-139 (decided: `checked`, "configured checks passed"; R4 Decision 2), and the settlement record names it ("accepted under verification profile checked", never "proved correct", per L141-143).
- **The authoritative decision settles X**: the work owner, evaluating the current lease and configured verification at settlement time (L55-62), not the caller's self-report.
- **The dependent item Y becomes ready**: `next-work --explain` lists Y under `ready_items` after settlement and not before.
- **Restart/resume**: a third case in which A is killed and *A itself* restarts under the same principal and idempotency key, resumes its own claim, and completes normally, so a crashed-and-restarted worker does not look like a takeover. Normatively (lease semantics 5), a stale claim that nobody took over is reactivated with the same claim and generation. The shipped 0.9.0 lease reclaims it under a new lease id with the same run id, so the check asserts the same run id, one settlement and no stale-result rejection, and asserts the same claim id only once the conformance follow-up lands. A fourth case, where B has already taken over, expects A's restart to be refused as superseded (INV-L2): `lease-superseded` on 0.9.0, `CLAIM_SUPERSEDED` after conformance.
- Check: the six cases above are a scripted run (two `--cloud` sessions or Routines plus one kill), re-runnable, with the resulting records quoted in the packet. The landing page's proof section may cite the packet only after it exists.

*Continuation (M1-5).*
- `register_run` accepts an optional `predecessor_run_id`. The edge records the link on the successor run and refuses it unless the caller's binding may read the predecessor (same workspace and repository; grant carries `work:read`), because the contract resolves runs only to "the exact same binding" (contract §4 L79) and a successor is a *new* run, not a resolution of the old one.
- A successor run may read the predecessor's evidence and session notes (its checkpoint) through the read tools; the predecessor is not modified. Continuation transfers context, not authority (R4 Decision 3): the successor's later writes rest on its own grant, never on the predecessor's.
- Check: Claude Routine run R1 writes a session note and stops; a session on a different client identity (a second pre-registered OAuth client if one exists by then, otherwise a second principal on the same client) registers R2 with `predecessor_run_id = R1`, reads R1's note, appends evidence to R2, and `describe_run R2` shows the link. A negative case: a caller outside R1's workspace gets `run-not-found`. This is the minimal TS-8 second route; registering an OAuth client alone does not count (review point 5).

**Ordering constraints that are real.**
- M1-4 cannot start its live cases before `vuoro:work.claim` is granted (#2520 itself shipped 2026-09-27 in sprintctl 0.9.0 / vuoro-service 0.1.77; #2528, folded into #2539, must land before the proof relies on non-self-settling profiles): without an exclusive durable lease there is nothing to take over (operator decision in the cloud-enablement plan; #2520's own precondition that every tenant runtime serves the claim tools before the grant, because the edge refuses assertions carrying `work:claim` without tools). The harness, prompts and the restart case can be written first against a local backend.
- M1-1 needs generation 47 promoted for a non-zero result; writing the runbook and conformance script does not.
- Nothing else in M1 is ordered. M1-2, M1-3 and M1-5 can start now in parallel.

---

### M2. Apply one bounded effect reliably

**Objective.** One diff-shaped `EffectIntent` on one canary repository travels `proposed → accepted → applied` through a chosen lifecycle owner, the deployed homelab reconciler, and a signed commit whose provenance chain resolves; it survives a crash at every step; acceptance of the *proposal* is never confused with settlement of the *work*.

**Included items.**

| Id | Item | Origin | Existing tracker ids |
|---|---|---|---|
| M2-1 | Lifecycle owner decided and the durable intent store built in it, served on read | H1-1, reframed as a lifecycle and recovery contract (review point 2) | #2480, #2482 consumed as inputs |
| M2-2 | Reconciler deployed on the homelab; one intent applied on the canary; authenticated acceptance | H1-2 | none |
| M2-3 | Crash recovery and concurrency cases for the deployed path | new, split out of H1-1/H1-2 | none |
| M2-4 | Minimal provenance resolver: signature check and commit → intent → run → evidence chain | H3-2 minimal, pulled in (review point 3) | none |
| M2-5 | Pending intents visible in `next-work`/`session resume` | H2-3, shipped with the first consumer | #2474's bucket pattern |
| M2-6 | Cloud build lane, reproducible setup | H2-5, brought forward enough to support M1/M2 cloud work | none |

**What a finished M2 demonstrates (the checks).**

*Lifecycle contract (M2-1, M2-2).*
- **The owner was decided before the store was built** (R4, decision 1). One authority holds intent state; there is no second table elsewhere that can disagree with it. Check: the ADR/decision note is cited from the store's PR.
- **Effect-proposal acceptance is separate from work settlement.** Accepting an intent changes only the intent's state (`proposed → accepted`); it never changes the work item's status, and settling a work item never accepts an intent. Check: accept an intent on an item that is still claimed and confirm the item status is unchanged; complete the item and confirm a `proposed` intent on it is still `proposed`. The intent record names its acceptor as the authenticated `acceptor_principal` plus the acceptance binding (Decision 1; `acceptor_policy_version` for a later policy acceptor), and the reconciler's own re-validation still refuses an intent accepted by its proposer (README L93-95).
- **Acceptance is authenticated and bound** (Decision 1). `accept`/`reject`/`mark-applied` reuse the authenticated served-shell transport, which cloud assertions cannot reach (TS-16: no cloud-reachable path to acceptance), but each requires its own capability: `work.effect.propose`, `work.effect.accept`, `work.effect.reject`, `work.effect.mark-applied`. A principal that may change ordinary work state does not thereby hold acceptance authority. Each acceptance record binds `intent_id`, `intent_revision`, `canonical_intent_digest`, `acceptor_principal` (the authenticated principal, not a self-asserted string), `acceptor_policy_version` (for policy acceptance later) and a timestamp. An accepted intent is immutable (INV-E1): changing it requires a new proposal. Check: a principal with work-write but without `work.effect.accept` is refused; an accept naming a stale revision or a mismatched digest is refused; the reconciler refuses to apply an intent whose content digest differs from the accepted one.
- One canary repository (`vuoro-e3-canary`, Decision 4), one accepted docs diff, one PR opened by the reconciler with a commit signed by the reconciler identity `vuoro-reconciler-e3-canary`'s key and carrying `Vuoro-Run`, `Vuoro-Intent`, `Vuoro-Accepted-By` trailers (README L104-108). Check: `git verify-commit` succeeds against the reconciler's public key, and the PR body names the intent.

*Crash recovery and concurrency (M2-3).* Each case is a scripted kill of the reconciler at a named point, then a restart; the expected outcome is one branch, at most one PR, and one terminal intent state:
- **Crash after push, before PR creation**: restart finds `vuoro-effect/<intent_id>` already carrying the change and opens exactly one PR (extends README L111-112's re-run rule).
- **Crash after PR creation, before recording `applied`**: restart finds the open PR, does not open a second one, records `applied` once.
- **Crash before recording success** (after PR, provider call returned, process died before the `IntentSource` write): same outcome as above; the provider marker (branch + PR) is the recovery key, so the outcome is recoverable "without the ledger" (cloud-enablement plan L55, item 8).
- **Concurrent consumers**: two reconciler processes against the same `IntentSource` and the same accepted intent produce one branch and one PR; the loser records nothing or a harmless duplicate-detected outcome.
- **Credential revocation**: revoke the provider token (or the workspace token) mid-run; the intent ends `failed` with the reason recorded, no partial branch is left on the default branch, and other intents continue (README L113-115).
- Check: a pytest module with one test per case against a fake provider plus one live run of the after-push case on the canary. Cheap to assess: each is a red/green test with an artifact (branch, PR, intent state) to inspect.

*Provenance (M2-4).*
- `vuoro provenance <sha>` (or an agentops script; the polished command is M3) verifies the commit signature against the reconciler's key, reads the trailers, and resolves intent → run → RunManifest → evidence digests through the public read operations, printing one document that says "reconstructable", never "attested".
- Failure cases each produce a distinct, named failure: **wrong-repository reference** (the intent's repository is not the commit's repository), **missing evidence** (a run with no evidence entries, or a referenced evidence id that does not resolve), **mismatched digests** (evidence digest in the record differs from the recomputed digest), and **signature verification failure** (unsigned, or signed by a key that is not the reconciler's).
- Check: four fixture commits, one per failure, plus the canary's real commit; the resolver exits non-zero with the named failure for each fixture and 0 for the real one.

*Visibility (M2-5).* `next-work --explain` and `session resume` show a `proposed_intents` bucket (intent id, run, repository, title, proposer, age, the exact accept command). Check: propose one intent and see it listed; accept it and see it leave.

*Cloud lane (M2-6).* `scripts/cloud-setup.sh` builds the same environment twice from a clean checkout with identical lockfile digests; any claimed network restriction is enforced by the setup, not asserted (a test tries an outbound request after setup and it fails). Check: two runs, diffed; one denied request in the log.

**Ordering constraints that are real.**
- **Decision 1 (lifecycle owner) precedes M2-1's implementation** (decided 2026-09-27: A, sprintctl). Building the store in the wrong owner creates a second lifecycle authority (the review's "second settlement authority" risk) and rework of the served operations, scope rows and reconciler `IntentSource`; this is a design-invariant break, not a process gate. Everything else in M2 can be prototyped against an in-memory `IntentSource`.
- **M2-2's canary allowlist is one repository until H2-1 (M3) lands**: "stay canary-only until then" (cloud-enablement plan L50). This protects the TS-16 blast radius.
- M2-3 and M2-4 do not block M2-2's first live intent; they are what makes M2 *reliable*, and can land in the same or the next dispatch.

---

### M3. Widen proven use

**Objective.** Widen effects and access only on top of M1/M2 evidence, in this order: exact repository subsets, one narrow auto-accept policy, the full external onboarding contract, then comment intents and richer operator views.

**Included items.**

| Id | Item | Origin | Existing tracker ids |
|---|---|---|---|
| M3-1 | Exact-subset repository grants, including grant narrowing, revocation and existing-run behaviour | H2-1 | #2518 (edge half) |
| M3-2 | First auto-accept policy (docs-only diffs), measured on failures and operator effort as well as latency | H2-4 | none |
| M3-3 | External onboarding: the full executive-decision list, without operator assistance | H2-6 widened (review point 6) | #2428 (backups) as a stated precondition per 00-EXECUTIVE L98 |
| M3-4 | Comment and review intents through the reconciler | H3-1 | none |
| M3-5 | Settlement view: exceptions, pending intents, evidence links, freshness | H3-5 narrowed | none |
| M3-6 | Human OIDC sign-in for the admin identity (the acceptor is already an authenticated principal from M2, Decision 1) | H2-8, following the identity design | #2482 |
| M3-7 | Activity and denial report (observational) | H3-3 narrowed | folds into #2472 |
| M3-8 | Polished `vuoro provenance`, second-harness registration, Managed Agents proof | H3-2 rest, H3-4 rest, H3-7 | #2469 |

**What a finished M3 demonstrates (the checks).**

*Repository subsets (M3-1).* A grant names a subset of the workspace's repositories; every tool call names one repository from it; a call naming a sibling fails with the same not-found shape as an unknown repository. Narrowing a grant while a run is live: the run's next call outside the new subset fails, the run's record is unchanged. Revoking a grant: all calls fail, existing evidence remains readable to the workspace. Check: three tests in vuoro-cloud, one live consent-screen screenshot.

*Auto-accept (M3-2).* One policy `{workspace: kotona, repository: <canary>, effect_kinds: [unified_diff], path_globs: ["docs/**"]}`, off by default, switched on from the trusted side, every acceptance recording `{kind: policy, id, version, config_digest}`. Measured over two weeks: proposal → PR latency, number of failed applies, number of operator interventions (reverts, rejections after the fact). Check: a table with those three columns for policy vs operator acceptance; a proposed diff outside `docs/**` stays `proposed`.

*External onboarding (M3-3).* One invited external user, without operator assistance, does all six of 00-EXECUTIVE L9-14: creates an account and workspace; commissions a repository from a terminal; receives a scoped identity and client profile; runs `sprintctl doctor` successfully in served mode; creates, reads and updates sprint work through the public API; rotates and revokes credentials. **Connector evidence access and terminal work authority stay separate paths**: the MCP connector grant reaches `work:read`/`work:evidence` only; work creation/update/settlement authority is the terminal identity, and the evidence packet shows the two identities and their scope rows. Check: a screen recording or transcript per step, the `doctor` output, the credential rotation event in the audit log, and the second tenant visible in the drift report (H1-7).

*Comments (M3-4).* `forge_comment` intents pass provider authorization (the reconciler's token is scoped to the allowlisted repositories and comment permission), replay recovery (the after-push analogue: a crash after posting does not double-post), and output policy (mention and URL allowlist per trusted-service design §3). Check: tests for the three, one live comment on the canary. This is not "free" Forgejo support; Forgejo goes on the allowlist only after the same three pass against it.

*Operator views and reports (M3-5, M3-7).* The settlement view starts with exceptions (stale leases, rejected completions), pending intents and evidence links, and shows freshness (age of the newest record) and an explicit "authority unavailable" state when the served backend does not answer. The activity and denial report lists, per runtime and per model family, observed calls and recorded denials (`rate_limit_event` evidence) for a week; it does **not** claim to measure vendor quota consumption. Parking is decided (lease semantics 7): it is a work-level disposition (`work.disposition = parked`, reason = the denial ref) with the claim released or naturally inactive, never a lease state; M3-7 consumes that disposition/event. Check: the view renders against a workspace with one stale lease and one pending intent; the report runs weekly and its header says what it does not measure.

*Identity (M3-6).* M2 already binds `acceptor_principal` to an authenticated served-shell principal (Decision 1). M3-6 adds human OIDC sign-in for the admin identity, so the acceptor principal can be a named human session rather than a host credential, and the `--operator` string becomes attribution only. Check: an accept with a forged `--operator` records the authenticated principal, not the forged string.

**Ordering constraints that are real.**
- **M3-1 before effects expand beyond the canary** (cloud-enablement plan L50): a security invariant, not a process gate. Everything in M3-1 can be built while M2 is finishing.
- **M3-2 after M2-3 and M2-4**: enabling a policy that accepts without an operator before recovery and provenance exist means a failure is silent and unresolvable. Ordering protects TS-16's "every auto-acceptance ... can be reconstructed" (plan L41).
- **M3-3 after #2428-style backups and revocation exist** (00-EXECUTIVE L98: "hard quotas, token revocation, backup and selective restore procedures before onboarding anybody external"). This is the executive decision's own precondition, not a new gate.
- Everything else in M3 is unordered.

---

### R2. H2/H3 disposition, reconciled item by item

The review's table, with each row placed against the original item and the milestone it now belongs to.

| Original item | Review recommendation | Disposition in this revision |
|---|---|---|
| H2-1 repository subsets | Keep high priority after E2 proof; require before effects expand beyond the canary; include grant narrowing, revocation, existing-run behaviour. | **M3-1**, first item of M3; the three behaviours added to its acceptance. #2518 stays its edge half. Hard constraint: before effects widen (security invariant). |
| H2-2 settlement proof | Promote into the first milestone, with verification and resume added. | **M1-4.** The original outcome lacked the verification profile and a restart case; both added. |
| H2-3 pending intents | Ship visibility with the first consumer. | **M2-5**, shipped alongside M2-2's first live consumer. |
| H2-4 auto-accept | Enable the narrow policy after recovery and provenance work; measure failures and operator effort as well as latency. | **M3-2.** Measurement widened from latency alone to failures and operator interventions. Ordered after M2-3/M2-4. |
| H2-5 cloud build lane | Bring forward enough to support early cloud work; prove reproducible setup and enforce any claimed network restriction. | **M2-6**, may start during M1. Reproducibility check (two builds, identical digests) and an enforced-not-asserted network test added. |
| H2-6 external tenant | Keep as a distinct product milestone with the full onboarding contract. | **M3-3**, widened from an evidence-only connector pilot to all six items of 00-EXECUTIVE L9-14, with connector evidence access and terminal work authority as explicit separate paths. |
| H2-7 Routine firing | Defer until the manual flow works reliably; keep the dispatcher outside the substrate; specify duplicate-fire handling and bounded dispatch. | **Deferred past M3.** When revived, its acceptance includes a duplicate fire producing one run and a cap on concurrent fires; TS-2 keeps the dispatcher on the homelab. |
| H2-8 admin OIDC | Follow the identity design; browser sign-in alone does not authenticate the reconciler's `--operator`. | **M3-6.** Rewritten so the deliverable is an authenticated acceptor for the reconciler, not a login page. Superseded 2026-09-27: Decision 1 binds an authenticated `acceptor_principal` in M2; M3-6 adds human OIDC sign-in. |
| H3-1 comment intents | A sensible later extension, not "free" Forgejo support; require provider authorization, replay recovery, output-policy tests. | **M3-4** with those three tests; Forgejo enters the allowlist only after they pass against it. |
| H3-2 provenance | Promote the minimal proof; postpone broader tooling. | **M2-4** (signature check, chain resolution, four failure cases); the polished command and GitHub check move to **M3-8**. |
| H3-4 second harness | Promote the minimal proof; postpone broader tooling. | **M1-5** (successor run linked to predecessor, with the permission rule); OAuth client registration for Codex/Responses moves to **M3-8** and is explicitly not the proof of TS-8. |
| H3-3 denial reporting | Keep narrow and observational; add parking semantics only with the lease owner's contract. | **M3-7**, renamed "activity and denial report"; consumption accounting removed; parking decided 2026-09-27 as a work-level disposition, not a lease state (R4, lease semantics 7). H3-3 annotated in place below. |
| H3-5 settlement dashboard | Start with exceptions, pending intents, evidence links; show freshness and unavailable-authority states. | **M3-5**, narrowed to those and the two states; ready-item and last-20-runs panels dropped from the first cut. |
| H3-6 workspace-as-code | Defer; separate ordinary settings from policies that grant authority; a reconciler signature alone must not authorize widening its own permissions. | **Deferred past M3.** Kept in §3 as an idea with the operator's constraint recorded: authority-granting policies need an authenticated admin actor (M3-6) and a second signature, never the reconciler's alone. |
| H3-7 Managed Agents proof | Preserve as a bounded proof of the accepted second reachability path; define its trust model rather than calling it categorically safer. | **M3-8.** The "strictly safer than the public surface" claim in H3-7 is withdrawn; the item must state what the poller trusts (vendor task payloads, internal MCP server, devbox host). |
| H3-8 ablation | Defer until outcomes are dependable; ten cases establish feasibility, not a ranking. | **Deferred past M3.** When revived, it is a feasibility run and its Decision says so. |

H1 items not in a milestone: **H1-6** (control egress closure) and **H1-7** (fleet drift report) remain vuoro-cloud platform hygiene, dispatched when a Forgejo session is open; H1-7 is a stated input to M3-3. **H1-8** (status docs) is a `reconcile-project-contracts` pass to run after generation 47 promotes. None of the three is ordered against a milestone.

---

### R3. In-place corrections to H1-4 and H3-3

Both original items are annotated below where they stand (marked **Revised 2026-09-27**). In summary:
- **H1-4** no longer infers hosted sessions from `mcp_exchange` counts or Routine PRs. It counts a defined cohort: expected invocations → observed runs → evidence-bearing runs → fully resolvable outcomes, and reports unknown coverage explicitly. Retries count once per expected invocation.
- **H3-3** becomes an **activity and denial report**: observed calls and recorded denials per runtime and model family. It does not measure vendor quota consumption, and parking is a work-level disposition, not a lease state (decided in R4, lease semantics 7).

---

### R4. Decisions (decided by the operator 2026-09-27)

The operator decided all four decisions and the seven #2520 lease semantics on 2026-09-27, with refinements recorded below. R4 is sufficiently decided to start M2-1 and the #2520 conformance work in parallel. The option analysis for Decision 1 is kept as the record of why A was chosen.

**Decision 1 — decided: A. sprintctl owns the effect-intent lifecycle. M2-1 can proceed.** An EffectIntent is not execution state. It is work-domain state describing a proposed consequence of work, so it belongs beside runs, claims, settlement and the work event ledger.

- **Ownership rule.** The authority that owns work settlement also owns the effect-intent lifecycle. Vuoro transports and exposes intents; it does not independently own their state.
- **Operations** (sprintctl / work authority): `effect.propose`, `effect.get`, `effect.list_proposed`, `effect.accept`, `effect.reject`, `effect.mark_applied`. Vuoro provides adapters and tools over those operations. The store goes into a sprintctl schema after 18 (schema 18 is the lease tables).
- **Same path, different authority.** The operations reuse the authenticated served-shell transport and identity model, but they introduce distinct authorization capabilities: `work.effect.propose`, `work.effect.accept`, `work.effect.reject`, `work.effect.mark-applied`. Otherwise a principal allowed to manipulate ordinary work state could inherit acceptance authority. (This corrects f4c8b57's "`accept` needs no new auth path".)
- **Acceptance binding.** Acceptance binds `intent_id`, `intent_revision`, `canonical_intent_digest`, `acceptor_principal`, `acceptor_policy_version` (when policy acceptance exists) and a timestamp. This handles the public-plane tampering issue from the architecture review, and it resolves the independent review's point that M2 left the acceptor self-asserted until M3-6: the acceptor is an authenticated principal holding `work.effect.accept`.

| Option | What it means | Outcome |
|---|---|---|
| **A. sprintctl, the work owner** (chosen) | Intents live beside the work, runs, claims and the ledger they refer to. The reconciler's `IntentSource` is a served-shell client. | One authority for work state and intent state, so proposal acceptance and work settlement cannot drift apart; the idempotency ledger keyed by `(workspace, principal, tool, key)` (sprintctl#97) is reused; the served-shell transport is reused with distinct `work.effect.*` capabilities. Cost: a sprintctl schema change (after 18) and release; the served authority must roll before the edge can list the tools. |
| **B. vuoro-service adapter with its own table** | Faster to ship inside vuoro; no sprintctl release. | A second lifecycle authority next to the work owner; the contract's "each item's ledger lives with its record owner" (§5 L98) is bent. Not chosen. |
| **C. Homelab-held intents (file or Git)** | Nothing new served. | Fails TS-1's "stores and serves": the cloud cannot `get_effect`. Rejected. |

**Decision 2 — decided: M1's required verification profile is `checked`.** `checked` is the lowest profile that proves anything beyond "the actor says it succeeded". The profiles are modelled as capabilities, not as a numeric ladder:
- `self-reported`: the actor reports the outcome.
- `checked`: configured deterministic checks passed.
- `role-separated`: checks were evaluated by a principal in a verifier role.
- `identity-separated`: the verifier principal differs from the worker principal.
- `human-authorized`: a named human authorization exists.

They are not a simple strictest-wins ordering unless every stronger profile genuinely includes the weaker requirements; `human-authorized` and `identity-separated` may turn out to be orthogonal dimensions. For now the authority recognizes `self-reported` and `checked`, and rejects unknown profile identifiers rather than silently treating them as weaker.

**Decision 3 — decided: same workspace and repository binding, `work:read`; a different identity is allowed.** A successor is eligible when `successor.workspace_id == predecessor.workspace_id`, `successor.repo_binding == predecessor.repo_binding`, and the successor holds `work:read`. A different principal, client or grant is legitimate. **Continuation transfers context, not authority**: the successor does not inherit the predecessor's authority, and later operations that need `work:write`, `effect:propose` and so on need the successor's own grant.

**Decision 4 — decided: dedicated canary repository and a reconciler-specific host key.** The repository is `vuoro-e3-canary`. The signing key is generated on the reconciler host as a reconciler identity: identity **`vuoro-reconciler-e3-canary`**, scoped to repository **`vuoro-e3-canary`** only, used for effect-application signing only, and rotatable independently of host and operator keys. A host-held key is fine for the canary; no HSM.

**#2520 lease semantics (normative contract).** These are the contract the work authority's lease conforms to. Where the shipped 0.9.0 lease differs, the difference is follow-up work (see the conformance note below), not a change to the contract.

1. **Expiry is evaluated synchronously by the authority.** There is no sweeper, scheduler or expiry worker. Lease validity is evaluated whenever an operation touches the claim: claim, heartbeat, resume, report_outcome, settle, takeover. Initial defaults: `ttl` 10 minutes, `heartbeat_interval` 2 minutes. They are authority configuration, not per-workspace (a bounded workspace override may come later). `expires_at = last_heartbeat_at + ttl` is derived state: nothing runs at `expires_at`, and the claim becomes stale the next time somebody asks.
2. **Takeover: a stale lease may be claimed on demand without operator reassignment.** B requests; the authority evaluates A's lease as stale; one CAS transitions ownership (for example generation 17 → 18, holder B). The authority records `work.claim.taken_over` with `previous_claim_id`, `previous_principal`, `previous_generation`, `previous_last_heartbeat`, `new_claim_id`, `new_principal`, `reason = stale_lease`. Vuoro never decides that B should take over: B asks, and the work authority decides. Explicit operator reassignment may exist later as a separate operation.
3. **Stale completion: reject settlement, retain the result.** A late A must never settle after B took over. The stable machine code is `CLAIM_SUPERSEDED`, not `LEASE_EXPIRED`, because expiry alone is not fatal (A can resume if nobody else has claimed). The response is `{code: CLAIM_SUPERSEDED, claim_id, current_generation, reported_generation}`. A's outcome is retained as evidence (`outcome.reported`, `disposition = stale`, `settlement_effect = none`). A's computation survives; A's authority does not.
4. **Workers report outcomes; the record owner settles work.** `complete_work` becomes `report_outcome(...)` where feasible, because `complete_work` implies that the caller performs the transition. The authority checks whether the claim is still current, whether the verification profile is satisfied, whether the required evidence is present and whether the settlement transition is legal, then settles or retains a non-settling outcome. It recognizes `self-reported` and `checked` and rejects unknown profile identifiers.
5. **Same-principal restart resumes only while ownership remains valid.** The same workspace, principal, binding, tool and idempotency key resolve to the same run and claim identity. Case A (lease valid): resume and heartbeat. Case B (lease stale, nobody took over): the same principal **reactivates the existing claim and generation**, because nothing contested ownership. Case C (another principal took over): `CLAIM_SUPERSEDED`; the old idempotency key cannot resurrect the claim. Idempotency recovers identity, not superseded authority.
6. **Shared ledger protocol (H1-9, now).** The key is `(workspace_id, principal_id, tool, key)` and the protocol returns a typed record: `begin(workspace_id, principal_id, tool, key, request_digest) -> LedgerEntry`. The same tuple with the same request digest is the same logical operation and result; the same tuple with a different digest is `IDEMPOTENCY_KEY_REUSED`. One behaviour suite covers run registration, claim acquisition, effect proposal and (where appropriate) effect acceptance.
7. **`parked` is not lease state.** A lease answers who currently has authority to work the item; parking answers why nobody is proceeding. On a recorded denial: `work.disposition = parked`, `reason = <denial ref>`, and the claim is released (or naturally inactive). M3-7 consumes a work-level disposition or event, not lease semantics.

**Resulting lease model.** Claim → ACTIVE. Heartbeat keeps it ACTIVE. Report outcome → the authority evaluates lease and verification → SETTLED. No heartbeat → nothing happens. Another actor claims → the authority observes the stale lease → CAS takeover → the old claim is SUPERSEDED. Deliberately absent: **no scheduler, no expiry daemon, no retry worker, no assignment loop, no supervisor.** The authority evaluates its own state only when asked, which keeps TS-1 clean.

**Invariants.**
- **INV-L1 — A lease grants authority, not ownership of the result.** Results submitted under a stale or superseded lease may be retained as evidence but cannot settle work.
- **INV-L2 — Idempotency restores identity, never superseded authority.** A restarted actor may resume its existing claim only while no later claim has displaced it.
- **INV-E1 — An accepted effect is immutable.** Acceptance binds the exact canonical effect-intent revision and digest; modification requires a new proposal.

**Conformance of the shipped 0.9.0 lease.** #2520 shipped (sprintctl 0.9.0 / sprintctl#98, vuoro#141, vuoro-service 0.1.77) before these semantics were decided. The shipped behaviour stays as released; the contract above is normative and the deviations are follow-up work. Known deviations:
- **Default timing.** Shipped default TTL is 300 s; the contract is `ttl` 10 min with `heartbeat_interval` 2 min.
- **Same-principal restart.** Shipped: a stale own lease is resumed under a **new lease id** (same run id). Contract (semantics 5): reactivate the same claim and generation.
- **Stale-completion code.** Shipped: `lease-superseded` (HTTP 409), without generations in the response. Contract (semantics 3): `CLAIM_SUPERSEDED` with `claim_id`, `current_generation`, `reported_generation`.
- **Operation naming.** Shipped: `work.lease.complete-v1` (surfaced as `complete_work`). Contract (semantics 4): `report_outcome`.
- **Verification profile model.** Shipped: a "strictest-wins" ordering of profiles. Contract (Decision 2): capabilities, not a numeric ladder; unknown identifiers rejected.
- **Shared ledger protocol (H1-9).** Contract (semantics 6): a typed `begin(workspace_id, principal_id, tool, key, request_digest) -> LedgerEntry` with `IDEMPOTENCY_KEY_REUSED`, one behaviour suite across run registration, claim acquisition, effect proposal and (where appropriate) effect acceptance. Assessed: the ledger key and digest conform; the typed `begin` shape and one shared suite do not yet, and the published wire code stays `idempotency-conflict` (documented as `IDEMPOTENCY_KEY_REUSED`).

The conformance analysis (2026-09-27) found lease safety holds in the sprintctl runtime (INV-L1 and INV-L2 conform; vuoro's in-memory `lease.py` reference spec still discards a stale completion, contrary to INV-L1, and is corrected under #2540: a late or superseded report is retained and never settles; idempotency never restores superseded authority) and one gap outside the list above: **verification profiles stricter than `checked` are accepted but not enforced**, so any `work:write` decision can settle an item whose contract names `role-separated`, `identity-separated` or `human-authorized`. Tracked as:
- **#2539** (priority 1): verification profiles as enforced capability sets; folds in #2528 and #2529.
- **#2540** (priority 2): align the lease with semantics 1–5 before `vuoro:work.claim` is granted (no client consumes the names yet, so no migration).
- **#2541** (priority 2): M2-1, sprintctl-owned effect intents with `work.effect.*` capabilities and digest-bound, immutable acceptance (INV-E1).
- **#2542** (priority 3): the shared ledger protocol (H1-9).
- **#2543** (priority 3): the work-level `parked` disposition (M3-7).

Two related agentops follow-ups, both folded into #2539, were filed earlier: **#2528** (an awaiting-verification report does not protect the item, and the report never receives the verifier's decision) and **#2529** (releasing an item to pending leaves its lease active; heartbeat versus maintenance activation race).

---

### R5. Costs and counting, corrected

- **The 2-4-week horizon and the USD 250 estimate are provisional.** They were sized for the original ten dispatches and are kept only as the order of magnitude to revisit after M1.
- **Dispatch counting.** §4 counted ten rows as ten dispatches while §3 sized several of them as multiple dispatches (L = 4-6, M = 2-3). Re-counting §4 with §3's own mid-points: H1-10 (1) + H1-9 (1) + H1-3 (1) + H1-1 (5) + H1-5 (2-3) + H1-4 (1-2) + H1-2 (2-3) + H1-8 and H1-6 (1 + 2-3) + H2-2 (2-3) + H2-3 and H2-4 (1-2 + 1) is roughly **20-25 dispatches, not 10**.
- **M1 alone**, as filed in Appendix A: M1-0 (0.5) + M1-1 (1) + M1-2 (2) + M1-3 (1-2) + M1-4 (2-3, plus #2520's own 4-6) + M1-5 (2) is about **9-11 dispatches excluding #2520, 13-17 including it**. (Revised 2026-09-27: #2520 has shipped, so the remaining M1 count is the 9-11, plus the lease conformance follow-ups.) Roughly half are cloud-suitable.
- **What the tick cost does not cover.** The USD 2-3 per lane-loop tick (#2504) prices a bounded implementation tick. It does not price integration (two repos changing together, e.g. sprintctl release then edge composition then vuoro-cloud scope rows), retries (a failed cloud run is paid for and repeated), or releases (vuoro-service versions, generation promotions, served rolls, which are local and operator time, not credit). Treat the cloud-credit number as a floor.
- **Measure, then re-estimate.** M1-3's funnel and the lane check-up record the actual per-item cost; the M2 estimate is written after M1's numbers exist.

---

## 1. Current-state synthesis

**What works (verified in source and tracker).**

- **Public surface, OAuth-authenticated.** vuoro.cloud gateway + control act as OAuth AS/RS; the tenant runtime pod serves MCP through `vuoro-service mcp-serve` (vuoro-mcp-edge). Generation 46 is live with vuoro-service 0.1.76 (sprintctl 0.8.0, work schema 17). Generation 47 (vuoro-cloud `9b2d454`, `b013e29`) grants `vuoro:evidence.record` to the `claude-connector` client and fixes E2 actor attribution (`actor = external_subject`, contract §1).
- **Tools served today:** read bucket `list_ready_work`, `describe_work`; record bucket `register_run`, `append_evidence`, `write_session_note` (`oauth_scopes.py` `MCP_TOOL_SCOPES`). E1 first use is proven (Routine → vuoro#124). The scope registry structurally rejects `vuoro:effect.apply` at import time.
- **Built but not exposed:** `claim_tools.py` (claim/heartbeat/complete, waits on the exclusive durable lease, #2520); `effect_tools.py` `propose_effect`/`get_effect` (vuoro#130) with the tool list suppressed until a durable intent store exists (vuoro#132). `vuoro:work.claim` and `vuoro:effect.propose` stay reserved.
- **Trusted side:** `packages/vuoro-reconciler` (acceptance CLI, opt-in `AutoAcceptConfig` file, hermetic `gitenv.run_git`, signing, provider allowlist, `Vuoro-Run`/`Vuoro-Intent` trailers) exists as a package with tests only: no deployment, no `IntentSource` backend, no credentials. `vuoro-worker` (Managed Agents poller, #2469) is done but "not exercised against the vendor".
- **Evidence model:** RunManifest is first-class (vuoro#122), the run record is the Phase-1 RunManifest, idempotency ledger keyed on (workspace, principal, tool, key) in sprintctl#97.
- **Platform proofs:** D-044 restore drill and live tenant isolation; YubiKey-signed promotions; Flux source verification; digest-pin validation of kustomize output (#2515).

**Edges of what works.**

- Evidence from a hosted runtime can now be *recorded*, but no Routine has yet done so: the tripwire in the target state ("E1 in use with no E2-E4 follow-on, and no session that produced a reconstructable record", target-state.md:150-156) is live and unmet.
- Claims are advisory on the surface; the product's own differentiated scenario (19-PRODUCT-POSITIONING §"intended differentiated scenario", steps 3-6) needs the exclusive lease that #2520 is building.
- Effects are a package with no store, no deployment and no consumer credentials. TS-16 stands unamended; the Wave C in-cluster trusted service is gated on 12 prerequisites (cloud-enablement-plan "Required before slice 1").
- Multi-repository workspaces are refused by the edge (#2518); grants assert the whole project's repo set.

**Debt.**

- vuoro-cloud `IMPLEMENTATION-STATUS.md` on `origin/main` still says gen 44 and "E2 has not started" (line 48) while generation 47 is being promoted from the same branch.
- vuoro PR CI (`.github/workflows/ci.yml`) builds wheels only; the image is a separate publish workflow. The 2026-07-28 `resultType` regression reached generation 44 because only claude.ai (lenient) exercised the edge.
- Control may egress to any host on 443 (`platform/policies/network-policies.yaml:66-72`).
- The tenant controller has no fleet resync; `blocker12-canary` (`vuoro-ws-01m14w25eykc`) is an orphan still on 0.1.52.
- `IdempotencyLedger` protocol still takes `workspace_id` only; principal folding is per-implementation (contract §5 amendment).
- Operator steps are curl commands with a bearer from an allowed source CIDR (GETTING-STARTED "For operators") or browser-console pastes; onboarding gaps 1-5 remain (`docs/plans/2026-09-24-onboarding-ux-gaps.md`, item 3 half done).
- Talos environment has no policy-enforcing CNI; only GitHub OAuth sign-in exists.
- Sprint 559 carries 27 pending items across 16 tracks, several stale (#2502 rollout-c superseded by gen 46; #2479 RunManifest landed in vuoro#122 but is still pending).

**Risks.**

- **Foundation without use.** If E2's record tools are granted but no Routine emits runs, TS-16's control metric stays at zero and the next investment is unjustifiable by its own rule.
- **Two lifecycle owners for intents.** Building the intent store in the wrong place (edge, cluster) re-creates the C1 finding that killed the trusted-service design.
- **Cloud credit is USD 250.** Cloud dispatch is cheap for GitHub-authoritative code (vuoro, agentops), impossible for Forgejo-authoritative vuoro-cloud and for anything holding credentials.

---

## 2. Product direction as inferred

**The one-line promise:** "Keep long-running agent work resumable, and know which result actually counts" (vuoro-cloud `19-PRODUCT-POSITIONING-AND-PROOF.md` §Decision). The technical category is a *local-first operational state and settlement layer*; the companion boundary is "Coordinate the work. Keep control of where it runs."

**Who uses it, today and next.**

1. **The operator's own hosted runtimes** (claude.ai Routines, Claude Code `--cloud` sessions, the claude.ai connector). Target state TS-16 names them: "Cowork, claude.ai, mobile, Routines, cloud sessions, OpenAI Responses". They read ready work, and (from gen 47) record runs and evidence. They may only push unprotected branches and open PRs (cloud-enablement-plan decision 2).
2. **The operator as trusted-side acceptor.** Effects are queued by the cloud and accepted/executed on the homelab (cloud-enablement-plan "Effects: queued intents and acceptance"; reconciler README "Acceptance (TS-16)").
3. **An external user with their own repositories and workers,** invitation-gated, who commissions a repository from a terminal and uses served sprintctl as a real authority "without receiving PostgreSQL or Kubernetes access" (vuoro-cloud README "Primary outcome"). This is the PoC's stated proof and is *not yet attempted*; the threat model lists "Required security gates before external onboarding" (10-THREAT-MODEL §"Required security gates").

**What it is not:** hosted execution, hosted artifact custody, credential custody, a queue, a model router (`14-OPEN-QUESTIONS-AND-NON-GOALS.md` non-goals; TS-1, TS-2; options memo option 7 rejected). Vuoro "stores it, serves it on read, and does nothing else" for an EffectIntent (target-state TS-1).

**Implication for the backlog.** The product increment that matters is not more tools; it is *the settlement scenario running against a hosted runtime with a reconstructable chain from a signed commit back to a run record*. Everything in H1 serves that; H2 widens who can do it; H3 uses the edge's unique vantage point (it sees every runtime) for things nobody else can build.

---

## 3. Backlog proposals

Sizes: S ≤ 1 dispatch, M 2-3, L 4-6, XL a wave. "Cloud" means suitable for `claude --cloud` (GitHub repo, no credentials); "Local" means workstation/devbox; "Operator" means only the operator can do the step. Existing sprintctl items are referenced, not duplicated.

### H1: next 2-4 weeks, hardening and finishing

#### H1-1. Durable EffectIntent store in the work owner, served on read
- **Problem.** `propose_effect`/`get_effect` are built but unlisted (vuoro#132) because no durable store exists; the reconciler's `IntentSource` has no backend. The shared contract says each item's ledger "lives with its record owner, not in the edge" (contract §5) and TS-1 says Vuoro stores and serves intents and does nothing else.
- **Outcome.** An `effect_intent` table and `work.effect.propose/get/list-proposed/accept/reject/mark-applied` operations in sprintctl (**Revised 2026-09-27:** a schema after 18, which is now the lease tables; owner decided as sprintctl in R4 Decision 1) or, if the owner decision says otherwise, a vuoro-service intents adapter. States exactly `proposed|accepted|rejected|applied|failed`; no assignment, scheduling, retry, expiry (TS-1's five verbs). `accept`/`reject`/`mark-applied` are *not* on `MCP_TOOL_SCOPES`; they are served-shell operations the trusted side calls. Edge lists the propose bucket once `context.intents` is durable; vuoro-cloud adds the E3 scope rows already stubbed in `oauth_scopes.py`.
- **Repos.** sprintctl, vuoro (edge composition, reconciler `IntentSource` over the runtime shell), vuoro-cloud (scope rows, `is_mutating_authority`).
- **Depends.** #2480 (authoritative evidence capture decision) should be closed first or in the same brief; #2517 done. Not on #2520.
- **Size.** L. **TS-16.** Compliant by construction: cloud reaches `propose`/`get` only; acceptance operations require a trusted-side identity. **Track.** 1551 vuoro-edge. **Dispatch.** Cloud for sprintctl+vuoro code; Local for vuoro-cloud carry and release.

#### H1-2. Deploy the reconciler on the homelab and apply one intent end to end
- **Problem.** The reconciler is tests-only ("E3 builds the package and its tests only: no manifests, credentials or deployment", contract §7). TS-16's promised property, "a verifiable chain from a signed commit back to a run record", has never been produced.
- **Outcome.** A NixOS/systemd unit (gitops-nixos, devbox or workstation) running `vuoro-reconciler` against a served `IntentSource` with a workspace token, a dedicated signing key, and a provider allowlist of one canary repo (`bayleafwalker/vuoro` docs path or a `vuoro-e3-canary` repo). First proof: a Routine proposes a docs diff → operator `accept` → branch, signed commit with trailers, PR. Record as evidence in vuoro (like vuoro#124).
- **Repos.** gitops-nixos (Forgejo), vuoro (docs/evidence), agentops (runbook).
- **Depends.** H1-1. **Size.** M. **TS-16.** The whole point; credentials stay homelab-side. **Track.** 1551. **Dispatch.** Local + Operator (signing key, tokens).

#### H1-3. First evidence-emitting Routine (make gen 47 do something)
- **Problem.** The record tools are granted in gen 47 but no caller uses them; the target-state tripwire is on "no session that produced a reconstructable record" (target-state.md:150-156). `docs/runbooks/cloud-routine-authoring.md` only requires a verdict PR.
- **Outcome.** Update the runbook: a Routine must `register_run` at start (with RunManifest fields), `append_evidence` for its findings, `write_session_note` at end, and put `Vuoro-Run: <run_id>` in the PR body. Convert the existing E1 review Routine to this shape. Add a small conformance check in agentops (`scripts/`) that a Routine PR carries a resolvable run id.
- **Repos.** agentops, vuoro (Routine prompt lives with the report repo).
- **Depends.** gen 47 promoted. **Size.** S. **TS-16.** Record bucket only. **Track.** 1551. **Dispatch.** Cloud (the Routine itself is the test).

#### H1-4. Hosted-runtime reconstructability metric (TS-16's control question, computed)
- **Problem.** TS-16 defines the control question as "what proportion of automated activity is reconstructable; for hosted runtimes today it is zero" and nothing computes it.
- **Outcome.** A derived read-only query (agentops `scripts/`, beside `cost_per_release.py`) that joins gateway `mcp_exchange` counts / Routine PRs (GitHub API) against run records, and reports: hosted sessions observed, sessions with a run record, runs with ≥1 evidence entry, PRs with a resolvable `Vuoro-Run` trailer. Weekly number in the lane check-up.
- **Repos.** agentops. **Depends.** H1-3 for a non-zero result. **Size.** S-M. **TS-16.** Read-only. **Track.** 1568 target-state-path (pairs with #2486). **Dispatch.** Cloud (GitHub reads + served `work.read`), or Local if gateway logs are needed.
- **Revised 2026-09-27 (operator review, point 4).** The outcome above is superseded: joining `mcp_exchange` counts and Routine PRs cannot infer hosted sessions (silent failures and sessions that never contact Vuoro are absent; retries inflate request counts). The metric is a funnel over a **defined cohort**: expected invocations → observed runs → evidence-bearing runs → fully resolvable outcomes, with **unknown coverage reported explicitly** and retries counted once per expected invocation. Filed as M1-3 (Appendix A.3).

#### H1-5. Strict-client MCP conformance in vuoro PR CI, and build the image on PR
- **Problem.** The `resultType`/`cacheScope` regression reached production because claude.ai is lenient and Claude Code strict (cloud-enablement-plan "Why the 2026-09-25 verdict was no"). `ci.yml` builds wheels only; the image workflow is release-time.
- **Outcome.** A CI job that (a) builds the `Dockerfile` image, (b) starts `vuoro-service mcp-serve` with a test assertion signer, and (c) runs a strict MCP 2026-07-28 client (schema-validated `tools/list`, `tools/call` envelopes, error shape) plus the D-044 isolation test against the container. Fail on any envelope deviation.
- **Repos.** vuoro. **Depends.** none. **Size.** M. **TS-16.** n/a (test-only). **Track.** 1466 tests. **Dispatch.** Cloud.
- **Note 2026-09-27.** Part (a), the image build on PR, shipped in vuoro#135 (merged 2026-09-27); M1-2 covers (b) and (c).

#### H1-6. Close control's 443-anywhere egress and add policy deny-tests
- **Problem.** `platform/policies/network-policies.yaml:66-72` lets control reach any host on 443 (Wave B item, unowned in the tracker). Required-before-slice-1 item 9 asks for the CONNECT/SNI, metadata, node-local and IPv6 deny-test gaps to be closed.
- **Outcome.** Enumerate control's real egress (GitHub OAuth, CNPG, Cloudflare), pin to CIDR `ipBlock`s rendered by a CI job from published ranges, and add a kind-based deny-test suite for every policy (metadata 169.254.169.254, node-local, IPv6). Record the residual (k3s kube-router cannot do FQDN).
- **Repos.** vuoro-cloud. **Depends.** none. **Size.** M. **TS-16.** Reduces blast radius of a control compromise; prerequisite for any Wave C. **Track.** 1551 (or a new `vuoro-cloud-platform` track). **Dispatch.** Local (Forgejo; kind on workstation).

#### H1-7. Tenant fleet resync and drift report in the controller
- **Problem.** "The controller has no fleet resync. A tenant moves to the new runtime at its next reconcile event" (IMPLEMENTATION-STATUS gen 34); `blocker12-canary` is still on 0.1.52 with legacy LOGIN roles. The in-flight design pass owns *retirement*; this item is the *detection* half it needs.
- **Outcome.** A periodic controller pass that compares each workspace's live runtime digest/schema to `config/compatibility.json`, emits an audit event per drifted tenant, exposes the list on `/admin`, and (flag-gated) enqueues an outbox reconcile. The canary becomes the first drift row and the retirement design's first input.
- **Repos.** vuoro-cloud. **Depends.** none; feeds the in-flight retirement design. **Size.** S-M. **TS-16.** n/a. **Track.** new `vuoro-cloud-ops` or 1551. **Dispatch.** Local.

#### H1-8. Reconcile vuoro-cloud status docs to generations 45-47
- **Problem.** `IMPLEMENTATION-STATUS.md` header and line 48 ("E2 has not started") are two generations stale; `GETTING-STARTED.md` step 4 predates the E2 tools; `docs/plans/2026-09-24-onboarding-ux-gaps.md` item 3 is half-marked.
- **Outcome.** A `reconcile-project-contracts` pass: status header, generation 45-47 entries, E2/E3 state, the still-open list, and a "what a Routine may do today" table mirroring `MCP_TOOL_SCOPES`.
- **Repos.** vuoro-cloud. **Depends.** gen 47 promoted. **Size.** S. **Track.** 1469 process. **Dispatch.** Local (Forgejo).

#### H1-9. Fold the principal into the shared `IdempotencyLedger` protocol
- **Problem.** Contract §5 amendment: the protocol still takes `workspace_id` only; each ledger folds the principal ad hoc. That is a cross-principal replay risk waiting for the next implementer.
- **Outcome.** Protocol takes `(workspace_id, principal_id, tool, key)`; `InMemoryIdempotencyLedger`, the sprintctl-backed ledger and the intent-store ledger (H1-1) all pass one parametrized behaviour test.
- **Repos.** vuoro, sprintctl. **Depends.** none; do before H1-1 lands. **Size.** S. **Track.** 1551. **Dispatch.** Cloud.

#### H1-10. Tracker hygiene for sprint 559
- **Problem.** #2502 (roll to 0.1.71) is superseded by gen 46; #2479 (RunManifest) shipped in vuoro#122 but is pending; #2466 is done while #2520 carries its claims half; the 1551 track mixes decisions (#2480, #2482) with follow-ups (#2518, #2519).
- **Outcome.** Close or re-scope the stale items with notes citing the shipping PR; move #2480/#2482 into a decision brief that H1-1 consumes.
- **Repos.** none (served sprintctl). **Size.** S. **Track.** 1469. **Dispatch.** Local (needs served write; not a cloud task).

### H2: the next product increment

#### H2-1. Exact-subset repository grants (consent, assertion, edge selection)
- **Problem.** #2518 records the edge symptom (refuses >1 repo_id). The cause is that the gateway forwards every project repository and there is no grant-level subset (options memo option 4; Required-before-slice-1 item 3: "bind effects grants to exact repository subsets").
- **Outcome.** OAuth grant migration with a repository subset; consent screen lists repositories; assertion carries `repo_ids` = subset; every tool call names one repository from it; run/claim/evidence/intent bound to that repository; tests that one permitted repo cannot select a sibling. #2518 becomes the edge half of this item.
- **Repos.** vuoro-cloud (migration, consent UI, `security.py`, `control.py`, `gateway.py`), vuoro (edge schemas). **Depends.** gen 47; H1-1 for intents. **Size.** L. **TS-16.** Narrows blast radius; unlocks multi-repo Routines without workspace-wide authority. **Track.** 1551. **Dispatch.** vuoro half Cloud; vuoro-cloud half Local.

#### H2-2. The settlement scenario as a live conformance test
- **Problem.** The product's differentiated scenario (worker 1 disappears, worker 2 takes over, worker 1's late result is kept as evidence but rejected for settlement; 19-PRODUCT-POSITIONING steps 1-8) is "a target conformance scenario, not a claim". #2520 delivers the lease; nothing proves the scenario end to end over the public surface.
- **Outcome.** Two hosted callers (Routines or `--cloud` sessions) on the kotona workspace: A claims, heartbeats, stops; B takes over via the lease; A's `complete_work` fails with the dead-lease code and is recorded as evidence; B's completes; dependent item becomes ready. Recorded as an evidence packet in vuoro and cited from the landing page's proof section.
- **Repos.** vuoro (test harness + evidence), agentops (Routine prompts). **Depends.** #2520 shipped and granted. **Size.** M. **TS-16.** Coordinate + record only. **Track.** 1551 / 1518. **Dispatch.** Cloud for the callers; Local to grant `vuoro:work.claim`.

#### H2-3. Pending intents in the operator's resume surface
- **Problem.** Acceptance is a CLI (`vuoro-reconciler accept <id>`) the operator must remember to run; sprintctl's `next-work --explain` already has a `checkpointed_unacked` bucket (#2474). Queued intents will otherwise rot unseen.
- **Outcome.** A `proposed_intents` bucket on `next-work`/`session resume` (served, read-only), listing intent id, run, repository, title, proposer, age, with the exact `vuoro-reconciler accept ...` line. Optional desktop/Signal notification via the existing alert-delivery proof (D15).
- **Repos.** sprintctl, agentops (render). **Depends.** H1-1. **Size.** S-M. **TS-16.** Read-only view. **Track.** 1460 handoff / 1518. **Dispatch.** Cloud.

#### H2-4. First auto-accept policy: docs-only diffs, measured
- **Problem.** Auto-accept exists (`AutoAcceptConfig`) but has no first policy. Operator fatigue on trivial diffs will erode the approval signal that matters (trusted-service design §8 Q4 reasoning survives even though the amendment was rejected).
- **Outcome.** One policy `{workspace: kotona, repository: vuoro, effect_kinds: [unified_diff], path_globs: ["docs/**"]}`, off → on by operator, every acceptance recording `{kind: policy, id, version, config_digest}`. Measure proposal→PR latency for policy vs operator acceptance over two weeks.
- **Repos.** gitops-nixos (config file), agentops (runbook). **Depends.** H1-2. **Size.** S. **TS-16.** Within the four conditions in the cloud-enablement plan (off by default, trusted-side only, asynchronous, recorded acceptor). **Track.** 1551. **Dispatch.** Operator.

#### H2-5. Cloud build lane: pinned, credential-free test/build environment
- **Problem.** Wave B names it; the options memo ranks it #2; no tracker item exists. Cloud workers currently improvise setup, and `claude --cloud` costs credit on every re-derivation.
- **Outcome.** `scripts/cloud-setup.sh` in vuoro and agentops (uv + pinned Python, `uv sync --all-packages`, no network after setup), a documented Claude Code cloud environment referencing it, and a run-once Routine that executes `uv run pytest` for vuoro on a schedule and opens a verdict PR per the runbook. Records USD per run.
- **Repos.** vuoro, agentops. **Depends.** none. **Size.** M. **TS-16.** No credentials in the lane by design. **Track.** 1551 (or 1466). **Dispatch.** Cloud to author; Operator to register the environment.

#### H2-6. External onboarding gate closure and the first non-operator tenant
- **Problem.** The PoC's primary outcome is an external user completing the onboarding loop "without operator intervention" (vuoro-cloud README). The threat model lists the gates required before external onboarding; the onboarding-gaps doc lists five UX blockers; a second tenant has never been provisioned for a real person.
- **Outcome.** A checklist run against 10-THREAT-MODEL §"Required security gates before external onboarding" with evidence per gate; fix onboarding gaps 1, 2, 4, 5 (signed-out dashboard, member redirect, provisioning progress, bound-repo confirmation); bind the invitation code to the requester's GitHub login (gap 3 residual); then onboard one invited external user to a fresh workspace with their own repository and record it as `docs/evidence/`.
- **Repos.** vuoro-cloud. **Depends.** H1-7 (drift), backups (#2428 dated checks), in-flight retirement design (so a test tenant can be removed). **Size.** L. **TS-16.** External principals only reach `work:read`/`work:evidence` through the same scope table. **Track.** new `onboarding`. **Dispatch.** Local + Operator (invitation, provisioning supervision).

#### H2-7. Substrate-fired Routines: trusted side pushes ready work to the cloud
- **Problem.** Today a Routine decides for itself what to look at. The edge doc notes `POST /v1/claude_code/routines/{id}/fire` (edge doc §6 "One intake path worth knowing") as a clean push path, and TS-2 says the dispatcher chooses what runs, not the substrate.
- **Outcome.** A homelab-side dispatcher step (agentops lane-loop or a small `vuoro-fire` script) that, for items tagged `cloud-eligible` in `next-work`, fires a Routine with the item id and repository; the Routine registers a run, does the work on a `cloud/<run>/*` branch, and opens a PR. The fire payload is treated as untrusted on the Routine side. The Routine bearer lives only on the homelab.
- **Repos.** agentops (dispatcher), vuoro (Routine prompt). **Depends.** H1-3; #2520 for the claim. **Size.** M. **TS-16/TS-2.** Substrate records, dispatcher chooses; no credential crosses. **Track.** 1566 pipeline-rebuild or 1551. **Dispatch.** Local (holds the Routine token).

#### H2-8. Second identity provider for admin/operator sign-in (Authentik OIDC)
- **Problem.** Only GitHub OAuth exists; 14-OPEN-QUESTIONS left "users without GitHub accounts" undecided; the in-flight design separates admin and user identities. The homelab already runs Authentik (referenced by #2395).
- **Outcome.** A generic OIDC provider option in control (`/auth/oidc/start`, PKCE, same `principal_id` epoch scheme), used first for the *admin* identity so operator actions stop depending on a GitHub session. GitHub remains the user sign-in.
- **Repos.** vuoro-cloud, appservice (Authentik provider). **Depends.** in-flight admin/user identity design; #2482 principal binding decision. **Size.** M. **TS-16.** Strengthens the trusted-side actor's authentication (reconciler README "Trust assumption" says `--operator` is self-asserted today). **Track.** 1551. **Dispatch.** Local.

### H3: extended innovation paths

#### H3-1. Comment and review intents through the homelab reconciler (no in-cluster executor)
- **Opportunity.** Wave C's `forge_comment_pr` needs 12 prerequisites because it puts provider credentials on the cluster. The homelab reconciler already holds provider credentials and already does provider calls (open PR). A second `EffectIntent` kind, `forge_comment` `{run_id, repository, pr_number, body ≤ 8 KiB}`, executed by the same reconciler after acceptance or a policy, gives Routines a way to leave review comments with a blast radius of "comments on allowlisted repos" and zero new cluster surface.
- **Outcome.** Intent kind + edge validation (mention/URL allowlist rules from trusted-service design §3 table row 1), reconciler executor, auto-accept policy `effect_kinds: [forge_comment]`. Forgejo reach comes for free because the homelab can reach `git.apps.kotona.app`.
- **Repos.** vuoro, sprintctl (intent kind), gitops-nixos (policy). **Depends.** H1-1, H1-2. **Size.** M. **TS-16.** Compliant: proposed on the surface, applied on the trusted side. Makes most of Wave C unnecessary. **Track.** 1551. **Dispatch.** Cloud for code; Operator for token.

#### H3-2. Provenance chain resolver: `vuoro provenance <sha>`
- **Opportunity.** TS-16 promises "a verifiable chain from a signed commit back to a run record naming runtime, model and profile revision ... recorded and reconstructable, not attested". Once H1-2 produces commits with `Vuoro-Run`/`Vuoro-Intent` trailers, nothing resolves the chain.
- **Outcome.** A `vuoro-client` subcommand (or agentops script) that takes a commit, verifies the reconciler signature, reads the trailers, fetches intent → run → RunManifest → evidence digests through `work.public.*`, and renders one document. A GitHub check on reconciler PRs that the chain resolves. Wording enforced: "reconstructable", never "attested".
- **Repos.** vuoro, agentops. **Depends.** H1-2. **Size.** M. **Track.** 1566 / 1568. **Dispatch.** Cloud.

#### H3-3. Cross-runtime consumption and denial ledger (the edge's unique vantage)
- **Opportunity.** "Your MCP server sees every claim and completion from every runtime. It is the one vantage point you control that spans them all" (edge doc §6). No vendor exposes plan consumption programmatically; E4 (#2472) is parked for lack of signal.
- **Outcome.** Derive per-run, per-runtime, per-model-family activity from `mcp_exchange` logs + run records + `rate_limit_event` evidence appended by callers; a weekly "which runtime did what, and where did denials happen" report; a `parked` marker on a claim when a caller records a family denial (records and parks, never re-dispatches; TS-1). This is the minimal E4 that #2472 says is meaningful only with RunManifest and leases, both of which now exist or are in flight.
- **Repos.** agentops (derived query), vuoro (evidence kind `rate_limit_event`), sprintctl (parked state on the lease). **Depends.** #2520, H1-3. **Size.** M-L. **TS-1/TS-2.** Observe, never route. **Track.** 1551 (folds into #2472). **Dispatch.** Cloud for queries; Local for logs.
- **Revised 2026-09-27 (operator review, point 4 and disposition table).** Renamed **activity and denial report**. Observed calls do not measure vendor quota consumption, so "consumption ledger" is withdrawn: the report lists observed calls and recorded denials per runtime and model family, observationally, and its header says what it does not measure. Placed in M3-7. **Decided 2026-09-27:** parking is a work-level disposition, never a lease state (R4, lease semantics 7).

#### H3-4. Second hosted harness on the same connector (OpenAI Responses / Codex cloud)
- **Opportunity.** TS-16 lists OpenAI Responses as a target runtime; TS-8 requires cross-harness continuation; Codex is already in daily use (71 sessions in the first half of September). The OAuth connector is harness-neutral by design.
- **Outcome.** Register a second pre-registered OAuth client for a Codex/Responses MCP connector, restricted to `work:read` + `work:evidence`; run the H1-3 evidence Routine shape from that harness; prove that a Claude Routine's run can be continued by a Codex session through the ledger (TS-8's second route).
- **Repos.** vuoro-cloud (client registration), agentops (runbook). **Depends.** H1-3; #2484 S8 rehearsal pairs with it. **Size.** M. **TS-16.** Same scope table, new client id; no new authority. **Track.** 1551 / 1460. **Dispatch.** Operator for client registration; Cloud otherwise.

#### H3-5. Settlement view: exceptions and safe next actions in the dashboard
- **Opportunity.** 19-PRODUCT-POSITIONING says "an operator view that surfaces exceptions and safe next actions is the current user-experience promise" and reserves "attention layer" until acknowledgement/escalation are first-class. Onboarding gap 5 asks for a connect-a-client panel. Nothing in the dashboard shows work.
- **Outcome.** A read-only panel per workspace, fed by `work.public.*-v1` through the tenant `/api` proxy: ready items, live leases with age, stale leases, proposed intents, last 20 runs with evidence counts, and one "safe next action" line each (the exact CLI command). No write path from the browser.
- **Repos.** vuoro-cloud (web), vuoro (any missing public read operations). **Depends.** H1-1, #2520. **Size.** L. **TS-16.** Read-only. **Track.** new `settlement-view`. **Dispatch.** Local (Forgejo); UI could be prototyped Cloud in vuoro `site/`.

#### H3-6. Workspace-as-code: repository-held desired state reconciled from the trusted side
- **Opportunity.** Operator-only configuration (auto-accept policies, repository allowlists, effect kinds, bound repositories) is scattered across a JSON file on the homelab, SOPS files and console pastes. 14-OPEN-QUESTIONS already proposes `.vuoro/project.json` as the project descriptor.
- **Outcome.** A `.vuoro/workspace.yaml` in the workspace's primary repository declaring bound repositories, acceptance policies and allowlists; the trusted-side reconciler reads it at a signed commit on the default branch and applies it (policies to its own config; bindings via served admin operations). Changes to it are ordinary PRs, so they are reviewed, signed and reconstructable, and the cloud can only *propose* a change to it as a diff intent that the operator accepts.
- **Repos.** vuoro (reconciler), vuoro-cloud (admin operations), sprintctl. **Depends.** H1-1, H1-2, H2-8 (an authenticated admin actor). **Size.** L-XL. **TS-16.** Keeps configuration authority on the trusted side while making it GitOps-shaped. **Track.** new. **Dispatch.** mostly Cloud for reconciler code.

#### H3-7. Managed Agents worker live proof
- **Opportunity.** #2469 shipped `vuoro-worker` but its `managed_agents.py` is "not exercised against the vendor in this repository's tests". It is the unattended half of TS-16 and the only path that reaches nothing public.
- **Outcome.** Operator registers one Managed Agent; the poller runs on devbox against the internal MCP server; one task registers a run and appends evidence; the run appears in H1-4's metric as a hosted unattended run.
- **Repos.** vuoro (`deploy/poller`), gitops-nixos. **Depends.** H1-3 shape. **Size.** M. **TS-16.** Strictly safer than the public surface. **Track.** 1551. **Dispatch.** Operator + Local.

#### H3-8. Ablation on the hosted path (ExperimentRecord's first real case set)
- **Opportunity.** #2487 wants one real ablation over a committed case set. The evidence-emitting Routine (H1-3) gives a cheap, repeatable, cloud-hosted arm: same prompt, two model families or two skill sets, results as run evidence.
- **Outcome.** Case set = 10 `describe_work` reviews; arms differ by model family; ExperimentRecord binds arms to RunManifest digests; verdict written as a Decision.
- **Repos.** vuoro, agentops. **Depends.** #2487 object definition, H1-3. **Size.** M. **Track.** 1566. **Dispatch.** Cloud (uses the credit for what it is best at).

---

## 4. Sequencing: the next 10 dispatches

> **Superseded 2026-09-27** by the three milestones in "Revision after operator review" (R1) and the corrected counting in R5. Kept as the record of the original sequencing.

| # | Item | Why now | Mode |
|---|---|---|---|
| 1 | **H1-10** tracker hygiene + fold #2480/#2482 into a decision brief | Everything below cites the tracker; the intent store must not be built before the "where does hosted evidence live" decision is recorded. Half a day. | Local |
| 2 | **H1-9** principal in the ledger protocol | Small, unblocks H1-1 and #2520 sharing one ledger contract; a cross-principal replay bug otherwise ships twice. | Cloud |
| 3 | **H1-3** evidence-emitting Routine | Turns gen 47 from a grant into a record; moves TS-16's metric off zero; needed by H1-4, H2-7, H3-4, H3-8. | Cloud |
| 4 | **H1-1** durable intent store (sprintctl + edge composition + scope rows) | The single blocker for everything E3; largest item, so start early; runs in parallel with #2520 in sprintctl on separate units. | Cloud (code) then Local (release, gen 48) |
| 5 | **H1-5** strict MCP conformance + image build in vuoro CI | Protects every later release; the last regression cost a generation. Independent, cheap. | Cloud |
| 6 | **H1-4** reconstructability metric | Makes the tripwire measurable before more E3 investment; also the review packet's headline number. | Cloud |
| 7 | **H1-2** reconciler deployed, one intent applied | First end-to-end TS-16 proof; requires 4. Operator session for keys. | Local + Operator |
| 8 | **H1-8 + H1-6** vuoro-cloud status reconcile and control egress closure | One Forgejo session covers both; egress closure is a slice-1 prerequisite regardless of whether Wave C happens. | Local |
| 9 | **H2-2** settlement scenario live | As soon as #2520 lands: this is the product proof the landing page can cite. | Cloud callers + Local grant |
| 10 | **H2-3 + H2-4** intents in `next-work`, first docs-only auto-accept policy | Closes the loop from proposal to merge-ready PR without the operator polling a CLI; measured. | Cloud + Operator |

Then H2-1 (exact-subset grants) as the next L item, H3-1 (comment intents) as the first innovation slice because it displaces most of Wave C, and H2-6 (external tenant) once drift/retirement exist.

Credit note: dispatches 2, 3, 5, 6 and the code half of 4 are cloud-suitable and small; at observed run costs (USD 2-3 per lane-loop tick, #2504) the ten dispatches fit inside the USD 250 credit with margin. Anything touching Forgejo, keys, or the cluster is local.

---

## 5. Explicitly rejected ideas

- **In-cluster `vuoro-effects` executor as the next step (Wave C slice 1).** Twelve open prerequisites, provider credentials on the cluster, and a Codex review with 1 critical / 8 high findings. H1-2 and H3-1 deliver the same user-visible effects (PR, comment) with credentials that never leave the homelab. Revisit only if a Forgejo effect is needed from a runtime that cannot be reached by the homelab reconciler, which today is none.
- **Amending TS-16 to allow auto-executed "reversible" effects (design §8 Q4a).** Operator rejected on 2026-09-26; the auto-accept policy on the trusted side gives the same ergonomics inside the boundary.
- **An `vuoro:effect.apply` scope, or any tool that performs an effect in-call.** Structurally rejected in `oauth_scopes.py`; the C1 finding.
- **Vending Forgejo/S3/cluster credentials to cloud sessions (options memo option 7).** Critical blast radius; "wrong boundary". Cred-broker's future role is minting tokens for the *trusted side* (reconciler, admin CLI), not the cloud.
- **Vuoro assigning, scheduling, retrying, supervising or expiring intents.** TS-1 names the five verbs that void the not-a-queue resolution. H1-1 deliberately has no TTL and no retry; H2-7's dispatcher does the choosing.
- **Predictive quota routing / model routing in the substrate.** No vendor exposes consumption programmatically (edge doc §6); TS-2 keeps model choice in the harness. H3-3 records and parks only.
- **Static Vuoro PATs in Routines as the default.** Decision 4 in the cloud enablement plan: attended, 5-15 minute read-only exception only.
- **Talos cutover in this horizon.** No policy-enforcing CNI; the cloud-enablement plan scopes slice 1 to k3s. Keep the Talos environment as a target, not a dispatch.
- **Hosted execution tier, hosted artifact custody, pooled runtimes, PyPI publication, open registration.** All listed non-goals or resolved decisions in `14-OPEN-QUESTIONS-AND-NON-GOALS.md`; nothing in the current evidence changes them.
- **Deleting E1 if E2-E4 stall.** Superseded 2026-09-22: "assumption of use"; the response to a met tripwire is to stop investing, not to delete.
- **Replacing GitHub OAuth for users.** H2-8 adds a second provider for the *admin* identity only; user sign-in stays invitation-gated GitHub until an external tenant asks otherwise.
- **A browser-side write path in the dashboard (H3-5 with buttons).** Every mutation of work or effects stays behind an authenticated CLI or served operation with idempotency keys; the dashboard shows the command, it does not run it.


---

## Appendix A. M1 sprintctl filing proposal (filed 2026-09-27 as agentops#2521-#2525)

**Filed 2026-09-27:** A.1 = #2521, A.2 = #2522, A.3 = #2523, A.4 = #2524, A.5 = #2525. Do not file again. The text below is kept as the filing record. Proposed for sprint 559. Track names are the existing ones from `sprintctl item list --sprint-id 559`: `vuoro-edge` (1551), `tests` (1466), `target-state-path` (1568), `handoff` (1460), `process` (1469). Priority follows the sprint's convention (1 is highest; #2479 sits at 1, #2480 at 2). The list is deliberately lean: five items, each a whole deliverable with a pragmatic definition of done, rather than one item per sub-step.

### A.0 Stale items to close or re-scope first

Both verified on 2026-09-27 against what shipped.

**#2502 (track `sprintctl-lifecycle`, priority 3) — roll served vuoro-shared to vuoro-service 0.1.71, then upgrade the CLIs to 0.7.2.** Superseded. Evidence: the served authority now runs generation 46 (sprintctl 0.8.0-era vuoro-service, per #2520's description: "run/evidence half shipped (vuoro#131, sprintctl#97 / 0.8.0, generation 46)") and vuoro `origin/main` is at 0.1.76 (release PR vuoro#133); the item's own step-6 acceptance probe passes today: `sprintctl next-work --sprint-id 559 --explain --json` returns a `checkpointed_unacked` bucket (measured 2026-09-27 from the agentops marker repo, served backend); `sprintctl --version` prints 0.7.4 on this host, past the 0.7.2 target. **Action:** close as superseded with a note citing vuoro#133 and the probe output; re-check the devbox CLI version in the note (only the workstation was measured). #2502 blocks #2484 (edge 917); closing it unblocks S8, which pairs with A.5.

**#2479 (track `pipeline-rebuild`, priority 1) — RunManifest as a first-class object, emitted at session start and referenced from every evidence record.** Partly shipped. Evidence: vuoro#122 "feat(evidence): RunManifest as a first-class object (agentops#2479)" merged 2026-09-23 (`packages/vuoro-evidence/src/vuoro_evidence/run.py:100`, with `tests/test_run_manifest.py`); the E2 edge's `register_run` constructs a `RunManifest` as the run record (`packages/vuoro-mcp-edge/src/vuoro_mcp_edge/record_tools.py:270-274`), which is the emission point for hosted runs. Not shipped: scope items (2) and (3) for the *local* actionq-dispatcher path (one RunManifest at dispatcher session start; a reference on every EvidenceItem it produces). **Action:** re-scope, not close: rewrite the description to the residual (dispatcher emission and entry reference, hosted path done via E2), cite vuoro#122 and vuoro#131 in a note, and keep the dependency edge to #2487. If the operator prefers, close it and file the residual as a smaller item; either way #2487 stays blocked until the residual exists.

**#2520 (track `vuoro-edge`, no priority) — E2b claims behind an exclusive durable lease.** *Shipped 2026-09-27 in sprintctl 0.9.0 (sprintctl#98) and vuoro#141 / vuoro-service 0.1.77; the operator's lease contract (R4) is normative and deviations are follow-up work.* The original proposal (grow #2520's description with a seven-point lease checklist and H1-9 before A.4 depends on it) is superseded: the operator decided the seven lease semantics in R4 as the normative contract, and conformance of the shipped lease, including the shared ledger protocol (H1-9, semantics 6), is follow-up work tracked in sprintctl items, with agentops #2528 and #2529.

### A.1 Evidence-emitting Routine and Routine-PR conformance check

- **Track:** `vuoro-edge` (1551). **Priority:** 2. **Size:** S (1 dispatch, cloud).
- **Title:** M1-1: the E1 review Routine registers a run, appends evidence and links its PR to the run; conformance check for Routine PRs
- **Description:** Repos: agentops (runbook, `scripts/`), vuoro (Routine prompt). Problem: generation 47 grants the record tools but no caller uses them; the target-state tripwire is "no session that produced a reconstructable record" (target-state L150-155). Scope: (1) `docs/runbooks/cloud-routine-authoring.md` requires `register_run` at start (RunManifest fields), `append_evidence` per finding, `write_session_note` at end, and `Vuoro-Run: <run_id>` in the PR body; (2) convert the existing E1 review Routine to this shape; (3) `scripts/routine_pr_conformance.py <pr-number>` resolves the trailer through the public read operations and exits non-zero if the run is missing, has null RunManifest fields, or has no evidence. Acceptance: one real Routine PR in `bayleafwalker/vuoro` passes the script; the script fails on a PR without the trailer. Definition of done: the runbook diff merged, one passing Routine PR linked from a note on this item.
- **Depends on:** generation 47 promoted for the live run (writing the runbook and script does not wait). No tracker edge.

### A.2 Strict-client MCP conformance in vuoro PR CI

- **Track:** `tests` (1466). **Priority:** 3. **Size:** M (2 dispatches, cloud).
- **Title:** M1-2: strict MCP 2026-07-28 client conformance job against the service image on every vuoro PR
- **Description:** Repo: vuoro. Problem: the `resultType`/`cacheScope` regression reached production because claude.ai is lenient and Claude Code strict (cloud-enablement plan L12). vuoro#135 now builds the image on every PR; this item adds the client. Scope: a CI job that starts `vuoro-service mcp-serve` from the vuoro#135 image with a test assertion signer, runs a strict client (schema-validated `tools/list`, `tools/call` envelopes, error shape, `resultType` and `cacheScope` values) and the D-044 isolation test against it, and fails on any deviation. Acceptance: a deliberate one-line envelope regression on a throwaway branch turns the job red; main is green. Definition of done: the job runs on PRs and the red/green demonstration is linked from a note.
- **Depends on:** nothing.

### A.3 Reconstructability coverage funnel over a defined cohort

- **Track:** `target-state-path` (1568). **Priority:** 3. **Size:** S-M (1-2 dispatches, cloud for the script; local if gateway logs are needed).
- **Title:** M1-3: TS-16 coverage metric as a cohort funnel (expected → observed → evidence-bearing → resolvable), with unknown coverage reported
- **Description:** Repo: agentops (`scripts/`, beside `cost_per_release.py`). Problem: TS-16's control question ("what proportion of automated activity is reconstructable", target-state L45) has no computation, and the original H1-4 design (infer sessions from `mcp_exchange` counts and PRs) cannot see silent failures or sessions that never contacted Vuoro, and retries inflate it. Scope: `scripts/reconstructability_coverage.py --since <date>` takes a cohort definition (the Routine schedule and any dispatched cloud sessions) and prints four stages with counts and dropped ids: expected invocations, observed runs (run records bound to the cohort's client and grant), evidence-bearing runs (≥ 1 evidence entry), fully resolvable outcomes (PR or session note whose `Vuoro-Run` trailer resolves and whose evidence digests match), plus `unknown: N` for expected invocations never observed. Retries count once per expected invocation. Acceptance: with one Routine deliberately skipping `register_run`, that invocation appears under `unknown`, not `observed`; the weekly lane check-up quotes the funnel. Pairs with #2486 (S6/TS-7 derived queries): same join through the session binding, different question.
- **Depends on:** A.1 for a non-zero result; runnable before it. No tracker edge.

### A.4 Settlement takeover proof with verification and resume

- **Track:** `vuoro-edge` (1551). **Priority:** 1. **Size:** M (2-3 dispatches: cloud for callers and harness, local to grant `vuoro:work.claim`).
- **Title:** M1-4: the differentiated settlement scenario over the public surface: takeover, stale-result rejection with evidence retained, named verification profile, authoritative settlement, dependent ready, and a restart/resume case
- **Description:** Repos: vuoro (harness, `docs/evidence/` packet), agentops (Routine or `--cloud` prompts). Problem: the product proof contract's scenario (vuoro-cloud 19-PRODUCT L46-53) "is a target conformance scenario, not a claim" (L64); #2520 delivers the lease and nothing proves the scenario end to end. Scope: a re-runnable scripted run of two hosted callers A and B on the kotona workspace: A claims item X and heartbeats, A is killed; B takes over through the lease; A's late outcome report is rejected as superseded (`lease-superseded` 409 on the shipped 0.9.0; `CLAIM_SUPERSEDED` with generations once the R4 conformance follow-up lands) and A's payload is retained as evidence on X; B's result is settled by the authority under the named verification profile `checked` (default per R4 Decision 2), recorded as "accepted under verification profile checked"; dependent item Y appears in `next-work` `ready_items` only after settlement. Restart case: A killed and restarted under the same principal and idempotency key resumes its own claim and completes normally (same run id, one settlement, no rejection; same claim id once the R4 conformance follow-up lands). Acceptance: the evidence packet quotes the tool-call transcripts and the authority's records for all cases; the script re-runs green. Definition of done: packet merged in vuoro `docs/evidence/`, note on this item, and only then may the landing page cite it.
- **Depends on:** #2520 (tracker edge: blocked-by #2520). The harness, prompts and restart case can be built against a local backend before #2520 ships.

### A.5 Minimal cross-harness continuation: successor run linked to its predecessor

- **Track:** `handoff` (1460). **Priority:** 3. **Size:** M (2 dispatches, cloud; operator only if a second OAuth client is registered).
- **Title:** M1-5: `register_run` accepts `predecessor_run_id`; a successor on a different identity reads the predecessor's checkpoint and evidence (TS-8 second route, minimal)
- **Description:** Repos: vuoro (mcp-edge `record_tools.py`, `runs.py`, contract §4 amendment), agentops (runbook). Problem: TS-8 requires continuation across harnesses; the shared contract resolves a run only to "the exact same binding" (§4 L79), so another identity cannot continue a run by resolving it, and registering another OAuth client alone proves nothing. Scope: (1) `register_run` takes an optional `predecessor_run_id`; the edge records the link and refuses it unless the caller's binding shares the predecessor's workspace and repository and carries `work:read` (default per R4 Decision 3); (2) the successor reads the predecessor's session notes and evidence through the existing read tools, the predecessor unchanged; (3) `describe_run` shows the link; (4) amend contract §4 with the successor rule. Acceptance: Routine run R1 writes a session note and stops; a session on a different client identity (second pre-registered client if available, else a second principal) registers R2 with predecessor R1, reads the note, appends evidence, and `describe_run R2` shows the link; a caller outside R1's workspace gets `run-not-found`. Definition of done: tests for both cases in mcp-edge plus one live transcript linked from a note. Pairs with #2484 (S8 cross-harness leg): S8 rehearses the checkpoint route, this proves the ledger route.
- **Depends on:** nothing hard (E2 run handles shipped in vuoro#131). No tracker edge.

### A.6 Not filed in M1

- H1-9 is R4 lease semantics 6; filed 2026-09-27 as **#2542**. H1-10 is A.0 itself and needs no item.
- H1-6, H1-7, H1-8 (vuoro-cloud egress, drift, status docs) are platform hygiene outside the milestones; file them when a Forgejo session is scheduled, under `vuoro-edge` or a new `vuoro-cloud-platform` track.
- Everything in M2 waits for R4 Decision 1 to be recorded before M2-1 is filed; M2-3 to M2-6 can be filed alongside it. **Decision 1 was recorded 2026-09-27 (A); M2-1 is filed as #2541.**
