# Cloud enablement plan after E1 (2026-09-26)

Status: adopted by the operator 2026-09-26 (session d5ca23ce), except where a
line says it waits on review.
Inputs:
- [options memo](2026-09-26-cloud-environments-options-memo.md), Codex gpt-5.6-sol, read-only;
- [trusted-service boundary design](2026-09-26-trusted-service-boundary-design.md), Claude, read-only. Codex's adversarial review of it rejected the design (1 critical, 8 high, 4 medium); see decision 7.

## Where things stand

- **E1 is done (agentops#2514, accept decision #143).** A hosted claude.ai Routine authenticated over OAuth, called `list_ready_work` and `describe_work`, and opened bayleafwalker/vuoro#124 with verdict yes. The trace is in the gateway's gen-44 `mcp_exchange` logs.
- **Why the 2026-09-25 verdict was no.** vuoro-mcp-edge answered with per-method `resultType` values (`tools-list-result`) and `cacheScope: "none"`. Claude Code enforces MCP 2026-07-28 strictly and dropped every tool. claude.ai chat is lenient, which hid the bug. Fixed in vuoro#123 (vuoro-service 0.1.74).
- **What is live.** vuoro.cloud runs v0.1.0-poc.44 (image `5a7396d2`). The pilot workspace kotona runs vuoro-service 0.1.74.

## Decisions (operator, 2026-09-26)

These follow from the architecture and are fixed for the work below.

1. **Routine reports go to `bayleafwalker/vuoro`,** which is GitHub-authoritative. vuoro-cloud is Forgejo-authoritative, and its GitHub copy is a mirror.
2. **Cloud sessions and Routines may push to unprotected branches and open PRs only.** No merge, release, environment or admin authority.
3. **E2 records runs and evidence first.** `claim_work` then becomes an exclusive, owner-backed lease. An advisory `reserve_work` stays a separately named operation.
4. **Routines hold no CLI credentials.** The one exception is a 5–15 minute read-only PAT in an attended diagnostic session.
5. **E1 stays single-repository.** Exact-subset repository grants come after E2 run handles and audit are proven. Write authority is never inferred from workspace membership.
6. **Agents may change values inside SOPS-encrypted files as normal work** (`sops set` / `sops edit` on a value). SOPS configuration and keys (`.sops.yaml`, age keys) stay operator-only. YubiKey promotion signing stays with the operator.
7. **Trusted-service boundary.** Taken from the operator's proposal, with details from the design memo.
   - An in-cluster effects service is the only holder of provider credentials, and it reaches providers only through an allowlisting egress proxy.
   - Cloud agents ask it for effects over MCP and never receive credentials.
   - The design's open questions are resolved as follows. Effects serve operator workspaces only. Merges approved through `request_merge` are executed by the operator locally, using a pre-checked `credctl merge` command. Slice 1 uses a static, comment-only bot token rotated every 30 days.
   - **Superseded in part (operator, 2026-09-26, after the review): TS-16 is not amended.** The review rejected the design (1 critical, 8 high, 4 medium). C1: an `effect.propose` that performs the effect in the same call is apply authority, which TS-16 forbids. What holds instead is below, under "Effects: queued intents and acceptance". Slice 1 does not start until every item under "Required before slice 1" is closed.

## Effects: queued intents and acceptance (operator, 2026-09-26)

TS-16 stays as written. A cloud caller never applies an effect; it queues one.

- **Propose queues.** `propose_effect` records a run-bound intent in state `proposed` and returns. Nothing is carried out during the call.
- **Acceptance happens on the trusted side.** Only a separately authenticated trusted-side actor moves an intent from `proposed` to `accepted`. The proposing caller never does, and no cloud-reachable tool or MCP surface can. By default the operator accepts in an interactive session (credctl side). The trusted-side consumer carries out accepted intents later.
- **Auto-accept is opt-in.** A profile or config switch, scoped to a workspace and/or repository and optionally to an effect kind, lets the trusted-side consumer accept queued intents without the operator. It stays within TS-16 only while all of the following hold:
  - it is off by default;
  - it is set only from the trusted side (operator config or credctl), never through a cloud-callable tool;
  - the trusted-side consumer evaluates it asynchronously, and the edge never does;
  - every auto-acceptance records the policy (id, version, scope) as the acceptor in the audit and evidence trail, so the decision can be reconstructed.
- **First proof** is the review's simpler conforming alternative: a queued `propose_effect` after E2, carried out on the operator side through credctl.

## Required before slice 1

From the Codex adversarial review of the trusted-service design (2026-09-26). Item 1 is closed by the decision above.

1. ~~Record the operator decision: retain TS-16's queued-intent boundary or explicitly amend it.~~ Retained, 2026-09-26.
2. Land E2's server-minted run identity and append-only evidence first.
3. Bind effects grants to exact repository subsets; stay canary-only until then.
4. Choose the authoritative lifecycle owner from day one; no temporary Vuoro execution state machine.
5. Freeze a multi-resource authorization spec (client, resource, scope, principal and role policy, with `g.resource` rechecks).
6. Replace bearer forwarding with a one-use, body-bound internal proof.
7. Close the cred-broker prerequisites: workload auth, comment capability, service release and live isolation.
8. Specify crash-safe, concurrent idempotency, and make the provider marker recoverable without the ledger.
9. Remove recursive DNS from the executor, and close the CONNECT/SNI, metadata, API, node-local and IPv6 test gaps.
10. Define insert-only, tamper-evident audit storage and strict non-secret output schemas.
11. Pin and verify the proxy and executor image supply chain.
12. Scope slice 1 explicitly to k3s. Talos claims no conformance until its CNI and workload composition are fixed.

## Waves

### Wave A: in flight (runtime quality; generation 45)

| Item | Where | How |
|---|---|---|
| vuoro-client sends Authorization on handshake and catalog, plus a named User-Agent | bayleafwalker/vuoro | cloud worker (Routine, run once) → PR |
| Internal MCP server (vuoro-worker) conforms to 2026-07-28 `resultType` / `cacheScope` | bayleafwalker/vuoro | cloud worker → PR |
| mcp-edge `describe_work` not-found becomes a tool error, not "work source failed" | bayleafwalker/vuoro | cloud worker → PR |
| Release vuoro-client 0.1.1 and vuoro-service 0.1.75; bump sprintctl's vuoro-client pin | vuoro, sprintctl | local, after the worker PRs merge |
| IMPLEMENTATION-STATUS for gen 44, GETTING-STARTED step 4 (connect Claude) | vuoro-cloud (Forgejo) | local (cloud sessions cannot reach Forgejo) |
| Runtime pin 0.1.75, then generation 45 | vuoro-cloud | local; operator signs |

Acceptance for the wave:
- served sprintctl reaches vuoro.cloud with a workspace token;
- `claude mcp list` stays ✔;
- kotona runs 0.1.75.

### Wave B: next (cloud lane and E2 contract)

- **Cloud build lane.** A pinned setup script and least-egress environment for credential-free tests and builds of vuoro and agentops. Cloud workers use it by default.
- **E2 (agentops#2466), contract first:**
  - server-minted `register_run` bound to OAuth subject, client, grant, workspace and one repository;
  - idempotent, append-only evidence and session-note recording;
  - the mutation freeze covers the new tools;
  - no effect scope and no broad `work:write`.
- **Close the existing gap in control's egress.** Control may reach any host on 443 today (vuoro-cloud `platform/policies/network-policies.yaml:66-72`).

### Wave C: trusted-service boundary (after "Required before slice 1")

- **Slice 1: `forge_comment_pr`,** end to end. Acceptance is in the design memo, §7.
- **Egress enforcement.** k3s's bundled kube-router enforces only standard NetworkPolicy, so the host allowlist lives in the proxy.
- **Before any Talos cutover,** the Talos environment needs a CNI that enforces policy. As configured, `platform/policies` would not be enforced there.

## Operator actions

The session keeps a joint list: command, checked precondition, expected result, and what to send back. It moves into the next handoff.
