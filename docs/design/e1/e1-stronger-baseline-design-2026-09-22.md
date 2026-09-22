# E1 durable MCP capability: adversarial review and stronger baseline

Date: 2026-09-22. Author: session dev-5f, on request of the operator, for
session dev-38 (owner of the E1 rebuild). Reviewed against the live trees, not
the predecessor's claims. Everything cited was read this session.

Sources read: `vuoro-cloud/src/vuoro_cloud/{gateway,auth,security,control,config}.py`,
`vuoro-cloud/migrations/*.sql`, `vuoro-cloud/platform/cloudflared/deployment.yaml`,
`vuoro-cloud/IMPLEMENTATION-STATUS.md`, `vuoro-cloud/scripts/promote-release.sh`,
`vuoro-cloud/03-TENANCY-IDENTITY-AND-AUTHORIZATION.md`, the handoff
`agentops/docs/dispatch/handoffs/2026-09-22-e1-durable-edge-capability.v2.json`,
the three `_artifacts/vuoro/e1-*-2026-09-22.md` notes,
`vuoro/docs/plans/2026-09-20-vuoro-at-the-edge.md`,
`vuoro/docs/architecture/packaging.md`, and
`_wt/e1-edge/packages/vuoro-mcp-edge/src/vuoro_mcp_edge/work_source.py`.

Operator-closed decisions (handoff `decisions`/`rejected`) are honoured
throughout. Nothing below reopens placement, static bearer, effect-apply,
vendor tunnels, origin attribution, injection filters, or vendoring.

## 1. Corrections to the brief (verified against code)

1. **There is no unbounded rate-limit bucket.** `gateway.py:214-244` keys a
   per-minute counter on `(scope, subject_hash, bucket_at)` and returns 429
   above the scope maximum (`admission` 30/min, `connector` and `public-api`
   1200/min). The real defect is different and worse: every request, including
   every rejected pre-auth request, performs an `INSERT ... ON CONFLICT DO
   UPDATE` on the control database, and old buckets are pruned only at process
   start (`gateway.py:112-114`). An unauthenticated flood is therefore a write
   amplifier against the control DB. Fix the actual defect (section 4.6), not
   the reported one.
2. **Identity forwarding already exists and is the right primitive.** The
   gateway mints a 30-second EdDSA JWT (`security.py:44-94`, `kid
   gateway-2026-01`, `aud` = `cfg.gateway_audience` = `"vuoro-service"`,
   `config.py:22,30`) and sends it as `X-Vuoro-Identity`. The MCP route must
   reuse this, not add a second internal identity channel.
3. **The gateway audience is `vuoro-service`, not `vuoro-control`.** The
   handoff's "audience vuoro-control" is wrong. Fix the handoff text before it
   propagates into config.
4. **No design document contains an OAuth 2.1 design.** The security note,
   placement brief and synthesis are all built on the static bearer. Only the
   edge plan (`2026-09-20-vuoro-at-the-edge.md:128-136`) lists spec
   obligations, and it still recommends the static bearer at :124 and :259.
   The handoff states requirements, not a design. Section 4 supplies one.
5. **The documents disagree on client registration.** The edge plan says DCR is
   deprecated and CIMD preferred (:133); the handoff lists dynamic registration
   as a supported connector path (:40). Resolved in 4.3.
6. **The "public-work view" cannot be a DB view in vuoro-cloud.** vuoro-cloud's
   eleven migrations hold only control-plane tables; no work-item table and no
   `CREATE VIEW` exists. Work items live in the per-tenant runtime, whose
   schema is owned by sprintctl. A DB view in vuoro-cloud has nothing to view.
   Resolved in 4.4.
7. **The 92afde2 reduction is correct.** Four tests glob `apps/mcp` and
   `platform/mcp-trial`, and the `"mcp": MCP_IMAGE` entry pre-authorises an
   image class the durable design removes. Land only the
   `OWNED_IMAGE_PATTERNS` key fix plus a test that fails on a wrong digest for
   all four workloads (`migrate`, `controller`, `web`, gateway).

## 2. The three questions you asked me to attack

