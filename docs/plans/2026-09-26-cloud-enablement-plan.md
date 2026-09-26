# Cloud enablement plan after E1 (2026-09-26)

Status: adopted by the operator 2026-09-26 (session d5ca23ce), except where a
line says it waits on review.
Inputs:
- [options memo](2026-09-26-cloud-environments-options-memo.md), Codex gpt-5.6-sol, read-only;
- [trusted-service boundary design](2026-09-26-trusted-service-boundary-design.md), Claude, read-only. Codex's adversarial review of it is still pending.

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
   - The design's open questions are resolved as follows. Effects serve operator workspaces only. Merges approved through `request_merge` are executed by the operator locally, using a pre-checked `credctl merge` command. Slice 1 uses a static, comment-only bot token rotated every 30 days. TS-16 is amended to allow reversible, non-authoritative effects.
   - These are adopted, but slice 1 starts only after the Codex review returns and any critical or high findings are resolved. A decision-log entry (D-048) and the TS-1/TS-16 amendments follow with slice 1.

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

### Wave C: trusted-service boundary (after the review)

- **Slice 1: `forge_comment_pr`,** end to end. Acceptance is in the design memo, §7.
- **Egress enforcement.** k3s's bundled kube-router enforces only standard NetworkPolicy, so the host allowlist lives in the proxy.
- **Before any Talos cutover,** the Talos environment needs a CNI that enforces policy. As configured, `platform/policies` would not be enforced there.

## Operator actions

The session keeps a joint list: command, checked precondition, expected result, and what to send back. It moves into the next handoff.
