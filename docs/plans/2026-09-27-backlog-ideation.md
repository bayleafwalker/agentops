# vuoro.cloud backlog ideation (2026-09-27)

Status: proposal from a read-only Fable planning pass, not yet adopted. H1 items are candidates for sprintctl; H2 and H3 await operator review.

Read-only planning pass. Sources: agentops plans (target state, cloud enablement plan, trusted-service design, options memo), vuoro `origin/main` (758e081, vuoro-service 0.1.76 / mcp-edge 0.1.3), vuoro-cloud `origin/main` (b013e29, generation 47 candidate), sprintctl and cred-broker-public READMEs, and `sprintctl item list --sprint-id 559` (149 items, 27 pending). Nothing was edited or committed.

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
- **Outcome.** An `effect_intent` table and `work.effect.propose/get/list-proposed/accept/reject/mark-applied` operations in sprintctl (schema 18) or, if the owner decision says otherwise, a vuoro-service intents adapter. States exactly `proposed|accepted|rejected|applied|failed`; no assignment, scheduling, retry, expiry (TS-1's five verbs). `accept`/`reject`/`mark-applied` are *not* on `MCP_TOOL_SCOPES`; they are served-shell operations the trusted side calls. Edge lists the propose bucket once `context.intents` is durable; vuoro-cloud adds the E3 scope rows already stubbed in `oauth_scopes.py`.
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

#### H1-5. Strict-client MCP conformance in vuoro PR CI, and build the image on PR
- **Problem.** The `resultType`/`cacheScope` regression reached production because claude.ai is lenient and Claude Code strict (cloud-enablement-plan "Why the 2026-09-25 verdict was no"). `ci.yml` builds wheels only; the image workflow is release-time.
- **Outcome.** A CI job that (a) builds the `Dockerfile` image, (b) starts `vuoro-service mcp-serve` with a test assertion signer, and (c) runs a strict MCP 2026-07-28 client (schema-validated `tools/list`, `tools/call` envelopes, error shape) plus the D-044 isolation test against the container. Fail on any envelope deviation.
- **Repos.** vuoro. **Depends.** none. **Size.** M. **TS-16.** n/a (test-only). **Track.** 1466 tests. **Dispatch.** Cloud.

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