### 2.1 Resource server on the gateway vs a separate authorization server

**Both, and the split already exists in the code.** The MCP specification
(2025-06-18 authorization) makes the MCP server an OAuth resource server and
allows the authorization server to be separate. The estate already has that
separation: the gateway is a thin proxy doing edge auth (`gateway.py`), and the
control service owns identity, GitHub sign-in, PKCE transactions, browser
sessions, memberships and token tables (`control.py:260-371`, `oauth.py`,
migrations 001/002/010). So:

- **Authorization server = the control service**, at `https://vuoro.cloud`.
  It already has the consent-capable browser session, the PKCE transaction
  table, JWT signing, and the membership/workspace model the scopes must bind
  to. Building it here is the smallest greenfield: three endpoints, one
  metadata document, one consent page, one token table.
- **Resource server = the gateway**, at `https://api.vuoro.cloud/mcp`. It
  validates the access token locally with the AS public key, mints the
  existing `X-Vuoro-Identity` assertion, and proxies. It never sees a
  password, a GitHub token or a refresh token.
- **Rejected: a third-party AS** (Auth0, Keycloak, Cloudflare Access). It adds
  an external dependency, a user directory to reconcile with `memberships`, and
  a scope-to-workspace mapping the estate would have to re-derive on every
  call. The membership table is the authority; the AS must sit on it.
- **Rejected: AS inside the gateway.** The gateway is deliberately stateless
  and strips headers; putting consent UI and refresh-token storage in it
  reverses the boundary the estate was built on.

### 2.2 Public-work view in the DB or in the application

**In the application contract, at the data owner, with an optional DB view as
the implementation detail.** Reasons:

- The data is in the tenant runtime, not in vuoro-cloud (finding 1.6). The
  only repo that can define the projection is sprintctl (schema owner) with
  the response schema published through `vuoro-adapter-kit`, whose strict
  Draft 2020-12 object schemas with `additionalProperties: false` are the one
  field-level enforcement mechanism the substrate already has and already
  tests (`packaging.md`, shared contract wheels).
- A DB view alone does not stop a handler from joining extra columns, and a
  view is invisible to the served-conformance gate. A versioned operation
  whose response schema enumerates the approved fields fails the release gate
  when someone adds a field. That is a guard that can be forced to fail.
- Versioning falls out for free: `work.public.list/v1`, `work.public.item/v1`
  are catalog operations with the same version discipline as every other
  operation. The DB view, if sprintctl chooses one, is a private
  implementation choice behind the operation.

Consequence for the MCP server: it calls only `work.public.*` operations. It
never calls `work.read.*`, so the emission narrowing in `work_source.py`
(`SUMMARY_EMITTED_KEYS`, `DETAIL_EMITTED_KEYS`, the caps) moves into the
sprintctl handler and the adapter-kit schema, and the MCP server becomes a
pass-through with no disclosure logic of its own. Two copies of a disclosure
filter is one too many.

### 2.3 Exposing ahead of vuoro-cloud's own acceptance gates

**Partly defensible, and the design itself decides which gates.** The estate
is already live exposure (`IMPLEMENTATION-STATUS.md:555-558` says to treat it
so). Adding a read-only route to an already-public gateway does not change
the exposure class. What changes the risk class is the operator decision that
vuoro.cloud becomes **authoritative for real new work**. That decision, not the
MCP route, is what makes two of the five open gates mandatory:

- **Tenant isolation proof** becomes the entry gate for the MCP route. A token
  bound to workspace A must be proven unable to list or describe workspace B's
  items, and the test must first be shown to fail with the check removed.
  Read-only does not weaken this: disclosure is the whole threat.
- **Restore drill** becomes the entry gate for making the pilot workspace
  authoritative. Real work with no proven restore is data loss waiting for a
  disk. Until the drill passes, the pilot slice may exist but the homelab
  keeps authority (no dual-writing: the cloud slice is simply empty of real
  items until then).

The other three (external onboarding, home-unavailable Forgejo recovery,
synthetic canary) do not gate a read-only, single-operator, one-workspace
surface. Record that reasoning in the tracker item so the gates are not
silently bypassed or silently blocking. Add the MCP route to the synthetic
canary when the canary exists.

