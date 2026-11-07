---
status: rejected
date: 2026-11-07
decided_by: operator
reason: "Over-weighted retiring and not building tools on the basis of usage notes, which is not the relevant reason for this ecosystem. No retirement or not-build ruling in it is adopted; tools are not retired, archived or deleted because of low usage or dormancy."
retained_as: source material only; must not be cited as direction
original: "/projects/dev/_artifacts/deep-research/reports/Agentic substrate goal state.md"
---

> **REJECTED (2026-11-07, decided by the operator).** This plan over-weighted retiring and not building tools on the basis of usage notes, which is not the relevant reason for this ecosystem. None of its retirement or not-build rulings are adopted, and no tool or repo is retired, archived or deleted because of low usage or dormancy. Retained as source material only; do not cite it as direction. Archived copy: `/projects/dev/agentops/docs/plans/archive/2026-11-07-rejected-opus-goal-state-plan.md`.

# Agentic substrate goal state (2026-11-07 to ~2027-11)

Planning oracle output, 2026-11-07. Read-only synthesis of the landscape report and its five research notes, plus origin/main reads of the agentops target state, the Vuoro product direction (with the 2026-10-29 amendment), the operated-service plan, the KAOS 2028 roadmap and model-routing. Labels used throughout: **[F]** fact with source, **[I]** inference, **[B]** bet. Nothing here is an adopted decision. Each item is a proposal for the declared owner to accept, revise or reject.

**How this relates to existing plans.** The KAOS roadmap (`agentops/docs/plans/agentops/2026-10-18-kaos-2028-roadmap.md`, G00-G12) and the operated-service plan (`.../2026-10-29-operated-agentic-service.md`, stages D0-D5) already define the two-year goals and the service stages [F]. This document does not replace them. It picks the 12-month slice, names a single owner for each seam, makes build-versus-adopt rulings, and adds the connective layer that the landscape review found missing: durable plan state, one record per attempt, a release train, and operator gates handled as work.

**Horizon wording.** The estate plan says "Don't formalise the planning horizons ... no delivery dates" (`2026-10-17-estate-evolution-plan.md` lines 1-9) [F]. In this document H1, H2 and H3 are dependency tiers with indicative windows, not commitments. That reading resolves the tension, so no escalation was needed.

---

## 1. North star and goal-state properties

**North star.** One operator states an objective. Native harnesses (Claude, Codex, OpenCode Go) carry it across sessions, hosts and providers under Sovite-admitted attempts. A protected-side owner accepts the exact artifact by digest, and anyone can later reconstruct the route, the cost, the evidence and the acceptance from one read. All of this runs on a signed, versioned distribution built mostly from provisioned products, and the substrate develops itself this way.

This is G00 of the KAOS roadmap ("useful durable delegation with capacity growing faster than supervision") made operational for the first year [I].

| # | Property | Cheap verifiable check |
|---|---|---|
| P1 | **Plan state is durable and registered.** No live programme state sits only in untracked folders, `/tmp` or handoff prose. | A generated register (`plan-register --check` in agentops CI) reports zero docs with an unknown status and zero live programmes without `work_ref`. `git status --porcelain docs/dispatch/handoffs _artifacts/agentops/ecosystem-resume-*` is empty after each closeout. |
| P2 | **Each responsibility has one owner.** Every cross-tool schema id and shared noun (lease, fence, attempt, receipt, qualification) maps to exactly one owner. | A generated schema catalog fails CI when a `name/vN` id appears with two owners, or when an unqualified shared noun appears in a new contract. |
| P3 | **One record per attempt** (TS-17 made concrete). Each accepted outcome joins: route requested, observed model/harness binding, session, cost snapshot, EvidenceSet digest, Decision and effect receipt, with missing links named. | A derived query over the last 30 accepted outcomes returns coverage = complete / total with failure classes. Target ≥80% by H2 end, with the denominator printed (TS-20). |
| P4 | **There is a release train.** Source becomes a signed distribution, which becomes an installed tuple, which becomes qualified. The installed tuple never silently lags. | `vuoro-cloud/config/compatibility.json` pins equal the `vuoro/deploy/reference-distribution.toml` pins, and the installed digest equals the latest signed distribution or a dated hold record. Today: 0.1.94 pinned vs 0.1.104 released, `release_ready:false` [F, vuoro_cloud.md §2]. |
| P5 | **Operator gates are work items.** Every operator-only step is a ready command package. | Zero handoff "restriction/excluded" lines without a linked `operator-gate` work item. Median age of a ready package below 7 days. Operator minutes per gate recorded. |
| P6 | **Supplier independence is proven by swaps** (product direction "Swap test"). | The swap ledger has ≥3 dated rows (execution harness, telemetry backend, work-ledger store), and the first-use-case acceptance test passes after each swap. |
| P7 | **The substrate hosts its own development.** Substrate work flows claim, then attempt, then protected acceptance. | Share of merged PRs in agentops, vuoro, vuoro-cloud and sovite with a linked Decision and AttemptRecord: ≥50% at H2 end, ≥80% at H3. |
| P8 | **Dogfood economics are measurable.** Cost, elapsed time, coordinator effort, repairs and review findings are reported for each outcome, with n and the unknown share. | A monthly generated report from AttemptRecords where unknown-cost share falls month over month. PR #485's "effort_and_elapsed: not measured" [F, `_artifacts/agentops/outcome-routing-2026-11-04/review-and-checks.json`] becomes the baseline zero. |

