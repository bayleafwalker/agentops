# Design memo: trusted-service boundary MCP ("vuoro-effects") on the vuoro-cloud cluster

Date: 2026-09-26. Read-only design pass against the working trees under `/projects/dev`. Line numbers are from the files as read today. Inferences are marked **Assumption**.

## Recommendation

Build the trusted service as a separate MCP resource (`https://api.vuoro.cloud/effects/mcp`) in a new operator-only namespace, `vuoro-effects`. It should not live in the tenant runtime or in `vuoro-system`. The existing gateway stays the single public entry point and OAuth resource server, and control stays the single authorization server. Only a new audience and a new tool-to-scope table are added. Inside the namespace there are three pods, each able to reach only the next hop:

1. **An effects edge.** It speaks MCP, validates schemas, records the intent, and holds no provider credential. Owner: `vuoro`.
2. **An executor.** It holds the provider credential as a mounted file and independently re-verifies the caller before one bounded provider call. Owner: `cred-broker`, as its planned proxy-delivery mode and workload-auth method.
3. **An egress proxy.** It is the only pod allowed to reach the internet, and only to allowlisted hosts over 443. It sits behind a CIDR `ipBlock` NetworkPolicy. Owner: `vuoro-cloud`.

The cluster CNI cannot enforce FQDN rules. The PoC runs k3s with its bundled flannel/kube-router, which enforces only standard NetworkPolicy. The host allowlist therefore has to be enforced at L7 in the proxy, with CIDRs as a second layer. The Cloudflare tunnel is inbound only and restricts nothing on the way out.

Every tool maps to a "read" scope or to the already-reserved `vuoro:effect.propose` scope. `vuoro:effect.apply` stays structurally rejected. The trusted side decides whether a proposal runs automatically (reversible, non-authoritative effects on allowlisted repositories) or waits for the operator. Merge, promotion/signing, secrets and cluster mutation are never offered.

The first slice is one effect: `forge_comment_pr` on one allowlisted Forgejo repository, using a dedicated read-collaborator bot token stored in SOPS. It proves the whole boundary with a provider blast radius of "comments on allowlisted repositories". After that come Forgejo CI status, opening a PR from a pushed branch, an approval-gated merge request, and E2 run binding.

This placement revises two accepted target-state rows. TS-16 describes a *homelab-side* reconciler, and TS-1 forbids Vuoro itself from scheduling or executing intents (`/projects/dev/agentops/docs/plans/2026-09-17-target-state.md:30`, `:45`). Both amendments follow from the operator's stated direction and should be recorded as decision-log entries. They are not open questions.

---

## Component diagram

```
 Claude Code cloud session / Routine            (untrusted: holds only an OAuth access token, aud=effects)
        |  HTTPS  MCP  (Bearer at+jwt, 15 min)
        v
 Cloudflare edge --> cloudflared (vuoro-system)          [INBOUND ONLY; its own egress is 443/7844 to anywhere]
        |  http :8080  (hostname api.vuoro.cloud)
        v
 +-------------------------- vuoro-system -------------------------------------------+
 |  vuoro-gateway  (OAuth resource server for BOTH resources)                        |
 |    /mcp          aud=https://api.vuoro.cloud/mcp          -> tenant runtime :8081 |
 |    /effects/mcp  aud=https://api.vuoro.cloud/effects/mcp  -> vuoro-effects  :8090 |
 |    per request: JWT verify, grant/membership/epoch SQL, EFFECT_TOOL_SCOPES row,   |
 |    mutation freeze, (sub,workspace,tool) rate bucket, operator-workspace allowlist|
 |    mints X-Vuoro-Identity (aud=vuoro-effects, 30 s, jti) + forwards access token  |
 |  vuoro-control  (OAuth AS: 2 resources, pre-registered clients, audit_events)     |
 +-----------------------------------------|-----------------------------------------+
                                           | TCP 8090 (NetworkPolicy: gateway pods only)
 +---------------------------- vuoro-effects (new, default-deny) --------------------+
 |                                                                                  |
 |  effects-edge (vuoro)              NO provider credential                        |
 |    MCP catalog, strict schemas, repo allowlist lookup, idempotency, intent row   |
 |        | TCP 8091 (edge -> executor only)            | TCP 5432 -> vuoro-data    |
 |        v                                             v (own DB/role: effects)    |
 |  effects-executor (cred-broker proxy mode)   Secret file mount: forgejo-bot token|
 |    re-verifies access token (AS key) + gateway assertion (jti single-use),       |
 |    policy: (workspace, repo, capability) -> allow | step-up | deny,             |
 |    one provider call, secret-free receipt, returns non-secret result only       |
 |        | TCP 3128 (executor -> proxy only)                                       |
 |        v                                                                         |
 |  egress-proxy (smokescreen-class CONNECT proxy)                                  |
 |    host allowlist (SNI/CONNECT host), denies RFC1918/link-local/loopback,        |
 |    re-resolves DNS per connection; NetworkPolicy ipBlock egress 443 to the       |
 |    rendered CIDR list only                                                       |
 +-----------------------------------------|----------------------------------------+
                                           | 443
                                           v
         git.apps.kotona.app (Forgejo)   api.github.com   (later: S3 endpoint)

 Out of band, operator only: SOPS keys and .sops.yaml, YubiKey promotion signing,
 Flux sops-age Secret, merge execution (credctl on devbox), approval of queued intents.
```