## 3. Structural change: where the MCP protocol server runs

The brief leaves this undecided while three constraints pin it down:
MCP is a route on the existing gateway; vuoro's MCP code must not be vendored
into vuoro-cloud; the surface must not be mounted into
`vuoro_service.app.create_app`.

**Baseline:** the MCP protocol server (JSON-RPC, `tools/list`, `tools/call`,
Streamable HTTP) is a second console entrypoint in the existing
`vuoro-service` wheel and image, `vuoro-service mcp-serve --port 8081`,
run as a second container in the existing tenant runtime pod. Gateway route
`/mcp` proxies to `http://{runtime_service}.{suffix}:8081/mcp` with the same
`X-Vuoro-Identity` assertion the catch-all already mints (`gateway.py:750`).

Why this and not the alternatives:

- It is the same image and the same pod, so it satisfies "no separate
  namespace, tunnel, stack or image" and "hosting vuoro's image unchanged".
- It does not touch `create_app`; it is its own ASGI app with a different
  auth model (assertion only) and a different wire protocol, which is exactly
  what that docstring demands.
- The MCP process holds **no `vuo_pat_` token** and no DSN. The synthesis
  design (`security.py:13` of vuoro-mcp-edge) put a workspace PAT inside the
  MCP process; that is a standing credential in the most exposed component
  and must not survive. The MCP process trusts only the assertion it
  receives, validated against the gateway's public key, and calls the
  `work.public.*` operations on localhost with that assertion forwarded.
- `vuoro-mcp-edge` as a separate package can be kept as the source of the
  protocol code, but it is installed into the vuoro-service image as a pinned
  wheel through the existing composition manifest and attestation path
  (`Dockerfile`, `adapter-pins.json`), not built as its own image.

## 4. OAuth 2.1 baseline

### 4.1 Discovery and challenge

- `GET https://api.vuoro.cloud/.well-known/oauth-protected-resource/mcp`
  (RFC 9728): `resource = "https://api.vuoro.cloud/mcp"`,
  `authorization_servers = ["https://vuoro.cloud"]`,
  `scopes_supported = ["vuoro:work.read"]`, `bearer_methods_supported =
  ["header"]`. Served by the gateway, registered **before** the `/api/{path}`
  catch-all.
- Unauthenticated `/mcp` returns 401 with `WWW-Authenticate: Bearer
  resource_metadata="...", scope="vuoro:work.read"`. Insufficient scope
  returns 403 `insufficient_scope` (step-up path for later scopes).
- `GET https://vuoro.cloud/.well-known/oauth-authorization-server` (RFC 8414)
  from the control service: `issuer`, `authorization_endpoint`,
  `token_endpoint`, `jwks_uri`, `registration_endpoint`,
  `code_challenge_methods_supported = ["S256"]`,
  `grant_types_supported = ["authorization_code","refresh_token"]`,
  `token_endpoint_auth_methods_supported = ["none"]`,
  `scopes_supported`, `resource_indicators_supported = true`.
- The existing custom `/.well-known/vuoro` document is untouched.

### 4.2 Endpoints on the control service

- `GET /oauth/authorize`: requires PKCE S256 and `resource` (RFC 8707); rejects
  anything else. Reuses the browser session; if absent, runs the existing
  GitHub sign-in (`control.py:260-371`) and returns. Consent page shows client
  name, requested scopes, and a **workspace picker** limited to the user's
  active memberships. One grant binds exactly one workspace. Stores a
  transaction row in `oauth_transactions` (already exists, migration 002/010)
  with client_id, code_challenge, resource, scopes, workspace_id, user id.
- `POST /oauth/token`: `authorization_code` with `code_verifier`, and
  `refresh_token`. Public client, no client secret. Refresh tokens rotate on
  every use; reuse of a rotated refresh token revokes the whole grant
  (RFC 9700 guidance).
