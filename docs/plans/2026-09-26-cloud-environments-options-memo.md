# Decision memo: Claude Code cloud environments for Vuoro Cloud

## Recommendation

Use the credit now to finish E1 exactly as designed: one single-repository Routine authenticates through the existing Vuoro OAuth connector, reads `list_ready_work`/`describe_work`, and always opens a verdict PR through Claude’s GitHub App. In parallel, establish a pinned, credential-free cloud test/build environment. Next, build E2 as a narrow MCP coordination and evidence surface with server-minted run identity, explicit repository binding, idempotency, and owner-backed operations. Do not make static Vuoro PATs or hosted provider credentials the default: direct CLI access should remain an attended exception, while Forgejo, cluster, S3, SOPS, merge, deployment, and YubiKey authority remain operator-side. Later credential brokering should mediate an operator-side effect from a cloud-proposed intent, never return powerful credentials to the cloud sandbox. This preserves Vuoro’s accepted boundary—coordination rather than hosted execution or credential custody—documented in the [product authority model](/projects/dev/vuoro-cloud/19-PRODUCT-POSITIONING-AND-PROOF.md:73) and [target state](/projects/dev/agentops/docs/plans/2026-09-17-target-state.md:45).

## Ranked options

| Rank | Option | Operator value | Effort | Blast radius | Recommendation |
|---:|---|---|---|---|---|
| 1 | E1 read-only Routine → verdict PR | Very high now | S | Low | Do immediately |
| 2 | Reproducible credential-free cloud test/build lane | High | S–M | Low–medium | Do immediately |
| 3 | E2 MCP run coordination and evidence | Very high, durable | L | Medium | Build next, contract-first |
| 4 | Explicit multi-repository coordination | High after E1 | M–L | Medium | Design with E2 |
| 5 | Direct Vuoro CLI in cloud sessions | Medium | S–M repair, M operationally | Medium–high | Attended exception only |
| 6 | EffectIntent plus trusted-side broker/reconciler | High later | L | High but containable | E3, after E2 |
| 7 | Vend Forgejo/S3/cluster credentials to cloud | Low or negative now | L–XL | Critical | Reject under current boundary |

## Option detail

### 1. E1 read-only Routine and PR

**What it enables.** Scheduled or one-shot triage of ready work, with the judgment returned as a durable GitHub branch and PR. This is the recorded E1 acceptance path: OAuth, both MCP read tools, then a PR ([E1 design](/projects/dev/agentops/docs/design/e1/e1-stronger-baseline-design-2026-09-22.md:473)).

**Concrete changes.**

- Configure one Routine against one GitHub-authoritative repository.
- Require it to:
  1. verify both Vuoro tools are visible;
  2. call `list_ready_work`;
  3. call `describe_work` for selected items;
  4. write a dated assessment;
  5. open a PR even when no work is found.
- Follow the existing “always materialize the result” pattern in [cloud-routine-authoring.md](/projects/dev/agentops/docs/runbooks/cloud-routine-authoring.md:41).
- Record a Routine/run identifier in the report and PR. It is correlation only until E2 supplies a trusted server-minted run identity.
- After live confirmation, refresh the stale generation/version statements in [IMPLEMENTATION-STATUS.md](/projects/dev/vuoro-cloud/IMPLEMENTATION-STATUS.md:13) and [compatibility.json](/projects/dev/vuoro-cloud/config/compatibility.json:5).

No server feature should be needed once the supplied generation-44/`vuoro-service` 0.1.74 rollout is healthy. The edge already exposes only the two read tools ([server.py](/projects/dev/vuoro/packages/vuoro-mcp-edge/src/vuoro_mcp_edge/server.py:85)), and only `vuoro:work.read` is grantable ([oauth_scopes.py](/projects/dev/vuoro-cloud/src/vuoro_cloud/oauth_scopes.py:18)).

**Prerequisites and dependencies.**

- Generation 44 healthy.
- Connector authorization completed for the pilot workspace.
- Exactly one repository in the pilot workspace.
- GitHub access allowing non-protected branch pushes and PR creation, with the default branch protected.

**Security and blast radius.**

- No Vuoro secret enters the sandbox: connector OAuth is exercised server-side rather than exposed as an environment variable.
- Access tokens are short-lived—currently 15 minutes—and grant/membership/workspace state is rechecked ([oauth_server.py](/projects/dev/vuoro-cloud/src/vuoro_cloud/oauth_server.py:35)).
- The cloud session can disclose the selected read projection and alter its permitted GitHub branch. It cannot mutate Vuoro state, merge, deploy, or reach operator credentials.
- The transcript is session-local; the Git branch/PR is cross-host-replicated proposal evidence, not authoritative work state.