---

## 1. Placement and ownership

### What the architecture already says

- **Tenant runtimes are coordination-only and egress-starved.** The tenant `allow-required` policy allows DNS and PostgreSQL only (`/projects/dev/vuoro-cloud/src/vuoro_cloud/tenant.py:368-399`). The MCP edge container is deliberately started with "no envFrom, no DSN Secret, no token" (`tenant.py:639-654`).
- **The product boundary excludes custody.** "Vuoro Cloud | operated deployment of Vuoro Server | customer execution, repositories or credentials" (`/projects/dev/vuoro-cloud/19-PRODUCT-POSITIONING-AND-PROOF.md:81`). "Long-lived cloud, model or cluster credentials remain on the user-owned side" (`06-CONNECTORS-DISPATCH-AND-EXECUTION.md:187`). "Secret brokering" is listed under a deferred hosted-execution design (`06-...md:190-198`).
- **`vuoro-system` holds the identity-signing keys.** Those are the AS signing key and the gateway signing key (`platform/runtime-secrets/kustomization.yaml`). The namespace also has a blanket "all pods -> any namespace :8080" egress rule (`platform/policies/network-policies.yaml:27-38`).
- **The tenant controller is confined.** A ValidatingAdmissionPolicy limits it to `vuoro-ws-*` namespaces (`apps/tenant-controller/admission-policy.yaml:27-35`), so a non-`vuoro-ws-` namespace is outside its reach.

### Options

| Option | Verdict |
|---|---|
| **A. Per-tenant**: a third container in the runtime pod, or a pod in `vuoro-ws-*` | **Reject.** It would open internet egress in every tenant namespace, put operator credentials where the tenant controller can create and patch Secrets (`apps/tenant-controller/deployment.yaml:74-75`), and contradict `19-...md:81`. The credentials belong to the operator, not to a tenant. |
| **B. A platform service in `vuoro-system`** | **Reject.** It would put provider credentials next to the AS and gateway signing keys, so one namespace-scoped Secret read would yield both identity forgery and provider access. It would also inherit the broad 8080 egress rule. |
| **C. A separate operator-only namespace, `vuoro-effects`, behind the existing gateway** | **Recommend.** It has its own default-deny policy, its own Secret scope, is outside the controller's admission scope, and needs no new tunnel hostname or second resource server. |

Under option C the service is treated as the operator's own connector that happens to be hosted on the operator's cluster. That matches the connector model's `cluster-operator` / `execution-environment` kinds (`06-...md:36-46`). It serves only an allowlist of workspace IDs (the operator's), which is enforced at the gateway and re-checked in the executor. Tenants never see the route.

Record this as a decision-log entry in `/projects/dev/vuoro-cloud/17-DECISION-LOG.md`, next to D-046. Also record a TS-16/TS-1 amendment in agentops. TS-1 still holds in substance: Vuoro stores and serves the intent record, and the executor, which is not Vuoro, is the component that executes.

### Ownership split