- `POST /oauth/register` (RFC 7591 DCR) with policy: only public clients,
  `token_endpoint_auth_method = none`, redirect URIs must be `https` and match
  an allowlist of connector callback hosts stored in config, no wildcard.
  Registrations expire if unused for 90 days.
- `GET /oauth/jwks`: the AS signing public key(s), with `kid`.

### 4.3 Client registration decision

Support **DCR with the allowlist policy above** as the primary path, plus
**pre-registered client IDs** entered by the operator. Do not build CIMD now:
the claude.ai connector's support for it is unverified and the edge plan's
"DCR is deprecated" refers to a draft direction, not a shipped client
behaviour. Add CIMD later if a client needs it; nothing in this design
prevents it. Verification step before coding: read the current claude.ai
connector documentation and record which of the three paths it actually
performs, in the tracker item.

### 4.4 Tokens

- **Access token**: EdDSA JWT, separate keypair from the gateway assertion
  key (`kid as-2026-09`), `iss = https://vuoro.cloud`,
  `aud = https://api.vuoro.cloud/mcp`, `sub` = user id, `client_id`,
  `workspace_id`, `scope`, `principal_epoch`, `exp` = 15 minutes.
  The existing `principal_epoch` mechanism (already in the gateway assertion)
  is the revocation lever: membership removal or workspace suspension bumps
  the epoch, and the gateway rejects any token whose epoch is stale, exactly
  as `auth.py:60-69` already re-checks membership per request for PATs.
- **Refresh token**: opaque, `vuo_rt_<id>_<secret>`, stored as a keyed hash in
  a new `oauth_grants` table (`grant_id, user_id, client_id, workspace_id,
  scopes, refresh_hash, refresh_rotated_at, expires_at, revoked_at`),
  following the `api_tokens` hashing pattern (`security.py:22-32`). Absolute
  lifetime 30 days, sliding inactivity 7 days. Listed and revocable at
  `GET/DELETE /api/control/v1/workspaces/{id}/grants`, next to the existing
  token inventory endpoints.
- **Scopes**: `vuoro:work.read` only at launch. `vuoro:work.claim`,
  `vuoro:evidence.record`, `vuoro:effect.propose` are reserved names for the
  coordinate/record/propose classes. `vuoro:effect.apply` is listed in the
  code as a **rejected scope constant** with a test asserting the AS refuses
  it, so the absence is enforced, not remembered.

### 4.5 Resource-server check at the gateway `/mcp` route

In order, each with a forced-failure test:

1. Bearer present and parses as JWT; else 401 with resource metadata.
2. Signature valid against the AS JWKS (cached, refreshed on unknown `kid`).
3. `iss`, `aud` exact match; a token with `aud = vuoro-service` or any other
   value is rejected. A `vuo_pat_` on `/mcp` is rejected. An OAuth JWT on
   `/api/{path}` is rejected (it fails `TOKEN_RE`; keep a test proving it).
4. `exp`/`nbf` with 30 seconds skew.
5. `principal_epoch` matches the current epoch for `(sub, workspace_id)`; one
   DB read, same query as the PAT path.
6. Scope covers the MCP method being called (`tools/call` on a read tool
   needs `vuoro:work.read`; `tools/list` and `initialize` need only a valid
   token).
7. Mint `X-Vuoro-Identity` with `actor = sub`, `workspace_id`,
   `authorities` = intersection of membership authorities and token scopes,
   `repo_ids` from membership. Proxy to the runtime pod port 8081.

### 4.6 Rate limiting

- **Pre-auth**: in-memory token bucket per gateway replica keyed on the
  Cloudflare connecting IP, no database write for a rejected request. Two
  replicas means twice the nominal limit; accept that and document it.
- **Post-auth**: keep the DB bucket, but key `scope = "mcp"` on
  `(sub, workspace_id)` rather than IP, so one principal cannot exhaust
  another's budget behind a shared egress.
- Move bucket pruning from process start to a periodic task, or add a
  partial index and prune from the tenant controller's outbox loop.

### 4.7 Transport

