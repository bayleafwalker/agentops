# Contract addendum: vuoro.cloud multi-resource authorization

Date: 2026-09-27. Status: **addendum to cloud-enablement plan item 5** ("Freeze a multi-resource authorization spec: client, resource, scope, principal and role policy, with `g.resource` rechecks", `docs/plans/2026-09-26-cloud-enablement-plan.md`). It covers the two resources that the admin-identity design adds (`docs/plans/2026-09-27-admin-identity-and-vuoro-cli-design.md`, unit 0.1). It does not cover the effects resource; item 5 still owes that part.

Code facts are cited at vuoro-cloud Forgejo `main` `332faa4` (v0.1.0-poc.47).

## 1. Resources

| Id | Resource indicator (RFC 8707) | Served on | Grant shape | Status |
|---|---|---|---|---|
| **R-mcp** | `https://api.vuoro.cloud/mcp` (`cfg.resolved_mcp_resource`) | gateway `/mcp` → tenant runtime, through the public edge | authorization code + PKCE; grant bound to **one** workspace (`oauth_grants.workspace_id NOT NULL`, `migrations/012_oauth_authorization_server.sql:53`) | live |
| **R-control** | `https://api.vuoro.cloud/control` | control public listener (`:8080`) under `/api/control/v1/cli/*`, through the public edge | authorization code + PKCE, loopback redirect (RFC 8252); grant spans the principal's memberships (workspace chosen per request, membership checked per request) | unit 3.1 |
| **R-admin** | `https://api.vuoro.cloud/control/admin` | control **admin listener** (`:8443`) under `/api/control/v1/admin/*`, WireGuard tunnel only; the gateway refuses the prefix | WebAuthn challenge grant (no authorize redirect); refresh token rotating, 1 h absolute | unit 1.3 |

A token is valid at exactly one resource: its `aud` is the resource indicator, and every resource server verifies `aud` equality. No token, cookie or gateway assertion minted for one resource is accepted by another.

## 2. Principal kinds

| Kind | Where it lives | Subject / actor | Authenticates by | Status |
|---|---|---|---|---|
| `human` | `users` (`kind='human'`, default for existing rows from unit 2.1) | `users.id` / `github:<digits>` | GitHub OAuth (`oauth.py:94`) | live |
| `test` | `users` (`kind='test'`) | `users.id` / `test:<ulid>` | admin-minted test-login code or harness token | slice 4 |
| `agent` | `users` (`kind='agent'`) | `users.id` / `agent:<ulid>` | cred-broker RFC 8693 exchange under a delegation | slice 7 (gated) |
| `connector` | `connectors`, `principal_subjects.kind='connector'` | `connectors.id` / `connector:<id>` | connector enrolment | live |
| `admin` | `admin_principals`, `principal_subjects.kind='admin'` | `admin_principals.id` / `admin:<id>` | WebAuthn (YubiKey, UV) on the admin listener | unit 1.3 |
| `service` | client registration only (no principal row) | client id `vuoro-cli-service` / `service:vuoro-cli-service` | RFC 7523 JWT-bearer from a pinned issuer | slice 6 |

Until unit 2.1 adds `users.kind`, every `users` row is treated as `human` by R-mcp and R-control; R-control additionally requires the subject to match `^github:[0-9]+$` so a pattern violator (the blocker12 owner class) cannot obtain a control token.

## 3. Scopes