| Part | Owner repo | Why |
|---|---|---|
| Namespace, NetworkPolicies, egress proxy Deployment and allowlist, SOPS Secret, Flux wiring, CIDR renderer CI job | `vuoro-cloud` | Owns "Flux platform composition" and "public environment policy" (`13-REPO-OWNERSHIP-AND-CHANGE-MATRIX.md:7-20`). |
| Gateway `/effects/mcp` route, `EFFECT_TOOL_SCOPES` table, second RFC 8707 resource in control, workspace allowlist | `vuoro-cloud` (`src/vuoro_cloud/gateway.py`, `oauth_scopes.py`, `control.py`) | These are the resource server and AS that already exist (D-045/D-046). |
| `effects-edge` MCP process (schemas, intent record, idempotency) | `vuoro`, as a new package next to `packages/vuoro-mcp-edge` that reuses its assertion verification and JSON-RPC handling | Vuoro owns the MCP edge pattern and the intent/correlation record (TS-1). |
| `effects-executor` (policy, credential custody, provider adapters, receipts) | `cred-broker` (credctl) | It already has `Delivery.PROXY` (`/projects/dev/cred-broker/src/cred_broker/models.py:32-35`), secret-rejecting receipts (`receipts.py:14-47`), a repository registry, and GitHub App / Forgejo adapters (`adapters.py:90-273`). Its own plan calls for "a dedicated workload auth method" (`docs/implementation-plan.md:63-64`). Compose it rather than duplicating it in Vuoro (earlier memo, option 6). |
| EffectIntent lifecycle contract and settlement acceptance | `actionq` (the live `/projects/dev/actionq`, **not** the `actionq-dispatcher` tombstone, `/projects/dev/actionq-dispatcher/README.md:1-20`) | ActionQ owns "execution lifecycle and accepted action outcomes" (`19-...md:77`). Slice 1 uses a minimal ledger shaped to this contract. Moving it to ActionQ is a named follow-up, not an implicit one. |

---

## 2. Egress enforcement: what the cluster can actually do

### Facts

- **PoC cluster (live).** Native k3s `v1.36.3+k3s1` (`terraform/environments/poc/poc.tfvars:8`). The k3s config disables only `traefik` and `servicelb` (`terraform/environments/poc/cloud-init.yaml.tftpl:39-41`), so the bundled flannel CNI and the embedded kube-router NetworkPolicy controller are active. `network-policies.yaml:81-87` confirms this: "the k3s policy controller evaluates egress" after kube-proxy DNAT. The controller enforces **standard `networking.k8s.io/v1` NetworkPolicy only**: pod/namespace selectors, `ipBlock` CIDR with `except`, and ports. There are no FQDN rules, no L7 rules and no cluster-wide default policy. Every namespace needs its own `default-deny`, following `network-policies.yaml:1-5`.
- **Talos green environment (not live).** `terraform/environments/talos/main.tf:119-131` patches only `machine.network.interfaces`, with no `cluster.network.cni` patch.
  - **Assumption:** this means Talos's default flannel, which ships no NetworkPolicy controller. Every policy in `platform/policies` would then be accepted by the API server but **not enforced** on Talos, and the same would apply to the effects policies.
  - This must be closed before any Talos cutover. The options are Cilium, which also offers `toFQDNs`, or a kube-router policy controller. Verify first with a deny test, as `08-K3S-POC-DEPLOYMENT.md:58` already requires.
- **Node firewall.** The Hetzner firewall allows outbound TCP 443/587, UDP/TCP 53, UDP 123 and UDP 7844 to `0.0.0.0/0` (`terraform/modules/hetzner-k3s-node/main.tf:29-60`). It gives no per-pod narrowing.
- **Tunnel.** cloudflared is an outbound-initiated connector for **inbound** traffic (`platform/cloudflared/deployment.yaml:33-37`). Its own pod may reach anything on 443/7844 (`network-policies.yaml:57-63`). It does not constrain other pods' egress.
- **Existing gap (not caused by this design).** Control may reach any host on 443 (`network-policies.yaml:66-72`) for GitHub OAuth. It is noted here because it is the same kind of problem.

### Options

| Mechanism | Available now? | Strength | Verdict |
|---|---|---|---|
| NetworkPolicy `ipBlock` CIDR allowlist | Yes (kube-router) | L3 only. Weak for CDN-fronted hosts: a Cloudflare or GitHub range admits every tenant of that range. | Use as the **second** layer. |
| FQDN policy (Cilium `toFQDNs`, Calico DNS policy) | No (CNI swap) | Good | Revisit on Talos if Cilium is chosen. |
| Egress proxy with host allowlist (smokescreen or Envoy SNI filter) | Yes (a pod) | L7 host-level allowlist. Denies private, link-local and loopback targets and re-resolves DNS. This matches the precedent in `10-THREAT-MODEL-AND-SECURITY-GATES.md:148-152`. | Use as the **primary** layer. |
| Cloudflare Gateway / WARP egress | Would require the WARP connector | Good, but moves policy to an external control plane | Not recommended now. |