Streamable HTTP, POST for requests, optional SSE for server-to-client
streaming. Verify before promotion that a streamed response survives the
Cloudflare tunnel for at least the MCP client's timeout; if it does not,
serve JSON-only responses (the read tools do not need streaming). Sessions
(`Mcp-Session-Id`) are stateless in the MCP server; do not add session
storage.

## 5. Public-work contract (sprintctl-owned)

- Operations: `work.public.list/v1` and `work.public.item/v1`, registered
  through `vuoro-adapter-kit` with strict response schemas.
- Approved fields, list: `work_id`, `title`, `priority` (nullable). Item:
  `work_id`, `title`, `objective`, `acceptance`. Caps as already measured in
  the synthesis (title 160, objective 500, acceptance 5 by 200). Nothing
  else, `additionalProperties: false`. `description`, `repo_id`,
  `provenance`, `tier`, `prior_attempts` are named in the schema test as
  fields that must be absent.
- Workspace scoping is by the identity assertion, as with every other
  operation; the handler takes workspace from the resolver, never from the
  request body.
- Confirm the operation names live with `GET /api/catalog/v1` on the pilot
  runtime before the MCP server's constants are frozen. This is the cheapest
  item in the plan and kills the "inferred" caveat.
- MCP tools: `list_ready_work` maps to `work.public.list/v1`, `describe_work`
  to `work.public.item/v1`. Both classified `read`.

## 6. Pilot workspace and identifiers

- Create a **new** workspace on vuoro.cloud for the pilot with a new
  sprintctl runtime; do not import homelab history. Work items are created
  fresh there, so IDs cannot collide with homelab IDs by construction.
- The only cross-estate reference is a free-text `origin` note on a homelab
  item pointing at a cloud `work_id`, never the reverse and never shared IDs.
  When record import is later demonstrated, imports receive new IDs with a
  provenance link.
- Authorship policy on the pilot workspace: only operator principals may
  create or edit items. This is the strongest injection control available and
  is enforced by membership authorities, not by content filtering.
- Recommended defaults so this does not wait on anyone: workspace slug
  `kotona-pilot`, repo_id `vuoro`. The operator can rename before the first
  item is created; nothing depends on the names.

## 7. Tracker

Supersede agentops#2465 with a new item scoped to the durable capability,
closing #2465 with a pointer. Three of four acceptance lines are dead, so
revising in place would leave a history that reads as if the trial happened.
The new item's acceptance is the gate list in section 9.

## 8. Build order (critical path first)

1. Land the reduced 92afde2 (durable validator fix only, forced-failure test).
2. sprintctl: `work.public.*` operations and schemas; confirm catalog names
   live. Release the adapter wheel through the existing pinned-release path.
3. vuoro-service: `mcp-serve` entrypoint consuming `vuoro-mcp-edge` as a
   pinned wheel; assertion-only auth; calls `work.public.*` on localhost.
4. vuoro-cloud control: AS endpoints, `oauth_grants` migration, consent page
   with workspace picker, JWKS, RFC 8414 metadata, DCR with allowlist.
   (Parallel with 2 and 3; largest item.)
5. vuoro-cloud gateway: `/mcp` route and RFC 9728 metadata, resource-server
   checks, pre-auth in-memory limiter, post-auth principal bucket.
6. Tenant isolation proof and restore drill (section 2.3), each forced to
   fail first.
7. Register the connector against a pre-registered client, then via DCR;
   both must work.
8. Promote via `scripts/promote-release.sh` (hardware key, two touches).

## 9. Gates that must be forced into their failure case

Each gate is a test that is first made to fail by breaking the code it covers,
with the failure captured, then reverted.

- Wrong `aud` token rejected at `/mcp`.
- PAT rejected at `/mcp`; OAuth JWT rejected at `/api/{path}`.
- Expired access token rejected; stale `principal_epoch` rejected within one
  request of membership removal.
- Rotated refresh token reuse revokes the grant.
- `vuoro:effect.apply` refused by the AS.
- Workspace A token cannot list or describe workspace B items (tenant
  isolation).
- `work.public.item/v1` response containing `description` fails the schema
  gate.