| Scope | Registry | Resource | Grantable? |
|---|---|---|---|
| `vuoro:work.read` | `SCOPE_TO_AUTHORITIES` (`oauth_scopes.py:19-30`) | R-mcp | yes |
| `vuoro:evidence.record` | `SCOPE_TO_AUTHORITIES`, restricted to `claude-connector` (`:49-51`) | R-mcp | yes, `claude-connector` only today; slices 4 and 7 widen the restriction to `vuoro-test-harness` and `vuoro-agent-delegate` |
| `vuoro:work.claim` | `RESERVED_SCOPES` (`:34-37`) | R-mcp | **no — reserved** (see §5) |
| `vuoro:effect.propose` | `RESERVED_SCOPES` | R-mcp | **no — reserved** (see §5) |
| `vuoro:effect.apply` | `REJECTED_SCOPES` (`:40`) | — | **never** |
| `vuoro:control.workspace.read` | `CONTROL_SCOPES` (new) | R-control | yes, `vuoro-cli` + human only |
| `vuoro:control.workspace.write` | `CONTROL_SCOPES` | R-control | yes, `vuoro-cli` + human only |
| `vuoro:control.token.manage` | `CONTROL_SCOPES` | R-control | yes, `vuoro-cli` + human only |
| `vuoro:admin.read` | `ADMIN_SCOPES` (new) | R-admin | yes, `vuoro-cli-admin` + admin (slice 1); `vuoro-cli-service` (slice 6) |
| `vuoro:admin.audit.read` | `ADMIN_SCOPES` | R-admin | as `vuoro:admin.read` |
| `vuoro:admin.workspace.lifecycle`, `vuoro:admin.principal`, `vuoro:admin.token.mint`, `vuoro:admin.restore` | `ADMIN_SCOPES` | R-admin | `vuoro-cli-admin` + admin only; from slice 2/4/5 |
| `vuoro:admin.backup` | `ADMIN_SCOPES` | R-admin | `vuoro-cli-admin` + admin; `vuoro-cli-service` (slice 6) |

`CONTROL_SCOPES` and `ADMIN_SCOPES` never enter `SCOPE_TO_AUTHORITIES`, which is R-mcp's authority table, so no R-mcp default grant can contain them.

## 4. Decision matrix

Rows are evaluated top to bottom; the first matching row decides. Transport rows come first, then permanent refusals, then per-resource rows with the more specific client before the general one. "Refuse" means OAuth `invalid_scope` (or `invalid_target` for a resource mismatch, `invalid_client`, `invalid_grant`, `access_denied` as named) plus an audit row; on R-admin it means HTTP 400/401/403, audited under the named event once a principal or credential is identified.