### Recommended layering

1. The `effects-edge` and `effects-executor` pods have **no internet egress**. The edge gets DNS, `vuoro-data:5432` and `executor:8091`. The executor gets DNS and `proxy:3128`.
2. The proxy pod gets egress to `ipBlock` CIDRs on TCP 443 only, rendered from a checked-in list. Private ranges are listed in `except`.
3. The proxy allowlist names exact hosts: `git.apps.kotona.app` first, and `api.github.com` when GitHub effects arrive. CONNECT is limited to 443. There are no redirects to non-allowlisted hosts, and response sizes are capped.
4. **Keeping the lists current.** A credential-free scheduled CI job in `vuoro-cloud` does the following:
   - fetches `https://api.github.com/meta` (the `api` and `git` keys), the published Cloudflare ranges if Forgejo is Cloudflare-fronted, and the S3 endpoint range later;
   - renders `platform/effects/egress-cidrs.yaml`;
   - opens a PR when the list changes. Flux applies it after the normal review and promotion.

   Drift fails closed: a new GitHub address is dropped until the PR lands. It is never silently allowed.
5. **Assumption:** the network path from Hetzner to `git.apps.kotona.app` is unverified. Forgejo may be Cloudflare-fronted or Cloudflare-Access-protected. Its public addresses, and whether it accepts non-browser API calls from the cluster's egress IP, must be checked (`dig` plus an unauthenticated `/api/v1/version` probe from a debug pod) before slice 1 is built. If it is Cloudflare-fronted, the CIDR layer is nearly meaningless for it, and the proxy's host allowlist is what actually protects it.

---

## 3. Effect model

### Scope model

- Add the resource `https://api.vuoro.cloud/effects/mcp` to control. Today control refuses any other resource (`src/vuoro_cloud/control.py:845-846`, `:1142-1143`).
- Add an `EFFECT_TOOL_SCOPES` table beside `MCP_TOOL_SCOPES` (`src/vuoro_cloud/oauth_scopes.py:42-45`).
- Scopes:
  - `vuoro:forge.read`, which is new, for provider reads;
  - `vuoro:effect.propose`, already reserved (`oauth_scopes.py:26-29`), for everything that mutates a provider.
- `vuoro:effect.apply` stays in `REJECTED_SCOPES` (`oauth_scopes.py:31-35`). The cloud never holds execution authority; it proposes, and the executor's policy tier decides between `auto` and `operator-approval`.
- Grant the effects resource only to one pre-registered client (the Claude connector client) and only for workspaces on the operator allowlist.

### Common envelope for every effect

- **Input:** `repository` (Vuoro `repo_id`), `idempotency_key` (UUID), `correlation_id` (Routine or run value), and `run_id` (optional until E2, required after).
- **Output:** `intent_id`, `state` (`executed | pending_approval | refused | failed`), a non-secret provider result (URL, id, SHA), and `receipt_id`.
- **Audit:**
  - an intent row (sub, client_id, grant_id, workspace, repo, tool, digest of the normalized arguments, idempotency key, token `jti`, assertion `jti`, request_id, state transitions);
  - a cred-broker decision receipt (`receipts.py`), which cannot store secrets;
  - a gateway `mcp_exchange` log line (`gateway.py:83-93`);
  - after E2, a `record_evidence` entry on the run.
- **Idempotency:** the key is scoped to `(sub, workspace, tool, repo)`.
  - Same key and same argument digest returns the stored result.
  - Same key with a different digest is refused as `idempotency-conflict`.
  - Mutations also embed an `vuoro-intent:<intent_id>` marker in the provider object (a comment footer or PR body trailer). The executor searches for the marker before acting, so a lost ledger cannot cause a double effect.

### First effects