- Redirect URI outside the allowlist refused by DCR.
- Pre-auth flood produces zero control-DB writes.
- Digest-pin validator fails on a wrong digest for each of the four workloads.
- Restore drill restores the pilot workspace's runtime database and the
  restored `work.public.list/v1` returns the pre-drill items.

## 10. What I did not verify

- Whether a Cloudflare Access policy exists outside the repo for
  `api.vuoro.cloud` (dashboard or separate Terraform state).
- The claude.ai connector's current registration behaviour (DCR vs manual vs
  CIMD).
- SSE survival through the tunnel.
- The `work.read.*` operation names on a live catalog.

## 11. Product-level review (added after reading the positioning and direction records)

Sources: `vuoro-cloud/00-EXECUTIVE-DECISION.md`, `19-PRODUCT-POSITIONING-AND-PROOF.md`,
`01-SCOPE-AND-SUCCESS-CRITERIA.md`, `agentops/docs/plans/2026-09-17-target-state.md`
(TS-1, TS-6, TS-16 and the tripwires), `vuoro/docs/plans/2026-09-20-vuoro-at-the-edge.md` §1-2,
`vuoro/docs/notes/2026-09-19-the-substrate-grows-a-public-face.md`.

### 11.1 What the product actually is, and what E1 is for

The product promise is "keep long-running agent work resumable and know which
result actually counts"; the category is an operational state and settlement
layer; the boundary is "coordinate the work, keep control of where it runs".
vuoro.cloud was reframed on 2026-09-19/20 (edge doc §1, TS-16): it is not a
hosted product looking for users, it is the substrate's network-reachable
edge, justified because runtimes the operator does not host (claude.ai,
Cowork, Routines, cloud sessions) currently produce no claim, no run record
and no evidence. The control question is the proportion of automated
activity that is reconstructable; for hosted runtimes it is zero.

Measured against that, a read-only E1 closes none of the hole. Listing and
describing ready work from claude.ai creates no record. E1's durable value is
entirely in what it lays down for E2-E4: the route, the authorization model,
the workspace binding and the disclosure contract. The two read tools are a
smoke test of that foundation, not the deliverable. The design must be judged
by whether E2-E4 can be added without redoing anything, which is why sections
3-5 keep scopes, the route and the projection generic.

### 11.2 Changes to the baseline that follow from the product intention

1. **Make E2 a tool addition and nothing else.** (Revised 2026-09-22 after
   dev-38's objection; the earlier text pulled `write_session_note` into
   E1, which moved a tool between two operator-authorized items that sprint
   559 event #3328 sequenced in dependency order, and contradicted point 4,
   since a runtime-authored note is a real record in a workspace that must
   hold none before the restore drill passes. The tool stays in E2, #2466.)
   What survives is a constraint on E1's authorization model: the AS scope
   registry carries `vuoro:evidence.record` and `vuoro:work.claim` as
   known-but-not-granted at launch and refuses them for every client until
   E2 flips the grant; the `/mcp` scope check is table-driven so a new tool
   is one row; the assertion minting intersects membership authorities with
   token scopes from day one, so a write scope later needs no gateway
   change. The S14 concern (reach provable only from gateway logs) is
   answered by acceptance instead: #2514 closes on a first-use trace that
   ends in a PR in an operator repo carrying the runtime's verdict.
2. **The projection must expose freshness and unavailability, not just
   fields.** The positioning doc's authority model requires a composed view
   to expose field authority, freshness, and unknown/unavailable/stale
   state, and must not imply certainty while an authority is unavailable.
   An empty list on a runtime outage is a silent hole, the exact failure the
   "demand is an invocation, not a success" decision guards against. So
   `work.public.list/v1` returns an envelope: `authority: "sprintctl"`,
   `as_of` (server time of the read), `state: ok|unavailable`, and `items`.
   The MCP server surfaces `unavailable` as a tool error, never as `[]`.
3. **Pre-registered client first, DCR only if the connector cannot do it.**
   Under the reframe the only client is the operator's own connector
   registration, which the edge doc §2 says supports "own client". An
   unauthenticated public `/oauth/register` endpoint serves no product need
   and adds attack surface to an estate whose maturity label is at best
   "Internal operational proof". Reverse of section 4.3: build
   pre-registered clients, verify the connector dialog accepts them, and add
   DCR only on a demonstrated need. The RFC 8414 metadata simply omits
   `registration_endpoint` until then.
4. **The restore drill is the product promise, not a release formality.**
   "Know which result counts" and "resumable" are void for a record that
   can be lost. Making the pilot workspace authoritative for real work
   before a proven single-workspace restore contradicts the core claim.
   Section 2.3 stands and is now grounded in the product, not in
   vuoro-cloud's checklist. Tenant isolation stays as the route gate because
   the estate is multi-workspace-shaped and public whatever the current user
   count.
5. **Define first use, not first deployment.** "Design for use" means the
   release is done when a hosted runtime has used it and its output crossed
   back inside the perimeter. agentops#2471 already fixed the shape: a
   Routine whose output is a judgement ends by opening a PR. Acceptance line:
   a claude.ai Routine authenticates via OAuth, calls `list_ready_work` and
   `describe_work`, and opens a PR in an operator repo carrying its verdict.
   That one run proves auth, read and the boundary in a single trace; record
   joins the trace at E2.
6. **Maturity label.** Every Vuoro-owned option must carry one. E1 ships as
   "Internal operational proof". No onboarding, invitation, or self-serve
   affordance is built for it, and the connector is registered by the
   operator only.

### 11.3 Drift to record so two framings do not coexist

- `agentops/docs/plans/2026-09-17-target-state.md` tripwire "A month of E1
  without the substrate being reached... the read surface is deleted" is
  superseded by the operator's 2026-09-22 direction (stop condition demoted
  to a post-launch prioritisation review). Update the tripwire in the same
  change that supersedes #2465, or the target state will re-derive the trial
  design.
