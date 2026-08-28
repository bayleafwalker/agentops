# Cross-repo dogfood plan — 2026-08-28 (rev. 2, owner-amended)

Status: **thesis, narrowed ownership model, non-goals, vuoro `#1245`, hostproto adapter repair and cred-broker hygiene are approved.** Everything past R0 is authorized gate-by-gate, not by calendar. This revision incorporates the owner ruling of 2026-08-28; see §7 for what changed and why.
Scope: vuoro, agentops, sprintctl, actionq, auditctl, kctl, cred-broker, hostproto, scribectl, appservice/gitops-nixos as deployment hosts.

## 1. Where things actually stand

| Repo | State (evidence) | What blocks it cross-repo |
|---|---|---|
| vuoro | Direction doc (08-22/24) = "distribution/control projection", still a *freeze candidate*. Takeover experiment 08-20 adjudicated **NARROW**: surviving boundary is a read-only reconciliation/export adapter. | `#1245` `work_store.repo_id` hardcoded → 7 of 8 repos cannot use served mode. Three `vuoro-service` deployments on three digests (`vuoro-dev`, `vuoro-shared`, `agent-cockpit`). |
| sprintctl 0.3.2 | Served-mode hub; the only repo everything else already talks to. | Served-mode gaps (#1982–#1985) gated behind `#1164` split-backend retirement. |
| actionq 0.1.28 | Execution plane retired; federation is a *target*. | Federation schema uninitialized cluster-wide; 5.3 is the first GitOps mutation. W7 not authorized (D-10). |
| auditctl 0.1.2 | Shared Vuoro adapter contract landed. | `#1201` central ingest → `#1202` observation/receipt adapter. Nothing publishes into it yet except sprintctl hooks. |
| kctl 0.1.3 | Read-only over sprintctl. | `#1199` → `#1200`, mirrors auditctl's pair. Demand-gated: dormant unless a consumer's friction calls for it. |
| cred-broker | Passes 1–4 done, pass 5 mid-flight; all live canaries green on 08-11. **Dormant since.** | No dispatch manifest. Unattended-agent gate closed. Forgejo JWT integration not commissioned. Container build hand-overlaid. |
| hostproto | W1-01 landed 08-22, Wave 1 open. | Served `next-work` returns `adapter-result-invalid` (vuoro bug). No git remote. OQ-007 (evidence → auditctl or kctl?) undecided. Separate `hostproto-semantics` lineage. |
| scribectl 0.1.0 | Sprint 19/19 done, Phase C live in real vault. `observable` manifest. | Nothing — it is a pure substrate consumer and the best canary. `scribedispatch` never touches the substrate; keep it that way. |
| agentops | 18 dispatch manifests, mix of schema v1/v2; 13 are `guidance-only`. | Manifests describe routing that nothing executes end-to-end (`hybrid_dispatch.py:995` needs human review JSON; no `prepare → run → gate → receipt` driver). |

Two findings from the last fortnight frame everything below:

- The NARROW verdict: takeover-through-Vuoro was *safer in explanation* but strictly more glue (212 vs 148 lines, 5 vs 4 state locations) with zero operator-action advantage. Vuoro earns its place only where authorities genuinely compete.
- `2026-08-26-open-owner-decisions.md`: "the human was mostly being used as a very expensive Enter key." Per-packet approval is theatre; review belongs at the boundaries enumerated in §4.

Conclusion: the substrate is over-designed relative to its consumers. The next unit of value is not another contract — it is making the three real consumers (scribectl, hostproto, cred-broker-guarded agent writes) run through what exists, and letting their friction generate the requirements.

**Organizing rule (owner amendment).** This plan is sequenced by *consumer packet*, not by subsystem. Completing seams is not progress; a completed vertical slice is. Any tranche that finishes without one consumer running end-to-end has failed, however much substrate it built.

## 2. Cross-functionality worth building (the seams)

Seams below are described as capabilities. None of them is authorized as a subsystem project; each is built only as far as the consumer packet in §5 requires.

**S1 — Served mode proven by two independent non-sprintctl repos.** Fix vuoro `#1245` (repo_id per request, not per process) and reproduce/fix `adapter-result-invalid` under the `hostproto` scope. Success is scribectl and hostproto running served sprints — *not* eight repos enabled. Pre-emptively enabling every repo is the same over-build the thesis rejects.

*Authority model (amendment 2).* `repo_id` and `authority_repo_uuid` collapse into **one immutable authority UUID**; repository names and slugs are display metadata over it. Served authorization binds the **authenticated principal** to that UUID. A caller-supplied repo id is a routing hint, never an isolation boundary — accepting one as authorization is the bug `#1245` must not be re-introduced as.

*Deployment.* Converge the three `vuoro-service` deployments onto **one immutable image digest**. "Named roles" stay deployment configuration; no role abstraction until a consumer requires one.

**S2 — One evidence spine, repo-owned.** auditctl is the **receipt envelope owner, not the evidence owner**:
- Repo-local shards remain authoritative.
- auditctl owns the envelope, integrity rules, the rebuildable index and the query surface.
- `canon.ratified` (scribectl), `capability.decision` (cred-broker), `harness.gate` (dispatch gates) and hostproto verification remain **domain-owned payload schemas**.
- Cockpit reads auditctl's rebuildable index/API — not raw shards, not a Vuoro evidence projection. NARROW rejected takeover-through-projection because it added glue without operator benefit; it did not reject disposable read projections in general.

*OQ-007 closes here, by ratification:* **hostproto publishes its own verification schema inside `evidence-ref/v1`; auditctl owns storage and provenance mechanics, not verification meaning.**

**S3 — Manifest convergence, executable surfaces only.** Convert only **executable** manifests to schema v2 with `instruction_set`; explicitly mark or archive the 13 `guidance-only` manifests rather than renovating dead surface. Add a cred-broker manifest. Carry the authority UUID everywhere. Promote adoption level only from receipts on record — nothing reaches `dispatchable` without a gate run in evidence.

**S4 — cred-broker becomes the agent host's credential plane.** The only seam that unlocks *unattended* agents:
1. Hygiene first: close PR #1 + canary branch, delete the downloaded App PEM after rotation, formalize the container build (Dockerfile in-repo, image via appservice registry).
2. Commission Forgejo v16 Generic JWT integration; live isolation test.
3. devbox-agent enrollment: host mTLS cert via gitops-nixos (`hosts/devbox`), `credctl exec git push` as the write path for agents.
4. Forgejo-runner commissioning is tracked **separately** from broker enforcement where possible — both are substantial trust changes and should not fail together.
Vuoro composes the decision API; it never becomes an authorization authority.

**S5 — hostproto stays outside Vuoro unless a real consumer demonstrates leverage.** (Amended: a version number is not evidence, so `contract-v0.1.0` no longer auto-unlocks integration.) Give it a remote (Forgejo), land W1-02 envelope codec, resolve OQ-002 with spec package 0.1.1. Lineage stated explicitly: `hostproto` = conformance study; `hostproto-semantics` + adapters = consumption surface; `browser-workbench` is the eventual consumer. Its only substrate obligations are S1 (served sprint) and S2 (evidence).

**S6 — scribectl as the canary.** **No `scribedispatch` integration; only the generic served-work and receipt seams.** (The earlier "zero new integration" was wrong — an audit publisher is new code; what must stay zero is repo-specific coupling.) If the generic seams break scribectl, that is a P0 for vuoro, not for scribectl.

**Promotion rule — the actual proof a seam exists.** After the first consumer works, the second consumer must require **only repo-owned configuration and publishing code** — no changes to sprintctl, Vuoro or auditctl core. A second consumer that needs core edits means there is no seam, only a special case.

## 3. Dogfooding requirements (must hold for a repo to be "in")

D1. The repo's sprint state lives in served sprintctl under its own authority UUID; `session resume` works from a fresh devbox-agent shell.

D2. **Gating verification runs** emit an exact-revision receipt into auditctl (not every local test invocation). A receipt carries: exact commit/head and clean-source state; toolchain and policy version; input/configuration digest; producer identity; outcome and evidence reference; explicit lossy/sanitized markers.

D3. **Rebuild gate.** Delete the derived index, rebuild it without rerunning any work, compare canonical receipt digests, and detect duplicate, missing and corrupt shards.

D4. Agent writes (commit/push/PR) go through `credctl exec`; no long-lived provider tokens on devbox-agent.

D5. **The authoritative flow is `plan → build → commit/push → PR → independent exact-head CI/gate → ready for owner review`.** The writer must not mint its own dispositive acceptance result. Machine-generated review JSON is admissible only as an *independently produced* evaluation over immutable evidence — an agent approving its own homework is not a gate.

D6. Fault cases, both required:
- Interrupt after work is claimed, resume from a fresh shell → no duplicate state, write or receipt.
- Revoke or disable broker credentials → agent write **fails closed**, while the owner's break-glass path remains available outside devbox-agent.

D7. Human review points follow the standing policy in §4 — no per-packet sign-off.

D8. Measured per packet: operator actions after interruption, glue lines added, state locations touched — the NARROW scorecard, kept as a regression metric against the R0 baseline.

## 4. Standing review policy (replaces the human-review absolute)

Credential authority and irreversible migrations are not Enter-key decisions. The earlier three-item list was too narrow; the policy is:

- **Autonomous** — bounded code/test/docs changes under existing authority and an existing acceptance policy.
- **Human judgment required** — architecture or spec freeze; public release; taste/canon ratification; trust-root or credential-scope changes; authority-boundary changes; destructive migrations.
- **Denied** — anything with unexpected external effects, any authority expansion, anything lacking independent evidence.

Placement: **cross-repo orchestration policy** may live in `agentops.toml`; **repo-specific acceptance and authority policy stays in the owning repository.** Centralizing acceptance policy would recreate the ownership shape NARROW rejected.

## 5. Sequence — by consumer packet

Week figures are forecasts. **The gates, not the calendar, are the authorization boundaries.**

**R0 — Ratify boundaries and establish baselines.**
- Ratify the narrowed Vuoro direction and the non-goals **now** (§6); the takeover experiment already supplied the decision evidence.
- Define the canonical authority UUID and its binding to the authenticated principal.
- Classify every dispatch manifest as executable, guidance-only or archived.
- Run the current **direct/native** scribectl and hostproto paths and record the NARROW counting rubric — this is the baseline D8 measures against.
- *Gate:* baseline recorded; manifest classification committed; direction ratified.

**R1 — scribectl vertical slice (first consumer).**
- Fix vuoro `#1245` plus served authorization/isolation on the authority UUID.
- Pin the same service artifact digest across all three deployments.
- Run `next-work`, **interrupt it**, resume from a fresh shell.
- Publish one repo-local receipt; rebuild the auditctl index from shards.
- *Rollback:* previous service digest. No dual-write, no authority migration.
- *Gate:* D1, D2, D3, D6(interrupt) hold for scribectl.

**R2 — hostproto generalization test (does the seam generalize?).**
- Fix `adapter-result-invalid`.
- Close OQ-007 using the already-established evidence envelope (§2/S2).
- Repeat the interrupted run and the index rebuild.
- *Gate:* **no new repo-specific branch in Vuoro, sprintctl or auditctl core.** Repo-owned config and publishing code only. Failing this gate means R1 produced a special case, not a seam — stop and reallocate.

**R3 — guarded agent write (cross-cutting capability).**
- cred-broker hygiene; Forgejo JWT; devbox-agent mTLS.
- Canary `credctl exec git push` **alongside** the existing owner path, not replacing it.
- Agent opens a PR; independent Forgejo CI evaluates the **exact head** (D5).
- Test expiry, revocation and broker outage **before** enforcement (D6).
- Then, and only then, remove long-lived provider credentials from devbox-agent.
- *Gate:* one packet completes plan → build → PR → independent gate with no human action before the review boundary; revocation fails closed; break-glass verified.

**R4 — promote only demonstrated surfaces.**
- Upgrade active manifests to v2; promote adoption levels from receipts.
- Point cockpit at auditctl's rebuildable query surface.
- Time-box the Beads/Gas Town lane as a **bounded falsification exercise** — after the first vertical slice, or delete it. It does not block dogfooding.
- actionq federation and kctl `#1199/#1200` stay **dormant** unless observed friction calls for them.

## 6. Conditions on the dormant work

- **actionq federation (5.3)** requires an **observed conflict that native ownership/CAS cannot resolve** — not merely two authorities existing. Absent that, federation is a reconciliation view over auditctl, not a schema.
- **kctl `#1199/#1200`** — demand-gated.
- **hostproto ↔ Vuoro integration** — consumer leverage, not a version tag.
- **Beads/Gas Town** — one bounded lane or deletion.

## 7. Non-goals

No new execution control plane or takeover runner. No Vuoro ownership of code, intent, evidence or acceptance. No centralized evidence ownership in auditctl — repo shards stay authoritative. No federation schema on speculation. No `scribedispatch` integration. No W7. No hostproto-semantics merge into hostproto. No pre-emptive enablement of repos without a consumer. No renovation of guidance-only manifests.

## 8. Amendment record (owner ruling, 2026-08-28)

Approved as written: the thesis, the narrowed ownership model, the non-goals, vuoro `#1245`, the hostproto adapter repair, cred-broker hygiene.

Returned and now amended:

1. **Sequenced by consumer packet, not subsystem.** Rev. 1 could have finished most of T0–T1 — service consolidation, evidence schemas, manifest migration, cockpit work — without one complete consumer packet. Added the promotion rule and the R2 no-core-changes gate as the test that a seam is real.
2. **One authority model.** `repo_id` + `authority_repo_uuid` collapsed into one immutable UUID bound to the authenticated principal. auditctl demoted from evidence owner to envelope owner; OQ-007 closed by ratification; S5 unlocked by consumer leverage rather than by `contract-v0.1.0`.
3. **Gates prove more than happy-path existence.** Added the authoritative flow with an independent exact-head gate, the receipt content list, the rebuild gate, and the two fault cases (interrupt/resume, revocation fails closed).
4. **Standing policy replaces the human-review absolute.** Three tiers (autonomous / human judgment / denied); cross-repo orchestration policy in `agentops.toml`, repo acceptance policy stays repo-owned.
5. **Speculative work off the critical path.** Direction ratified at R0 instead of T3; federation conditional on an observed unresolvable conflict; kctl demand-gated; Beads/Gas Town time-boxed or deleted; one image digest with no role abstraction; Forgejo-runner commissioning separated from broker enforcement.

## 9. Known gaps in the inputs

State above is drawn from workstation clones and docs as of 2026-08-28. Devbox-agent and cluster reality were **not** verified — in particular whether the three `vuoro-service` digests are still three. R0 begins with that check.