| # | Tool | Scope | Policy checks (trusted side) | Tier |
|---|---|---|---|---|
| 1 | `forge_comment_pr` | `vuoro:effect.propose` | Repo on the allowlist and in `assertion.repo_ids`. PR exists and is open. Body ≤ 8 KiB, plain markdown, no `@`-mentions of non-collaborators, and no URL to a host outside the allowlist. Per-repo rate of N per hour. | auto |
| 2 | `forge_ci_status` | `vuoro:forge.read` | Repo on the allowlist. SHA is 40 hex. Returns job names, conclusions and a URL only, **never logs**, since logs can carry secrets. | auto (read) |
| 3 | `forge_open_pr` | `vuoro:effect.propose` | Head branch matches `cloud/<run-or-corr>/*` and exists at the stated SHA. Base is the default branch, which is protected. Title and body are capped. One open PR per head. | auto |
| 4 | `request_merge` | `vuoro:effect.propose` | PR open. `head_sha` equals the stated SHA. Required CI is green on that SHA. Fast-forward is possible. The result is a `pending_approval` intent only. | **operator approval**. The executor does not merge in this design (see open question 2). |
| 5 | `record_evidence_object` (later, optional) | `vuoro:effect.propose` | Single object key under a run prefix. Content digest supplied. Size cap. Pre-signed PUT bound to key and digest, or a server-side put. | auto. Deferred because S3 custody is a stated non-goal (`14-OPEN-QUESTIONS-AND-NON-GOALS.md:56`) and E2 evidence belongs to the Vuoro/auditctl authorities. |

On GitHub, Claude's own GitHub App already provides branch push and PR creation for cloud sessions (earlier memo, option 1). GitHub variants of effects 1-3 therefore add little. The service's value lies in Forgejo, which cloud sessions cannot reach, and in approval-gated authority.

### Never offered, by structure and not only by policy

- **Secrets:** any write to a Secret, a SOPS file, `.sops.yaml`, an age/PGP key, or a provider credential. Also any tool that returns a token, pre-signed credential, or key.
- **Signing and deployment:** promotion or signing (the YubiKey flow in `scripts/promote-release.sh:30-34`), Flux suspend/resume/reconcile, and any kubectl or cluster API action. The executor runs with `automountServiceAccountToken: false` and has no route to the API server.
- **Unapproved merges:** any merge to a protected branch without an operator approval, force-push, or branch or tag deletion on protected refs.
- **Provider administration:** repository settings, collaborators, webhooks, deploy keys, branch protection, Actions secrets or variables, and release publishing.
- **Remote code execution:** `workflow_dispatch` or re-run with inputs, which is execution on a runner with CI secrets.
- **Generic reach:** any generic HTTP fetch or proxy tool (SSRF) and any provider call whose target host comes from caller input.

---

## 4. Credential handling inside the boundary

- **Storage.** Add a new file `platform/effects/forgejo-bot.secret.yaml`. The existing rule `(platform|deploy)/.*secret.*\.ya?ml$` (`.sops.yaml:31`) already covers it, so no SOPS configuration change is needed. Flux decrypts it with the operator-created `sops-age` Secret (`clusters/bootstrap/poc/resources.yaml:36-41`). The Secret exists only in `vuoro-effects`. It is mounted as a read-only **file** (mode 0400) into the executor container only, never as an environment variable, and not into the edge or the proxy.
- **Provider identity for slice 1.**
  - A dedicated Forgejo bot user, added as a **read** collaborator on each allowlisted repository only. Read access is enough to comment on issues and PRs.
  - A token with scopes `write:issue` and `read:repository`.
  - Provider-side blast radius: read allowlisted repositories and comment on them.
  - `forge_open_pr` (slice 3) needs write access to non-protected branches. Keep branch protection on `main` and consider a separate bot or token for that tier.
- **Short-lived where possible (later).** Replace the static token with cred-broker minting, once its live-adapter and unattended-agent gates close (`/projects/dev/cred-broker/docs/acceptance-status.md`, "The unattended-agent gate is **closed**"):
  - Forgejo v16 Generic JWT integration, or a GitHub App installation token narrowed to one repository and one permission set (`README.md:15-18`, `adapters.py:160-230`);
  - a TTL of ≤ 5 minutes per effect;
  - the signing key in OpenBao Transit, or at least in its own SOPS Secret.
- **Rotation.** The static bot token expires after 30 days. Rotation means the operator mints a new token and runs `sops edit` on the value (agents may change values, but do not mint provider tokens), then promotes the change through the normal Flux path. Record a rotation runbook entry beside `docs/runbooks/credential-rotation.md`.
- **Never returned.** Executor results pass through an allowlisted output schema (IDs, URLs, SHAs, conclusions). Provider response bodies are not relayed. cred-broker's `assert_non_secret` receipt guard (`receipts.py:31`) is reused on the result as well as the receipt.
- **Relation to credctl.** The local `credctl` (pinned in `/projects/dev/gitops-nixos/pkgs/credctl.nix:1-15, 60-67`) remains the operator's attended tool, for example for fast-forward merges (`credctl merge ... --style fast-forward-only`, per agentops handoffs). The executor is a second deployment of the same broker core with:
  - a different authentication method: gateway assertion plus AS access-token verification instead of an mTLS host session (`implementation-plan.md:63-64`);
  - `Delivery.PROXY` only, with vending disabled;
  - its own policy file listing `(workspace, repo_id) -> provider repo -> capabilities`.

  Decision receipts share one schema, so the audit story is uniform across devbox and cluster.