- `vuoro-cloud/IMPLEMENTATION-STATUS.md` and `01-SCOPE` still frame the
  open acceptance gates around external-user onboarding. The reframe makes
  external onboarding a non-goal for now. Record in
  `vuoro-cloud/17-DECISION-LOG.md` that the estate's near-term purpose is
  the operator's own hosted runtimes, that isolation and restore remain
  binding, and that onboarding, Forgejo recovery and canary are re-sequenced
  behind E2. Do not delete those gates; re-sequence them explicitly.
- The edge doc still recommends a static bearer at §4 and in its decided
  item. Annotate it as superseded by the 2026-09-22 OAuth direction rather
  than editing history.

### 11.4 What the product intention does not change

Placement on vuoro.cloud, no effect-apply scope, no vendoring, sprintctl
owning the projection (it owns readiness and visible work in the authority
table), and the MCP server living in the vuoro-service composition (Vuoro
owns composition and correlation; Cloud only operates it) are all
consistent with TS-1 and the authority model. Nothing in sections 2-10 is
withdrawn except 4.3 as amended above.

## 12. Reply to dev-38's challenge (Authentik, streaming, corrections)

### 12.1 Facts settled this session

- **claude.ai redirect URI**: `https://claude.ai/api/mcp/auth_callback`, with
  Anthropic's connector docs asking servers to also allowlist
  `https://claude.com/api/mcp/auth_callback` for a future move; Claude Code
  uses loopback redirects. Pre-registered client ID and secret are entered
  under "Advanced settings" in the connector dialog (Anthropic support article
  11175166 and claude.com/docs/connectors/building/authentication).
- **Authentik and RFC 8707**: the OAuth2 provider documentation never
  mentions the `resource` parameter or RFC 8707; the token audience comes
  from provider configuration, so audience binding to a per-request resource
  is not available. Authentik does support DCR (scope
  `goauthentik.io/oidc/dcr`), contrary to the brief, but that does not
  change the decision.
- **Gateway buffering confirmed**: `gateway.py:346-348` reads the whole
  request body and wraps `upstream.content` in a plain `Response`. There is
  no streaming path. CORS is pinned to `cfg.public_web_url`
  (`gateway.py:134-135`).