**Effort:** S.  
**Dependencies:** Current rollout only.

---

### 2. Reproducible credential-free cloud test/build lane

**What it enables.** Useful consumption of the USD 250 credit for review, linting, unit tests, schema checks, packaging, and PR preparation without widening Vuoro authority.

**Concrete changes.**

- Add a small versioned setup script in the first owning GitHub repository, for example a new `vuoro/scripts/claude-cloud-setup.sh`, and copy that exact reviewed version into the environment configuration.
- Pin interpreter/tool versions and install packages from lockfiles or SHA-verified GitHub release artifacts. Vuoro’s existing packaging authority is release asset plus digest, not an unpinned PyPI install ([packaging design](/projects/dev/vuoro/docs/architecture/packaging.md:7)).
- Reuse the credential-free validation targets described in [LOCAL-VALIDATION.md](/projects/dev/vuoro-cloud/docs/LOCAL-VALIDATION.md:1) and the existing Makefiles rather than inventing a second CI contract.
- Start with default-deny egress:
  - allow the GitHub endpoints needed by the environment and immutable release assets;
  - do not allow Forgejo, Kubernetes endpoints, operator-network routes, or arbitrary package mirrors;
  - allow `api.vuoro.cloud` only in a separate direct-CLI experiment.
- Never install SOPS keys, cluster kubeconfig, Forgejo tokens, or promotion material.

| Workload | Cloud disposition |
|---|---|
| Unit tests, lint, schema/policy validation, static analysis, package builds | Run now |
| PostgreSQL integration tests | Run if the sandbox supports a local unprivileged service |
| Docker, kind, k3d, nested containers | Probe once; do not depend on it |
| Live PoC-cluster validation or restore drills | Operator-side |
| Forgejo landing/promotion, Flux mutation, SOPS decryption, YubiKey signing | Operator-side only |

**Assumption:** privileged nested containers and kind/k3d may be unavailable. The repositories do not establish this either way.

**Prerequisites and dependencies.**

- A GitHub-authoritative pilot repository.
- Verified package-host allowlist.
- A protected default branch.
- No dependency on E2.

**Security and blast radius.** A compromised session can read the cloned repository, alter its authorized branch, use permitted GitHub App operations, inspect environment variables, and exfiltrate over allowed egress. Keeping secrets absent is therefore more important than merely hiding them from prompts.

**Effort:** S–M.  
**Dependencies:** Independent of E2.

---

### 3. E2 MCP coordination and evidence

**What it enables.** Cloud and local agents can coordinate through authoritative state: register a run, record notes and evidence, detect competing activity, resume from the ledger, and eventually claim and complete work safely.

**Recommended first writable vertical.** Start with `register_run` plus append-only `record_evidence`/`write_session_note`. Add exclusive claiming only after its owner contract is settled.

**Concrete changes.**

- In `vuoro-cloud`:
  - extend [oauth_scopes.py](/projects/dev/vuoro-cloud/src/vuoro_cloud/oauth_scopes.py:18) with per-tool mappings for released operations;
  - add mutation classification and freeze enforcement to [gateway.py](/projects/dev/vuoro-cloud/src/vuoro_cloud/gateway.py:556), because `/mcp` currently bypasses mutation freezing on the assumption that it is read-only;
  - mint a trusted run ID and record OAuth subject, client, grant, workspace, repository, token identifier, request ID, runtime/profile metadata, and idempotency key;
  - normalize the current OAuth-user versus PAT-external-subject actor representation flagged in [D-046](/projects/dev/vuoro-cloud/17-DECISION-LOG.md:50).
- In `vuoro-mcp-edge`:
  - add strict schemas and handlers in `server.py` and `work_source.py`;
  - continue to hold no PAT, database credential, or downstream secret.
- In owner repositories:
  - Audit/evidence authority supplies append-only evidence operations.
  - Sprintctl continues to own readiness and advisory reservations.
  - ActionQ supplies the action/session lease only if an exclusive execution claim remains the desired E2 meaning.
- Pin released owner operations through `vuoro-service` composition and `vuoro-cloud/config/compatibility.json`.

Use narrow scopes, not a general `vuoro:work.write`. The existing reserved `vuoro:work.claim` and `vuoro:evidence.record` are the right pattern; `vuoro:effect.apply` must remain unavailable.

**Claim semantics require a decision.** Sprintctl reservations explicitly permit overlaps and are not leases ([reservation.py](/projects/dev/sprintctl/sprintctl/reservation.py:1)). Therefore:

- `reserve_work` may expose an advisory reservation and visible conflicts; or
- `claim_work` may represent an atomic ActionQ-owned execution lease with heartbeat, expiry, bound handle, and idempotent completion.

They must not share a name or security meaning. The retired `actionq-dispatcher` must not be revived; it is deliberately a fail-closed tombstone ([README](/projects/dev/actionq-dispatcher/README.md:1)). Routines are scheduled triggers, while Vuoro/owner state determines whether work may proceed.

**Attribution and rate limits.** Present MCP logging records bounded method/tool/client/workspace/request metadata, but not a trusted Routine run. Caller-supplied request IDs are correlation only. E2 should create a durable run/settlement record rather than treating short-retention edge logs as the ledger. Authenticated MCP calls currently share a rate bucket by `(sub, workspace)`; several Routines under one account therefore aggregate rather than receiving independent quotas ([gateway.py](/projects/dev/vuoro-cloud/src/vuoro_cloud/gateway.py:840)).

**Prerequisites and dependencies.**

- E1 proof.
- Released owner operations and compatibility pins.
- Actor identity normalization.
- Repository binding design.
- Negative tests for wrong workspace, repository, grant, stale handle, replay, and mutation freeze.

**Security and blast radius.** Medium: a compromised Routine could corrupt permitted coordination/evidence state, but not apply infrastructure or forge effects. Server-minted handles, idempotency, per-repository binding, and revocation constrain that damage.

**Effort:** L.

---

### 4. Explicit multi-repository coordination

**What it enables.** One cloud environment can work across a coordinated set of repositories without accidentally receiving workspace-wide write authority.

The current model is inconsistent: projects can bind several repositories, but the MCP edge rejects anything except exactly one repository ([server.py](/projects/dev/vuoro/packages/vuoro-mcp-edge/src/vuoro_mcp_edge/server.py:353)). Project composition itself already models ordered member repositories ([project composition](/projects/dev/vuoro/docs/architecture/project-composition.md:14)).

**Recommended shape.**

- Keep E1 single-repository.
- Add an explicit repository subset to OAuth consent/grant state.
- Put the authorized repository IDs in the token/assertion.
- Require every tool invocation to select one repository from that subset.
- Bind every run, claim, evidence entry, and idempotency key to one repository.
- Represent cross-repository work as a parent coordination item with repository-specific child items, run handles, branches, and PRs.
- Ensure the Claude GitHub App repository set is the same as or narrower than the Vuoro grant.

**Concrete changes.**

- `vuoro-cloud` OAuth grant migration, consent UI/API, `security.py`, `control.py`, and `gateway.py`.
- MCP tool input schemas and repository validation in `vuoro-mcp-edge/server.py`.
- Work/project owner contract for parent-child relations.
- Tests proving that one permitted repository cannot select another workspace member repository.

**Prerequisites and dependencies.**

- E1 remains single-repo.
- Design alongside E2; activate after the one-repository run/audit contract works.
- Clear semantics for cross-repository settlement.

**Security and blast radius.** Medium. The unsafe alternative is asserting every workspace repository and letting a tool choose implicitly. Exact subsets and repo-bound handles prevent one compromised run from gaining the whole workspace.

**Effort:** M–L.

---

### 5. Direct Vuoro CLI in cloud sessions

**What it enables.** Served Sprintctl reads and writes from an attended cloud coding session. It is not presently suitable as the Routine default.

**Required repairs.**

1. In `vuoro-client`, authenticate handshake and catalog. The client builds authenticated headers but omits them from handshake and explicitly marks catalog unauthenticated ([client.py](/projects/dev/vuoro/packages/vuoro-client/src/vuoro_client/client.py:79), [catalog](/projects/dev/vuoro/packages/vuoro-client/src/vuoro_client/client.py:145)).
2. Add regression tests and release a new client.
3. Update Sprintctl’s immutable URL/hash pin from 0.1.0 ([pyproject.toml](/projects/dev/sprintctl/pyproject.toml:23)).
4. Update Sprintctl’s unauthenticated-catalog assumptions.
5. Give every direct client and setup probe a stable named `User-Agent`; per the supplied fact, default Python `urllib` receives a Cloudflare 403.
6. Exercise rate limiting and `Retry-After` through a real cloud session.

**Credential choices.**

| Method | Assessment |
|---|---|
| Environment-variable PAT | Technically workable after repair; use only for attended experiments |
| Device bootstrap | Unsuitable for Routines: interactive and currently returns a 30-day, one-repo token with read/write/sprint/lifecycle authority |
| Connector OAuth token | Correctly unavailable to sandboxed CLI code; do not try to extract it |
| RFC 8693/workload exchange | Not implemented; future boundary and protocol work |