---

## 5. Threat model

| Threat | Mitigations | Residual blast radius |
|---|---|---|
| **T1. Compromised cloud session with a valid grant** (including stolen access or refresh tokens) | Audience-separated token: a work-read token is useless on `/effects/mcp`. Per-tool scopes. Operator-workspace and repository allowlists. Auto tier limited to reversible, non-authoritative effects. Per-(sub, workspace, tool) rate limits. The mutation freeze **is** applied to `/effects/mcp`, unlike today's `/mcp` (`gateway.py:559-563`, D-046 (14)). Grant revocation takes effect on the next request (D-046 (2)). Refresh-token reuse revokes the grant (D-045 (7)). | Comments, and later PRs, on allowlisted repositories until revocation or freeze. No merge, deploy, or secret access. |
| **T2. Prompt-injected agent** (it reads a hostile issue or PR and requests an effect) | The same allowlists apply. Content checks on comments (no external URLs or mentions). Output never includes CI logs or provider bodies. Approval tier for anything authoritative, with the operator shown the exact argument digest, head SHA and linked run. Comments carry the intent marker, so injected output is attributable. | Low-integrity text on allowlisted private repositories. The exfiltration channel is limited to readers of those repositories. |
| **T3. Replay** (captured access token or in-cluster assertion) | Access token lifetime is 15 minutes (`oauth_server.py:35`). Gateway assertion lifetime is 30 s (`config.py:39`) and its `jti` must equal `request_id` (`vuoro-service/gateway_identity.py:245-251`). The executor keeps a single-use `jti` cache for effects assertions. The effects assertion audience is `vuoro-effects`, distinct from the shared `vuoro-service` audience (`config.py:31`). The idempotency-key digest binding turns replays into no-ops or conflicts. | A replay within 30 s from inside the cluster yields the same stored result, not a second effect. |
| **T4. Confused deputy across tenants or repositories** | The provider repository is looked up from a Git-reviewed binding `(workspace_id, repo_id) -> forgejo:owner/name` and is never taken from caller input. It is checked against `assertion.repo_ids`. Today those are all of the workspace's repositories (D-046 (12)), and exact-subset grants narrow this after E2. The executor re-checks the workspace allowlist independently of the gateway. Tenant namespaces cannot reach `vuoro-effects` (ingress from gateway pods only). The controller cannot write there (admission policy). | Bounded to the operator's workspace and its allowlisted repositories. |
| **T5. Compromised effects-edge** | It holds no credential. The executor re-verifies both the AS-signed access token (aud=effects, AS public key) and the gateway assertion, so the edge cannot fabricate requests for other subjects or repositories. NetworkPolicy prevents the edge from reaching the proxy. | It can re-issue effects that authenticated callers were already allowed to request in the last 30 s. |
| **T6. Compromised executor or trusted service** | The bot token has provider-minimal rights (read plus comment on allowlisted repositories). Egress goes only via the proxy to allowlisted hosts. No SA token and no API-server route. It is in a separate namespace from the AS and gateway signing keys. It is read-only-rootfs, runs as non-root, and drops all capabilities. Receipts are append-only in PostgreSQL, which is covered by CNPG backup. Later the token becomes ≤ 5-minute minted tokens with keys in OpenBao Transit. | The bot token's rights, until the operator revokes it at Forgejo. It cannot reach cluster, SOPS, promotion, or other provider accounts. |
| **T7. Compromised gateway or control** (pre-existing trust root) | Already trusted for every tenant. Requiring the AS token at the executor means the gateway key alone is not enough; the AS key in control is also needed. | Same as today for Vuoro data, plus the effects above. |
| **T8. Malicious Git change to the allowlist or policy** | Flux reads the GitHub replica, but deployment requires the YubiKey-signed promotion (`scripts/promote-release.sh:2-34`). Cloud sessions push only non-protected branches (decision 2). | Unchanged by this design. |