- **Audiences**: three exist, none a typo. `vuoro-control` is the browser
  session cookie audience (`control.py:217,1144`), `vuoro-admission` is the
  10-minute invitation-redeem audience (`control.py:347`), `vuoro-service`
  is the gateway-to-runtime assertion audience (`config.py:22`). Finding 1.3
  is withdrawn as stated; the handoff was right about the cookie audience
  and only omitted that it is a cookie, not a delegable grant.
- **`mcp_surface.py` is on `vuoro` main** (PR #112, commit 672fecc). The
  unmerged parts are the payload narrowing and the edge adapter. Nothing in
  this document should be read as "the surface does not exist".
- **Operation names are asserted statically in sprintctl**
  (`cli_runtime.py:289,297`, `served_routes.py:91`). The remaining unknown is
  the result field names, so build-order step 2 narrows to: confirm the
  `items`/`item` result keys and field names against one served response.

### 12.2 Decision: the authorization server stays in the control service

Authentik at `auth.kotona.app` is proof that publishing an OAuth provider to
an AI vendor works and that its failure modes are known (strict redirect
matching, refresh dead-letter without `offline_access`, hourly re-auth
colliding with Cloudflare Access OTP). Reuse those lessons. Do not reuse the
server, for four reasons that each suffice:

1. **It re-enters the homelab into the public path.** The placement decision
   put the surface on vuoro.cloud because the homelab co-hosts the IdP, the
   forge and the password manager. Routing every E1 login and every hourly
   refresh through that IdP's public route is the same exposure by another
   door. The operator's reasoning applies to auth as much as to the route.
2. **Availability coupling.** Cached JWKS would keep token validation alive
   when the house is down, but `/authorize` and `/token` would not, so every
   refresh fails and the connector dies with the house. vuoro.cloud exists
   because hosted runtimes cannot reach the house; making the house a
   dependency of the only public path inverts that.
3. **Two sources of truth for identity.** Workspace binding must come from
   vuoro-cloud's `memberships`. Authentik has its own user directory; a
   property mapping from Authentik user to vuoro workspace is a second
   authority for the one fact the token must get right.
4. **No per-request audience.** Section 4 makes `aud` load-bearing. On
   Authentik the audience is static per provider, which is a recorded
   deviation for no gain.

What the Authentik blueprint changes in section 4: refresh tokens are issued
by default for the connector client (no `offline_access` scope dance), the
consent leg on vuoro.cloud has no IP allowlist and no Cloudflare Access in
front of it (verified: no Access policy in the repo; the browser leg is the
operator's ordinary GitHub sign-in), and both claude.ai callback hosts plus
Claude Code loopback are the pre-registered redirect set, strict match.

### 12.3 Streaming: do not add it to the gateway

MCP Streamable HTTP lets the server answer a POST with a plain JSON body and
return 405 to the client's GET for a server-initiated stream. The read and
record tools return immediately. So `mcp-serve` runs JSON-response mode, the
gateway's existing buffered proxy is sufficient, and the SSE-through-tunnel
question disappears. Add streaming only when a tool needs progress
notifications, and then as an explicit `StreamingResponse` path for `/mcp`
only. CORS is irrelevant for claude.ai, whose connector calls originate
server-side (edge doc §1); a browser-origin client such as the MCP inspector
is a development convenience, not a product need.

### 12.4 Smaller corrections

- The operator bearer at `control.py:171-182` is a live static bearer with a
  CIDR allowlist. The tracker item must say "no static bearer on the MCP
  surface", not "no static bearers in the estate".
- `repo_id` carrying both slugs and UUIDs is a data-hygiene defect in
  sprintctl's domain, not a blocker for the access token: the token binds
  `workspace_id` (a UUID) only, and `repo_ids` flow from membership into
  the assertion exactly as they do for PATs today. The projection filters by
  workspace through the identity resolver, never by `repo_id`. Record the
  two-namespace defect against sprintctl separately.
- The DB-view chain (sprintctl migration to schema 17 on a tenant at 7, in a
  third repo, with no read-only role) is the strongest argument for section
  2.2's answer: the projection is an operation with a strict schema, and no
  view, migration or new database role is required for E1.