---

## 2. Target architecture

### Layers (bottom-up)

| Layer | Contents | Character |
|---|---|---|
| L0 Infrastructure | Talos/Flux (appservice), Hetzner k3s VPS (vuoro-cloud), gitops-nixos hosts, CloudNativePG, S3 (BYO/Garage), Forgejo + Actions, OpenBao, Authentik, OTel collector + Langfuse | **Adopted** |
| L1 Protected horizon | cred-broker (credential mediation), protected executor (`credctl accept`), resource-owner gateway (D2) | **Built, narrow.** Only these hold effect authority |
| L2 Records | sprintctl (work identity, claims, settlement, evidence); vuoro-evidence derivations (EvidenceSet, ExperimentRecord); vuoro-workspace (knowledge/artifacts); Git (repository documents) | **Built contracts** over adopted Postgres |
| L3 Execution | Native harnesses (session loop, tools, retries, subagents, model choice); Sovite (admission, bindings, attempts, execution leases, fences, receipts) | Harness **adopted**; Sovite **built** |
| L4 Coordination and composition | Vuoro (four contracts, composition, MCP edge, distribution manifest); vuoro.cloud (operated tenancy, lifecycle, support) | **Built glue**. "Coordination without custody" |
| L5 Guidance and packaging | agentops: canonical skills, schemas, generators (plan register, schema catalog, command packages, closeout measurement), routing guidance. **No** sprint, queue, knowledge or audit state | **Glue** |

### One owner per responsibility