**Blast radius compared with today.**

- **Cloud sessions today:** Vuoro `work.read`, plus GitHub branch push and PR through Claude's app.
- **After slice 1:** those, plus comments on N allowlisted Forgejo repositories, recorded and attributable.
- **Operator credentials:** unchanged. They stay on the devbox (credctl) and the YubiKey. The one new custody item is a comment-only bot token held in a namespace that cannot reach anything but one proxy.

---

## 6. Composition with E2 and exact-subset grants

- **Before E2 (slice 1).** `run_id` is optional. The edge mints `intent_id` and records the caller's `correlation_id` as correlation only, as in the earlier memo, option 1.
- **With E2 `register_run`.** Every effects tool requires `run_id`. Binding options:
  - **(a) Recommended:** E2 returns the run handle as a short-lived, gateway-verifiable token bound to `(sub, workspace, repo_id, run_id, exp)`. The effects edge and executor verify it offline and reject a `repository` that differs from the run's repository.
  - **(b)** The executor calls the tenant runtime's `describe_run` through a new gateway-internal service principal. This is more moving parts and adds cross-namespace egress.
- **Settlement.** After execution, the edge records the outcome to the run via E2 `record_evidence`: intent id, provider URL or SHA, and receipt id. The durable chain is then Routine PR/comment -> intent -> receipt -> run.
- **Exact-subset grants.** Once grants carry an exact repository subset, the gateway puts that subset in `repo_ids` instead of all of the project's repositories (`MCP_GRANT_QUERY`, `gateway.py:137-150`), and effects inherit the narrowing with no change to effects code.
- **Claims.** When `claim_work` becomes an ActionQ lease (decision 3), `request_merge` can additionally require that the run holds the live lease for the work item. A stale worker's intent then settles as `refused-stale`, which is the property claimed in `19-...md:109-124`.

---

## 7. Minimal first slice: `forge_comment_pr` end to end

### Scope

- **`vuoro-cloud`:**
  - namespace `vuoro-effects` (restricted Pod Security) and its default-deny plus the three allow policies;
  - an egress-proxy Deployment and host allowlist, and a CIDR list for `git.apps.kotona.app`;
  - a gateway allow rule to TCP 8090;
  - a `vuoro-data` ingress rule for the edge (`network-policies.yaml:109-118` pattern), plus the `effects` database and role;
  - the gateway `/effects/mcp` route with an RFC 9728 document, the `EFFECT_TOOL_SCOPES` table, the mutation freeze, the workspace allowlist, and the effects assertion audience;
  - the second resource in control;
  - the SOPS Secret file and a D-048 decision entry.
- **`vuoro`:** the `vuoro-effects-edge` package with one tool, released and pinned.
- **`cred-broker`:** proxy-mode service with gateway and AS token verification and a Forgejo comment operation.
- **Canary:** first allowlist only a dedicated canary repository (for example `forgejo:bayleaf/vuoro-effects-canary`). Add `bayleaf/vuoro-cloud` after the acceptance criteria pass.

### Acceptance criteria

1. From a Claude Code cloud session or Routine, the effects connector completes OAuth against `/effects/mcp`. `tools/list` shows exactly `forge_comment_pr`. A token minted for `/mcp` is refused on `/effects/mcp` (401, audience), and the reverse is also refused.
2. A call against the canary PR posts one comment carrying the `vuoro-intent:<id>` marker. The result contains only `intent_id`, the comment URL and id, `receipt_id`, and `state=executed`.
3. Retrying with the same idempotency key returns the same result and creates no second comment. Reusing the key with different arguments returns `idempotency-conflict`. After deleting the ledger row, a retry finds the marker and does not double-post.
4. Negative cases are refused with no provider call recorded at the proxy:
   - a repository not on the allowlist;
   - a `repo_id` outside `assertion.repo_ids`;
   - a non-operator workspace;
   - a missing scope;
   - a closed PR;
   - an oversized body;
   - a body with an external URL;
   - a replayed assertion `jti`;
   - an active mutation freeze;
   - a revoked grant (the next request fails).
5. Egress is proven:
   - from the executor pod, `curl https://example.com` through the proxy is denied and a direct connection times out;
   - from the edge pod, any 443 connection fails;
   - the proxy refuses `169.254.169.254`, `10.43.0.1` and a non-allowlisted host;
   - a kube-router deny test is recorded as evidence.