| # | Client | Resource | Requested scope | Principal kind | Decision |
|---|---|---|---|---|---|
| M1 | any | R-admin path on the public listener or through the gateway | anything | any | **Not routable** (404): no admin route exists on control's public process, and the gateway refuses `/api/control/v1/admin/*` (units 1.2, 1.3) |
| M2 | any | R-admin, TCP peer not an enrolled `/32` (the operator's; slice 6 adds the appservice peer's), or a `cf-*` header present | anything | any | **Refuse** 403 `admin-source-denied`, counted, not DB-audited (no principal yet) (unit 1.3) |
| M3 | any | any | `vuoro:effect.apply` | any | **Refuse**, audited `oauth.scope.rejected_requested` (live) |
| M4 | any | R-mcp | any `vuoro:control.*` or `vuoro:admin.*` | any | **Refuse** `invalid_scope`, audited `oauth.scope.rejected_requested` (unit 1.3) |
| M5 | any | R-mcp | `vuoro:work.claim` or `vuoro:effect.propose` | any | **Refuse** `invalid_scope` while reserved (live); for minted tokens also by name (M12, M15) |
| M6 | ≠ `vuoro-cli-admin`, ≠ `vuoro-cli-service` | R-admin | anything | any | **Refuse** `invalid_client` (unit 1.3) |
| M7 | `vuoro-cli-service` | R-admin | ⊆ {`admin.read`, `admin.audit.read`, `admin.backup`} | service (JWT-bearer, pinned issuer) | Grant, 5 min, no refresh (slice 6); anything else **Refuse** |
| M8 | `vuoro-cli-admin` | R-admin | anything | admin inactive, `adm_epoch` stale, credential disabled or unknown, assertion without UV | **Refuse** 401, audited `admin.login.refused` / `admin.token.refused` with the reason code (unit 1.3) |
| M9 | `vuoro-cli-admin` | R-admin | anything outside the shipped `ADMIN_SCOPES` | admin | **Refuse** `invalid_scope` (unit 1.3) |
| M10 | `vuoro-cli-admin` | R-admin | ⊆ shipped `ADMIN_SCOPES` (none = `vuoro:admin.read vuoro:admin.audit.read`) | admin, active, `adm_epoch` current, WebAuthn assertion with UV from an enrolled, enabled credential listed in `allowCredentials` | Grant: access 5 min, refresh rotating ≤ 1 h absolute (unit 1.3) |
| M11 | `vuoro-cli-admin` | R-admin | anything | any non-admin (no WebAuthn credential exists for it) | **Refuse** (structural) |
| M12 | `vuoro-test-harness` or `vuoro-agent-delegate` (admin mint or delegated exchange) | R-mcp | names `vuoro:work.claim` or `vuoro:effect.propose` | any | **Refuse** by name, independently of M5 (slices 4, 7) |
| M13 | `vuoro-test-harness` | R-mcp | ⊆ {`vuoro:work.read`, `vuoro:evidence.record`} | test, not expired, member of a test workspace | Grant by admin mint only, ≤ min(24 h, expiry), no refresh (slice 4); other kinds **Refuse** |
| M14 | `vuoro-agent-delegate` | R-mcp | ⊆ delegation ceiling ⊆ {`work.read`, `evidence.record`}, workspace ∈ delegation workspaces, repos ⊆ delegation repos | agent, not expired, active membership with role ≤ `member` in that workspace | Grant ≤ 15 min, no refresh, `act` claim. The exchange inserts a row **in `oauth_grants`** carrying the delegation's `repo_ids` (grant id in the token), so the gateway's per-request grant, membership, workspace and epoch check (`gateway.py:823-841`) applies; slice 7 also makes the gateway intersect the repositories it forwards (today every repository in the workspace, `gateway.py:147-148`, `:983`) with the grant's `repo_ids`. Disabling the delegation revokes that row (slice 7, gated on plan item 7) |
| M15 | `vuoro-agent-delegate` | R-mcp | anything else, including a reserved scope in the ceiling | any | **Refuse** (slice 7) |
| M16a | `vuoro-cli-admin`, `vuoro-cli-service` (and `vuoro-test-harness` requests not already decided by M12-M13) on `/oauth/authorize` or `/oauth/token` | R-mcp | anything | any | **Refuse** `unauthorized_client`: these clients never use the authorization-code path; unit 1.3 refuses them by id there, with a conformance case |
| M16b | `vuoro-cli` | R-mcp | anything | any | **Refuse** `invalid_target`: the CLI never holds work-plane tokens (unit 3.1; placed here so no later grant row can match it) |
| M16 | `claude-connector` | R-mcp | `vuoro:work.read`, `vuoro:evidence.record`, or none (default = both) | human (GitHub login), or test via a single-use test-login code (slice 4) | Grant, bound to one workspace the principal is an active member of (live for human) |
| M17 | other registered client | R-mcp | `vuoro:evidence.record` | any | **Refuse** `invalid_scope`; dropped silently from a scope-less default (live) |
| M17a | any registered client not named in M6-M17 (today none is registered besides `claude-connector`; `vuoro-cli`, `vuoro-cli-admin`, `vuoro-cli-service`, `vuoro-test-harness`, `vuoro-agent-delegate` are decided above) | R-mcp | `vuoro:work.read` or none | human, active member of the workspace | Grant, bound to that one workspace (live: `evaluate_scopes` grants it to any registered client; `grant_usable` checks membership) |
| M18 | ≠ `vuoro-cli` | R-control | anything | any | **Refuse** `invalid_target` (unit 3.1) |
| M19 | `vuoro-cli` | R-control | anything outside `CONTROL_SCOPES` | any | **Refuse** `invalid_scope` (unit 3.1) |
| M20 | `vuoro-cli` | R-control | ⊆ `CONTROL_SCOPES` | not human, or subject fails `^github:[0-9]+$` | **Refuse** `access_denied` at authorize; `invalid_grant` at refresh (unit 3.1) |
| M21 | `vuoro-cli` | R-control | ⊆ `CONTROL_SCOPES` (none = read only) | human | Grant; every request still checks `administrative_membership` for the target workspace (unit 3.1) |
| M22 | any | any | none of the above | any | **Refuse** |