| Responsibility | Single owner | Ruling | Notes |
|---|---|---|---|
| Work identity, claims, settlement | sprintctl (reference provider) | Build contract, adopt Postgres | ActionQ is deleted after the W5 fence. The Beads/Dolt swap is an H3 test, not a migration [F product direction OD2]. |
| Execution attempt, **execution lease**, fence, cancellation | Sovite | Build | Renamed "execution lease" to separate it from sprintctl "work lease" (P2) [F operated-service ownership table]. |
| Durable execution and retries inside a session | Native harness | **Adopt** | Restate/Temporal **rejected** for the substrate core. This records a disposition for L-6 and `orchestration-meta-planning.md`. Reopen only on the TS tripwire of sustained >5 concurrent workers [F target-state Tripwires]. |
| Model choice | Native harness / coordinator preference | Adopt; agentops holds alias guidance only | Jev stays advisory (60.6% vs 90% rule) [F]. |
| Acceptance (Decision, TS-5) | Protected owner via `credctl accept` | Build (exists) | Auto-accept ratchet starts with the `forge_comment_pr` canary (#255 Q4). |
| Evidence of record | sprintctl evidence → vuoro EvidenceSet | Build | auditctl: import and retire. outctl: delete. |
| Telemetry | vuoro.cloud owns. OTel → Langfuse | **Adopt** | The capture "adapter" is collector config plus harness hooks, not a new repo [I]. Attribute allowlist checked in CI (TS-15). |
| Knowledge | vuoro-workspace resolver over Git | Adopt Git | kctl retires at S4. knowledge-base stays a Git corpus and gets no new store [B]. |
| Credentials | cred-broker | Build (exists) | cred-broker-public is archived. |
| Human identity | Authentik OIDC + gateway EdDSA JWT | Adopt | SPIFFE/SPIRE stays **deferred** [F ledger]. |
| Policy evaluation | Policy-as-data minimal evaluator now, Cedar at H3 | Adopt later | See §6 D4. |
| Distribution packaging and signing | Vuoro (`reference-distribution.toml`) | Build the manifest; **adopt** OCI + cosign + SLSA/in-toto provenance | See §6 D9. |
| Installed tuple and tenant lifecycle | vuoro-cloud | Build | Mirrors distribution pins, never chooses them independently [F operated-service "Release and qualification"]. |
| Release-train integration (merge order, migration numbers) | **New declared role:** vuoro-cloud release integration owner | Process | Nobody holds it today [F landscape report]. |
| Tenant schema-version mapping contract | vuoro (contract), vuoro-cloud (consumer) | Build | Unblocks migration plan P5/P6. |
| Plan register, schema catalog, command-package schema | agentops (generated projections) | Glue | Generated from Git front matter and the served sprintctl. Not a writable ledger. |
| Acceptance rules taxonomy | ExperimentRecord + Decision policy | Fold | acceptance-lab is archived [B]. |

### Deleted or retired in the window

ActionQ, actionq-cas and actionq-dispatcher go after the W5 fence, a dump, a restore test and scale-to-zero. kctl retires at S4 and its data becomes lesson evidence. auditctl's central line retires after import plus its 90 days. outctl, sprintctl-orchestrator and sprintctl-bootstrap-template are archived. cred-broker-public is archived. `agentops.dispatch.json` and its schema are retired, with the `mechanical_bulk` self-candidate ruling moved first into a decision record. The session-mechanization v1 contracts are deleted (TS-12, zero producers). The hostproto family is archived if it still has zero consumers at 2027-03-17, which is 6 months after its last commit (TS-12). Sovite's standalone bundled Garage/Ollama profile is demoted to a test fixture. The workspace-root docs (`build-2026-schedule.md`, `ops-upgrade-rollout.md`, `orchestration-meta-planning.md`, `TOOLING.md`) are archived. The empty `/projects/dev/_orchestration` is removed. [F for each current state: tool_fleet.md inventory; agentops_core.md §2-3; plan_coherence.md §1.]

---

## 3. Staged roadmap

**Tier guidance.** It follows `model-routing.md` "Active dogfood practice" [F]. **Luna** (Codex) or **Sonnet 5.5** (Anthropic) take bounded outcomes with deterministic checks. **Terra** or **Sonnet 5.5 high** take semantic, concurrency, authority or migration work. **Opus 5.5** takes frontier planning and high-consequence review only. **Haiku 4.5** stays clerical. Reviews use fresh context, which need not mean a pricier model.

**Default escalation rule.** When a precondition fails, route to repair, then refinement, then park, with an exact continuation basis. Escalate to the operator only for a verified operator-only authority: YubiKey signing, live field execution, a new grant, or an external data boundary.

### H1: now to ~4 weeks (to ~2026-12-05). Stop losing state, unblock the terminal gate

| ID | Outcome | Acceptance | Deps | Tier | Escalate when |
|---|---|---|---|---|---|
| H1.1 | **Preserve at-risk work and restore freshness** | The declaration-v2 adjunct (`codex/declaration-v2-ledger-20261106`, in `/tmp`) and Sovite expired-owner WIP are pushed as draft PRs. Untracked resume and handoff state is committed to a tracked programme-status file or archived. `/tmp` and prunable worktrees are removed by explicit allowlist. agentops, sovite and vuoro-cloud checkouts are on origin/main. `estate_status` flags stale checkouts at session start. | none | Luna / Sonnet 5.5 | A branch is held by a live session (route to its owner) |
| H1.2 | **Operator-gate command packages** (see §4) | Packages exist for Work31 field execution (appservice PR2153), the 0.1.104 rollout and Work-schema 30/31, the next poc.N promotion, the live signing/mint authorization scope, and the staging rehearsal with real wheels. Each has verified preconditions, one `&&`-chained command block, expected output, rollback and the evidence to return. A dry-run preflight passes. | H1.1 | Terra (Work31, mint) / Luna (promotion) | A precondition can only be observed by the operator |
| H1.3 | **First operator window executed** | ≥3 packages run in one window. Results are recorded as evidence and the gates close or carry an exact repair item. | H1.2 | n/a (operator) | none. This is the planned operator touchpoint |
| H1.4 | **Programme completion redefined** | Each of 01-08 is closed as "source accepted" with its residual deployment as a separate gate item, or kept open with a single named blocker. No parent stays open for more than three handoffs without a named blocker. | H1.1 | Opus 5.5 (one pass) | none |
| H1.5 | **Sovite CI flake diagnosis** | Root cause found or a quarantined reproducer exists for the `authority_unavailable` failure (PR70), the 1122 ms timeout (PR71) and the push failure. Then 20 consecutive green runs on main. New Sovite feature slices are paused until this lands. | none | Terra | The root cause is in a pinned Vuoro wheel (route to vuoro) |
| H1.6 | **Declare unowned seams** | Named owners and items for the release-train integration owner, migration-number reservation, the tenant schema-version mapping contract (vuoro) and the EC-00 #405 holder. | none | Luna | none |
| H1.7 | **Plan register v0** | Generated `docs/plans/REGISTER.{json,md}` uses one 6-value status vocabulary (proposed, accepted, active, superseded, retired, source-material) plus owner, work_ref, last_verified and successor. An ADR index marks what is in force. A CI check covers it. The live programmes and 2026-10/11 plans are registered first. | H1.1 | Luna | none |
| H1.8 | **Doc corrections and dispositions** | Fix the Sovite PLATFORM-SPEC (it does write through a Vuoro adapter). Correct the product-direction ledger row "Hosted multi-tenant: Defer", which is now partially superseded by the 10-29 amendment for operator-owned workspaces. Update the vuoro-cloud README (it still says poc.22), `ecosystem.md` (kctl, cockpit), the kctl-routed skills (`item-done`, `workflow-artifact-capture`), and `next-session-dispatch.md`. Record a rejection of the Restate pilot. Retire `agentops.dispatch.json` and add a decision record for the self-candidate ruling. Clarify the OpenCode Go external-provider data boundary in `model-routing.md`. | H1.7 | Luna / Sonnet 5.5 | none. Per intent-first, these are doc corrections |
| H1.9 | **AttemptRecord v0** | Schema `attempt-record/v1` (agentops canonical) joins route requested, observed binding, session id, cost snapshot, EvidenceSet digest, Decision id and missing links. The producer is a closeout script built from `outcome_measurement.py` and `cost_per_release.py`, both of which exist [F #487/#488]. It runs over every H1 outcome as cohort 0. | none | Terra (contract) then Luna (producer) | A join field has no producer (record it as a failure class; do not escalate) |

### H2: to ~3 months (to ~2027-02). Release train, first live use case, self-hosting v1

| ID | Outcome | Acceptance | Deps | Tier | Escalate when |
|---|---|---|---|---|---|
| H2.1 | **Release train v1** | Signed distribution `vuoro-distribution` as OCI artifacts with cosign (YubiKey PIV key) and SLSA provenance from Forgejo Actions. vuoro-cloud mirrors its pins. Live Work schema migrated (30/31). `release_ready:true` for ≥1 capability. Migration plan P5/P6 merged. The rehearsal job is required after 5 consecutive green runs. | H1.3, H1.6 | Terra; Opus 5.5 review | Signing key custody change (operator) |
| H2.2 | **Generated schema catalog** | Every `name/vN` across the critical-path repos (sprintctl, vuoro, sovite, cred-broker, vuoro-cloud, agentops) is listed with owner, version and digest, with a disambiguated vocabulary. A cross-repo CI lint (P2) runs in each repo. | H1.7 | Luna | none |
| H2.3 | **First use case passes live** (product direction §First use case) | Hosted Claude claims via vuoro.cloud MCP, then a native Codex continuation, then protected digest acceptance, then a cold reconstruction. All five acceptance bullets pass, including one harness swap. | H2.1, material-v2 proofs (H2.6) | Opus 5.5 plan; Terra build | none |
| H2.4 | **Operated service D1-D2** | Managed VM workbench, retained candidates, worker replacement. The resource-owner gateway has scoped cluster read and one LAN API. Denial tests pass for escape, admin and foreign tenant. | H2.1, H1.5 | Terra | First billable resources (operator spend grant, packaged) |
| H2.5 | **Self-hosting loop v1** | agentops and vuoro work items are claimed through vuoro.cloud MCP (`claim_work`/`report_outcome`, already exposed to sessions [F]), executed natively or by Sovite, accepted via `credctl accept`, with an AttemptRecord written. ≥50% of substrate PRs pass through it (P7). | H1.9, H2.1 | Sonnet 5.5 / Luna | Median time-to-merge regresses >50% (see kill criteria) |
| H2.6 | **Authority chain completion** | material-v2 proofs: all-writer gate, lock order (40P01), restore/epoch anti-fork, outbox recovery. Admission private transport. Real mint under a packaged signing grant. Owner lookup over a trusted return channel. | H1.1, H1.3 | Terra; Opus 5.5 review | Mint authorization scope (packaged gate) |
| H2.7 | **Retirements executed** | ActionQ dump + restore test + scale-to-zero (W5 fence). kctl S4 import. auditctl import started. Archives per §2. | H1.7 | Luna | none |
| H2.8 | **Telemetry real, not synthetic** | OTel allowlist CI gate. Native child export to Langfuse repeated under a scoped grant. Capture coverage with denominator. A "last successful authoritative event age" metric with an alert (#255 Q6). | H1.9 | Sonnet 5.5 | The repeat-probe authority (packaged) |
| H2.9 | **Dogfood economics report** | A monthly generated report covers per-tier accepted-first-pass, repairs, review findings, elapsed time, coordinator minutes and unknown share. The first Luna-vs-Terra observations come with n. | H1.9 | Luna | none |

### H3: ~6-12 months (to ~2027-11). Operated distribution, ratchet, multi-workspace

| ID | Outcome | Acceptance | Deps | Tier |
|---|---|---|---|---|
| H3.1 | **Operated service D3-D4** | AgentOps repository-workflow consumer. Combined recovery/restore/revocation. Second-tenant adversarial qualification. Independent reconstruction. | H2.4, H2.6 | Terra; Opus 5.5 review |
| H3.2 | **Swap ledger ≥3 rows** | Harness (done in H2.3), telemetry backend (Langfuse → alternative), work-ledger store (Beads/Dolt trial behind WorkRelease). | H2.3 | Terra |
| H3.3 | **Quarterly signed distributions** | A fresh agent installs the self-hosted reference profile from the manifest alone in under a working day, including restore and export. | H2.1 | Sonnet 5.5 |
| H3.4 | **Abstraction ratchet** | Auto-accept for `forge_comment_pr`, then ≥2 further low-risk decision classes, each authorized under existing policy with its record cited. | H2.5, H2.9 | Opus 5.5 (policy) |
| H3.5 | **Multi-workspace** | ≥3 operator workspaces on vuoro.cloud (software, household/homelab-analytics, creative), with per-workspace restore proven. | H3.1 | Terra |
| H3.6 | **Self-hosting ≥80%; gates packaged automatically** | Gate packages are generated from handoff restrictions with no hand authoring. Operator minutes per week are trended. | H2.5 | Luna |
| H3.7 | **External admission decision** | Decided on D4 evidence: admit (design a tenant-side protected horizon) or keep it operator-only. | H3.1 | Opus 5.5 |

### Critical path and parallelism

**Critical path [I]:** H1.1 → H1.2 → H1.3 (operator window) → H2.1 (release train, Work31 live) → H2.6 → H2.3 (first use case live) → H2.4 → H3.1 → H3.5.

**Parallel from day one:** H1.5 (Sovite CI), H1.6, H1.7 → H2.2, H1.8, H1.9 → H2.9, H2.7, H2.8.

**Throughput constraint [F]:** vuoro-cloud has fast-forward-only merges on a single runner (~30-75 min), so all vuoro-cloud work lands as one stacked linear branch serialized by the H1.6 integration owner.

---

## 4. Replanning moves

**The seven 2026-10-24 programmes plus 08 integration.** None closed in two weeks, and three consecutive handoffs (11-04 to 11-06) record no accepted parent [F plan_coherence.md §3]. Collapse them into three tracks, each with one integration owner:

- **Records and contracts:** 01 contract foundation, 04 requests/continuation, and 06 telemetry's evidence parts. Becomes H1.9, H2.2, H2.6 and H2.8.
- **Operated service:** 02 cloud recovery, 03 cloud product/TUI/distribution, 05 Sovite, 07 retention/recovery. Becomes the D-stages H2.4 and H3.1.
- **Release train:** 08 integration plus every deployment tail. Becomes H1.2, H1.3 and H2.1.

The ~30 h target becomes an observed effort figure in AttemptRecords, not a budget (P8). Completion means "source accepted". Deployment is a gate item (H1.4).

**vuoro-cloud P0-P7.**
- Confirm the #353 (P5) merge. Move the tenant schema-version mapping contract to vuoro under a named item (H1.6).
- Merge-time migration numbering becomes a reservation held by the integration owner.
- The rehearsal job becomes required after 5 consecutive green runs against pinned wheels, not locally installed schema 27.
- P7's staging rehearsal and live Talos proof become gate packages.

**Sovite slices.**
- Freeze feature slices until H1.5 lands.
- Afterwards, admit only slices that serve D1/D2: repository execution, the resource-owner gateway, removal of the worker-pod control environment (R4/S3/S4/S6).
- Decide the standalone-mode demotion (§6 D7).
- Add a Sovite plan index that maps R/S/PW/CL-K06 to register entries.

**Operator-only gates become first-class work [I].** Define `operator-command-package/v1` in agentops (schema and skill only; the items live in sprintctl as `kind=operator-gate`). Required fields:

1. Gate id and authority class: why it is operator-only (YubiKey, field execution, spend, data boundary).
2. Precondition checks with the command and observed result, verified no more than 24 h before the window.
3. One `&&`-chained command block, with numbered steps only around `nix develop` (operator preference [F memory]).
4. Expected output.
5. Rollback.
6. The exact evidence to send back.
7. Expiry.

A handoff that lists a restriction without a package is invalid; the handoff validator checks this. Packages are batched into a recurring operator window (§6 D2). Each run records operator minutes. A package that runs unchanged three times becomes a ratchet candidate: either a fenced automated job where the operator only signs, or a standing grant recorded under existing policy. Signing itself stays human.

**Merge and collapse.**
- Vuoro claims and the ActionQ queue become sprintctl work leases only.
- Evidence: auditctl, outctl and Vuoro evidence become sprintctl evidence plus the derived EvidenceSet. OTel is observation only (TS-6, TS-15).
- Knowledge: kctl, knowledge-base and vuoro-workspace become vuoro-workspace over Git.
- Acceptance: acceptance-lab and ActionQ acceptance become Decision plus ExperimentRecord.
- Agent protocol: hostproto MCP/A2A and vuoro-mcp-edge become vuoro-mcp-edge only. hostproto stays a frozen semantic reference until its TS-12 date.

---

## 5. Risks, bets and kill criteria

| Pattern / bet | Kill or retire when (evidence) |
|---|---|
| [B] The plan register is read, not just generated | After 4 weeks, sessions still act on stale state (freshness-check hits per session not falling), or register drift exceeds 10% of docs. Then move status into served sprintctl only and drop the file projection. |
| [B] AttemptRecord can be joined from existing producers | Coverage stays below 50% after 8 weeks of the producer. Then the hook-based capture (TS-4) is insufficient, and harness-side emitters get prioritized over the join. |
| [B] Rejecting Restate/Temporal | Sustained >5 concurrent workers, or harness subagents failing cost per accepted item (target-state tripwire) [F]. Then reopen L-6 as a pilot under Sovite, never in Vuoro. |
| [B] Sovite's own queue/lease stays built | Queue, lease or fence defects make up more than 30% of Sovite CI failures over a month. Then replace the internals with a standard Postgres queue library behind the same contract. |
| Self-hosting loop | Median time-to-merge regresses more than 50% for a month with no reconstructability gain. Then scope it back to authority-touching work only. |
| Luna owns discovery and planning (2026-11-04 practice) | Luna's accepted-first-pass rate on planning-heavy outcomes falls more than 20 points below Terra's at n≥15, or repairs per outcome double. Then retire that pattern and keep Luna for bounded builds. |
| Operator-window cadence | Two consecutive windows run fewer than 50% of ready packages. Then preconditions are not being verified honestly, so pause package generation and repair the preflight. |
| hostproto family | Zero consumers at 2027-03-17. Archive (TS-12). |
| Operated-service ambition (D5 external onboarding) | Operator ops minutes per week rise while P7 stays below 50%. Then park D5 and keep vuoro.cloud operator-only. |

**Assumptions most likely wrong [I]:**
1. That the operator can sustain a recurring deployment window. Everything on the critical path depends on it.
2. That served sprintctl state matches the docs. It was not queried [F landscape "did not verify"].
3. That the single-node k3s VPS with a single CNPG instance can carry several workspaces with acceptable restore. Physical/WAL recovery was still unqualified at 2026-10-29 [F].
4. That observed instruction digests separate outcomes (TS-3 tripwire).
5. That the OpenCode Go data boundary permits meaningful delegation. A 2026-11-06 auto-approval rejection suggests a narrow boundary [F].
6. That roughly 30 h programmes are a meaningful unit of work at all.

**Top risks.**
- Migration-number collisions across two lanes.
- YubiKey and single-runner bottlenecks: release cadence is bounded by two signing touches per promotion and 30-75 min CI.
- Flaky Sovite CI undermines qualification claims.
- Hosted claims outrun evidence. Mitigation: the "unknown stays unknown" rule plus P4.

---

## 6. Open decisions, each with a recommendation

| # | Decision | Recommendation |
|---|---|---|
| D1 | What "complete" means for a programme | "Source accepted" closes the parent. Each deployment or field step is a separate gate item. Adopt in H1.4. |
| D2 | Deployment-window cadence | A weekly 60-minute operator window, with packages frozen and preflighted 24 h before. If none are ready, skip the window and record why. |
| D3 | Restate/Temporal (L-6, meta-planning) | Reject for the core and record it as a decision. The provisioning ledger already says "harness-native; Temporal where a provider ships it" [F]. |
| D4 | Policy engine (product direction OD1) | Policy-as-data with a minimal evaluator through H2, while review boundaries are still moving. Choose Cedar at H3 for its analysability. Revisit if OPA is already deployed for another owner. |
| D5 | Work-ledger store (OD2) | Keep sprintctl. Run Beads/Dolt only as the H3 swap test. |
| D6 | Evidence schema home (OD3) | Vuoro-native now, with the exporter mapping onto OTel GenAI semantic-convention attributes. Propose upstream only after a swap has been run. |
| D7 | Sovite standalone vs workspace-hosted | The supported profile is workspace-owned execution under Vuoro. Standalone Compose with Garage/Ollama becomes a dev/test fixture with no separate docs line. |
| D8 | Hosted-runtime entry (OD4) | MCP only. A2A stays deferred with hostproto-a2a frozen. |
| D9 | Distribution signing | OCI artifacts signed with cosign using a YubiKey-held key, plus SLSA provenance from Forgejo Actions. No public keyless dependency for a private estate. The signed Git tags remain Flux's trigger. |
| D10 | vuoro.cloud authority for others (OD7) | No within this window. Operator-owned workspaces only. Decide in H3.7 on D4 evidence. |
| D11 | knowledge-base successor | It stays a Git corpus, resolved through vuoro-workspace with no new store. Rendered prose remains Git-authoritative. |
| D12 | The `mechanical_bulk` self-candidate exception | Move it into a decision record with an expiry. Renew it only if review-finding data from H2.9 supports a green-gate-only disposition. |
| D13 | Release-train integration owner | One declared role per session lineage under the vuoro-cloud release owner. It holds merge order, migration reservations and the pin bump. |
| D14 | Horizon wording versus the estate plan | Keep H1-H3 as dependency tiers with indicative windows, as stated in the header. No date commitments. |

**Sources read (2026-11-07):**
- `_artifacts/deep-research/reports/Agentic substrate landscape alignment.md`
- research notes `vuoro_cloud.md`, `tool_fleet.md`, `plan_coherence.md` (§1-3), `sovite.md` and `agentops_core.md` (takeaways and inferences)
- agentops origin/main (33ef59b): `docs/plans/2026-09-17-target-state.md`, `docs/plans/agentops/2026-10-17-estate-evolution-plan.md`, `2026-10-18-kaos-2028-roadmap.md`, `2026-10-29-operated-agentic-service.md`, `docs/dispatch/model-routing.md`, `docs/dispatch/programmes/2026-10-24/*`, commits #487, #488 and #493
- vuoro origin/main: `docs/direction/2026-10-15-product-direction.md`, `deploy/reference-distribution.toml`
- sovite origin/main (5d6f5ab): `pyproject.toml`

Not verified: served sprintctl, Forgejo/CI state after 2026-11-06 21:39Z, live clusters, and the text of issue #255 (read only through the memory note).