Sprintctl accepts only a `file:` credential reference with an owned, regular, non-symlinked, mode-0600 file ([credential loader](/projects/dev/sprintctl/sprintctl/vuoro_credentials.py:24)). A cloud setup would therefore have to:

- receive a PAT as an environment secret;
- write it without shell tracing to ephemeral mode-0600 storage;
- unset the original variable;
- delete/revoke it after the run.

This limits accidental persistence but not a malicious process inside the session.

For an attended diagnostic, use a one-repository PAT, the minimum authorities, and a 5–15 minute expiry. The API supports explicit authorities/repositories and expiries from five minutes upward ([api.py](/projects/dev/vuoro-cloud/src/vuoro_cloud/api.py:131)). Do not use the device bootstrap’s broad 30-day credential.

**If the environment variable leaks.** The bearer can be replayed from any reachable machine until expiry or revocation. Within its bound repository it can impersonate its actor and perform every granted operation—potentially reservations, handoff mutation, item creation/editing, or terminal lifecycle decisions. Repository binding prevents cross-repository use, but does not undo damage inside the authorized repository.

**Network.**

- Direct CLI requires HTTPS access to `api.vuoro.cloud`.
- Do not identify cloud workers by source IP: vendor egress may be shared.
- MCP connector use does not require sandbox egress to `api.vuoro.cloud`; the connector call is server-side.
- Keep package and API egress separate so ordinary test sessions cannot reach Vuoro unnecessarily.

**Prerequisites and dependencies.** Client release, Sprintctl repin, named-UA smoke test, and short-lived PAT operating procedure.

**Security and blast radius:** Medium–high.  
**Effort:** S–M code repair, M operational hardening.

---

### 6. EffectIntent plus trusted-side broker/reconciler

**What it enables.** A Routine can propose an auditable external action—merge, publish, deploy, artifact operation—while a trusted operator-side component decides whether and how to execute it.

This is the appropriate future use of the credential broker.

**Concrete changes.**

- Add `propose_effect` under the already reserved `vuoro:effect.propose` scope.
- Bind the intent to run ID, repository, exact effect digest, expected revision, and evidence.
- Create a new product-native trusted reconciler. Do not reuse `actionq-dispatcher`.
- On the trusted side, ask `cred-broker` for one repository, one capability, and one short TTL; record its non-secret receipt.
- Link the resulting commit, PR, object digest, or deployment evidence back to the Vuoro run.
- Keep `vuoro:effect.apply` structurally absent.
- For S3, prefer a single-object operation or pre-signed upload bound to an object key/digest over returning an S3 credential.

An RFC 8693-style exchange could later turn authenticated Vuoro run context into an internal one-run broker authorization. Its output should remain inside the trusted broker/reconciler path rather than being returned to Claude’s sandbox.

**Prerequisites and dependencies.**

- Complete E2 run identity and evidence.
- EffectIntent schema and settlement states.
- Product-native reconciler ownership.
- Broker policy and provider coverage.
- Operator-side promotion/signing remains unchanged.

**Security and blast radius.** High because real effects occur, but the cloud holds only proposal authority. The current broker already binds subject/session/host, repository, capability, policy, and TTL and records receipts ([cred-broker README](/projects/dev/cred-broker/README.md:3)); this should be composed, not duplicated in Vuoro.

**Effort:** L.

---

### 7. Hosted provider credential vending to cloud sessions

**What it enables.** Direct Forgejo, S3, cluster, merge, or deployment operations from Claude cloud. Under the current product direction, that is the wrong capability.

| Design | Exposure if session is compromised | Assessment |
|---|---|---|
| Static environment secret | Usable for its full lifetime; easily inherited, logged, or exfiltrated | Worst |
| Short-lived per-run credential | Better expiry, repository/capability narrowing, and receipts; still fully usable during its TTL | Better mechanics, wrong boundary |
| Trusted-side mediated operation | No provider secret enters cloud; exact intent can be authorized and audited | Recommended |

`credctl exec` itself injects the downstream credential into the child environment, so short TTL limits duration rather than the actions possible during that duration ([execution.py](/projects/dev/cred-broker/src/cred_broker/execution.py:10)).

Current blockers are also substantial:

- Broker identity is presently host/session/mTLS-oriented; its own plan calls for a separate workload-auth method ([implementation plan](/projects/dev/cred-broker/docs/implementation-plan.md:53)).
- The capability vocabulary covers forge/deploy operations, not Vuoro, S3, or cluster access ([models.py](/projects/dev/cred-broker/src/cred_broker/models.py:10)).
- No RFC 8693 implementation was found in the inspected sources.
- The unattended-agent acceptance gate is not closed.
- Native Claude GitHub integration already supplies the low-risk clone/branch/PR use case.

**Recommendation:** reject direct provider credential vending. Reconsider only through an explicit revision of the current trust boundary.

**Effort:** L–XL.  
**Blast radius:** Critical.

## Sequenced plan: next three sprint items

### 1. Prove E1 with one real Routine

**Scope:** Configure a single-repository Routine against `bayleafwalker/vuoro`. It verifies both tools, reads ready work, describes selected items, writes a dated assessment, and unconditionally opens a PR.

**Acceptance criteria:**

- Generation 44/0.1.74 is observed healthy.
- OAuth succeeds without a PAT or environment secret.
- Both MCP tools are visible and invoked.
- A PR is created even when zero items qualify.
- The report carries a Routine/run correlation value.
- No local Claude Code/Codex MCP attachment is added.
- No Forgejo, cluster, SOPS, or promotion credential enters the environment.

### 2. Establish the cloud build lane and repair CLI transport

**Scope:**

- Add a pinned, versioned setup script and least-egress policy for credential-free tests/builds.
- Fix authenticated handshake/catalog and named `User-Agent` behavior in `vuoro-client`.
- Release it and update Sprintctl’s immutable dependency pin.

**Acceptance criteria:**

- Pure validation runs from a fresh cloud environment.
- Setup does not print or persist secrets.
- GitHub branch/PR works while default-branch merge, release, Forgejo, cluster, and SOPS access do not.
- Negative tests show handshake/catalog fail without authorization and succeed with it.
- A separate attended smoke test reaches `api.vuoro.cloud` with a short-lived read-only PAT and named UA.
- PAT expires or is revoked immediately after the smoke test.

### 3. Land the first E2 owner-backed writable vertical

**Scope:** Decide repository binding and claim semantics, normalize actor identity, then implement server-minted `register_run` plus idempotent append-only evidence/session-note recording. Keep `claim_work` and heartbeat reserved until a released exclusive-lease owner exists.

**Acceptance criteria:**

- Run handle is bound to OAuth subject, client, grant, workspace, and one repository.
- Retries with the same idempotency key return the same result.
- Wrong repository, wrong grant, stale handle, and replay are refused.
- Mutation freeze applies to the new tools.
- The durable record links the Routine PR/commit to its evidence.
- No effect, provider credential, or broad `work:write` scope is introduced.

## Open questions only the operator can answer

### 1. Which repository should receive the first Routine’s report?

- Options: `vuoro`, `vuoro-cloud`, or `agentops`.
- **Recommendation:** `vuoro`. It is GitHub-authoritative and exercises the runtime repository without giving the cloud infrastructure authority. `vuoro-cloud` is Forgejo-authoritative with GitHub as a mirror, so a GitHub PR there would be proposal evidence rather than landed canonical work ([CI authority](/projects/dev/vuoro-cloud/docs/CI-AND-INTEGRATION.md:3)).

### 2. What GitHub authority may cloud sessions hold?

- Options: non-protected branch push + PR; ordinary repository write; merge/release/admin.
- **Recommendation:** non-protected branch push and PR only, with a protected default branch and no merge, release, environment, or administration authority.

### 3. What should E2 `claim_work` mean?

- Options:
  - advisory Sprint reservation;
  - exclusive ActionQ-owned execution lease;
  - defer claiming and ship evidence/run recording first.
- **Recommendation:** ship run/evidence first, then make `claim_work` an exclusive owner-backed lease. Retain `reserve_work` as a separately named advisory operation.

### 4. May Routines receive direct CLI credentials?

- Options: none; short-lived read-only PAT; write-capable PAT/device token.
- **Recommendation:** none. Permit a 5–15 minute read-only PAT only in an attended diagnostic session. A write-capable Routine credential should require an explicit trust-boundary revision.

### 5. When may one Routine touch several repositories?

- Options: immediately; after E1 with an exact repository subset; unrestricted workspace membership.
- **Recommendation:** keep E1 single-repository. Design exact-subset grants alongside E2 and activate them only after repo-bound run handles and audit are proven. Never infer write authority from whole-workspace membership.

The supplied generation-44/0.1.74 facts were treated as authoritative; the checked-in status and compatibility files are stale. No files, network state, or credentials were changed or accessed.