## 5. Reserved authorities

- `vuoro:effect.propose` stays reserved until a durable intent store exists **and** every tenant runtime serves the propose tools.
- `vuoro:work.claim` stays reserved until an exclusive, durable lease exists **and** every tenant runtime serves the claim tools.
- No row above grants either. A reservation lifts only when the scope gains a row in `SCOPE_TO_AUTHORITIES` (`RESERVED_SCOPES` is derived from it, `oauth_scopes.py:34-37`). Delegation ceilings and admin mints refuse them by name (M12, M15), so adding that row alone still does not open them to minted tokens. Lifting a reservation is its own reviewed change and must show both conditions.
- TS-16 is unamended: a cloud caller queues effects and never applies them; acceptance is trusted-side.

## 6. Rechecks

| When | What is rechecked |
|---|---|
| R-mcp refresh (live) | the request's `resource` parameter, if given, equals the configured MCP resource (`control.py:1142`); `client_id` matches the grant (`control.py:1154`); grant not revoked, idle-expired or past absolute expiry (`:1181`); the new token is stamped with the current principal epoch (not compared; the gateway compares it per request, `gateway.py:840`); scope narrowing through `evaluate_scopes(..., client_id=...)` (`:1189`) and still grantable (`:1197`); membership and workspace still active via `grant_usable` (`:1201`, `:657-660`). **Not** rechecked today: the grant's stored `resource`; `aud` is the MCP resource constant (`mint_access_token`, `:736-755`). This is correct only while every grant is an R-mcp grant. |
| R-mcp and R-control refresh (unit 3.1 obligation) | the grant's stored `resource` (`g.resource`) equals the resource being refreshed and the client's registered resource; `aud` of the minted token is taken from `g.resource`, never a constant; an R-control grant presented at the R-mcp token path is `invalid_grant` by name, not by accident. Unit 3.1 adds conformance cases for both directions. |
| R-control refresh (unit 3.1) | client is `vuoro-cli`, principal kind human and subject pattern, principal epoch |
| R-control request (unit 3.1) | `aud`, `typ=at+jwt`, principal epoch, scope, `administrative_membership` for the target workspace; any session cookie on the request → 400 |
| R-admin refresh (unit 1.3) | token hash matches an unused member of a live family, absolute expiry, admin active, `adm_epoch`, credential not disabled; reuse revokes the family |
| R-admin request (unit 1.3) | TCP peer is an enrolled `/32` (the operator's; slice 6 adds the appservice peer's), no `cf-*` header, `aud`, `typ=at+jwt`, admin active, `adm_epoch`, scope |
| Delegated agent request (slice 7) | the gateway's grant query plus: forwarded repositories ⊆ the grant's `repo_ids`; a request naming a repository outside them is refused (403), with a slice-7 conformance case |

## 7. Conformance

Unit 1.3 adds `tests/test_scope_matrix.py` to vuoro-cloud. It encodes the rows of §4 that exist at that point (M1-M6, M8-M11, M16, M16a, M17, M17a) as table-driven cases against the real `evaluate_scopes`, the admin token endpoint and the gateway, so a code change that contradicts this addendum fails CI. Later units extend the same table for their rows.

## 8. Not yet covered

The public, Authentik-backed operator identity decided on agentops#255 (Q2) adds a fourth resource (`/control/operator`, client `vuoro-operator`, scopes `vuoro:operator.read`, `vuoro:operator.freeze`). Its rows are added with design units O.1-O.2 (design memo §8), not in this addendum.