6. Secrets stay contained:
   - the token appears in no environment variable (`kubectl exec ... env`), no log line, no receipt and no tool result (grep over pod logs and the receipts table);
   - the Secret is mounted only in the executor;
   - `automountServiceAccountToken: false` is set on all three pods.
7. An audit trace links the gateway exchange log, the intent row, the cred-broker receipt, and the Forgejo comment by `request_id` and `intent_id`.
8. No change to `/mcp` behaviour, to tenant namespaces, or to the AS signing key. `make check-fast` and the Conftest/staged Kubernetes gates pass. Generation N+1 promotion is signed by the operator.

### Sequence after slice 1

1. **`forge_ci_status`** (read). Same machinery plus the log-exclusion test.
2. **Allowlist `bayleaf/vuoro-cloud`** and wire the CIDR-renderer CI job.
3. **`forge_open_pr`** from a `cloud/*` branch, which needs a branch-write identity and a decision on which remote the cloud session pushes to.
4. **E2 run binding** made mandatory (§6(a)), with settlement written as run evidence.
5. **`request_merge`** as `pending_approval` plus an operator approval surface (open question 2).
6. **Replace the static bot token with cred-broker-minted ≤ 5-minute tokens**, once its gates close.
7. **Before any Talos cutover**, a policy-enforcing CNI and the full `platform/policies` deny-test suite.

### Operator actions slice 1 needs (instructions, not questions)

This is provider administration that only the operator holds.

- **On `git.apps.kotona.app`** (Forgejo admin UI):
  1. Create the user `vuoro-effects-bot`.
  2. Create the repository `bayleaf/vuoro-effects-canary` with a protected `main` branch and one open PR.
  3. Add the bot as a **Read** collaborator on that repository only.
  4. As the bot, create a token with scopes `write:issue` and `read:repository` and a 30-day expiry.
- **Precondition to verify first:** from a debug pod on the PoC, `curl -sS https://git.apps.kotona.app/api/v1/version` returns JSON. An agent can run this during implementation.
- **Then:** in `/projects/dev/vuoro-cloud`, run `sops edit platform/effects/forgejo-bot.secret.yaml` and set `stringData.token`. The agent creates the file skeleton; the operator enters the value.
- **Expected result:** `sops -d` of the file (operator side only) shows the key, and the agent sees only an encrypted diff.
- **Send back:** "token placed" and the bot's user id. Do not send the token.

---

## 8. Operator-only open questions

1. **Should the effects surface ever serve non-operator workspaces?**
   - (a) Operator workspace only, permanently. This keeps `19-...md:81` true for customers.
   - (b) Operator only now, with productization reconsidered under the deferred hosted-execution design (`06-...md:190-198`).
   - (c) Offer it to tenants now.

   **Recommend (b).** The allowlist is enforced in code, and productization requires its own threat-model pass.

2. **Who executes an approved merge?**
   - (a) The executor never holds merge authority. `request_merge` produces a queued intent plus a pre-verified `credctl merge ... --head-sha <sha> --style fast-forward-only` command that the operator runs locally.
   - (b) The operator approves in the Vuoro web UI with passkey step-up, and the executor merges with a merge-capable token.
   - (c) Approval by a Forgejo PR label that the executor watches.

   **Recommend (a)** until cred-broker's unattended gate closes. It keeps merge credentials off the cluster and matches decision 2, and (b) can be added later without changing the intent schema.

3. **Provider identity for slice 1.**
   - (a) A static, read-collaborator bot token in SOPS with 30-day rotation (the design above).
   - (b) Wait for cred-broker's Forgejo v16 JWT or GitHub App minting to pass its live gates.
   - (c) Reuse an existing operator token.

   **Recommend (a).** Its blast radius is comment-only on allowlisted repositories and it unblocks the slice now. (c) is rejected because it would put operator-wide authority on the cluster.

4. **Auto tier compared with TS-16's "maximum outcome is an unmergeable branch and a queued intent".**
   - (a) Amend TS-16 to allow auto-executed, reversible, non-authoritative effects (comment, CI read, PR open into a protected base).
   - (b) Keep every mutation queued for approval, including comments.

   **Recommend (a).** The operator's stated direction, "the trusted service decides and executes", implies it, and approval fatigue on comments would erode the approval signal that matters for merges. This is listed as a question only because it changes an accepted operator row. If the operator's statement is taken as already deciding it, record the amendment and proceed.
