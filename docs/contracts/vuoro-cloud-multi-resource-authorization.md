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

Until unit 2.1 adds `users.kind`, every `users` row is treated as `human` by R-mcp and R-control; R-control additionally requires the subject to match `^github:[0-9]+$` so a pattern violator (the blocker12 owner class) cannot obtain a control token.

## 3. Scopes

| Scope | Registry | Resource | Grantable? |
|---|---|---|---|
| `vuoro:work.read` | `SCOPE_TO_AUTHORITIES` (`oauth_scopes.py:19-30`) | R-mcp | yes |
| `vuoro:evidence.record` | `SCOPE_TO_AUTHORITIES`, restricted to `claude-connector` (`:49-51`) | R-mcp | yes, `claude-connector` only |
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

Rows are evaluated top to bottom; the first matching row decides. "Refuse" means OAuth `invalid_scope` (or `invalid_target` for a resource mismatch) and an audit row; on R-admin it means HTTP 400/401/403 and an audit row once a principal is identified.

| # | Client | Resource | Requested scope | Principal kind | Decision |
|---|---|---|---|---|---|
| M1 | any | any | `vuoro:effect.apply` | any | **Refuse**, audited `oauth.scope.rejected_requested` (live) |
| M2 | any | R-mcp | any `vuoro:control.*` or `vuoro:admin.*` | any | **Refuse** `invalid_scope`, audited `oauth.scope.rejected_requested` (unit 1.3) |
| M3 | any | R-mcp | `vuoro:work.claim` or `vuoro:effect.propose` | any | **Refuse** `invalid_scope` while reserved (live) |
| M4 | `claude-connector` | R-mcp | `vuoro:work.read`, `vuoro:evidence.record`, or none (default = both) | human | Grant, bound to one workspace (live) |
| M5 | other registered client | R-mcp | `vuoro:evidence.record` | any | **Refuse** `invalid_scope`; dropped silently from a scope-less default (live) |
| M6 | any | R-control | anything | any, client ≠ `vuoro-cli` | **Refuse** `invalid_target` (unit 3.1) |
| M7 | `vuoro-cli` | R-control | anything outside `CONTROL_SCOPES` | any | **Refuse** `invalid_scope` (unit 3.1) |
| M8 | `vuoro-cli` | R-control | ⊆ `CONTROL_SCOPES` (none = read only) | not human, or subject fails `^github:[0-9]+$` | **Refuse** `access_denied` at authorize; `invalid_grant` at refresh (unit 3.1) |
| M9 | `vuoro-cli` | R-control | ⊆ `CONTROL_SCOPES` | human | Grant; every request still checks `administrative_membership` for the target workspace (unit 3.1) |
| M10 | `vuoro-cli` | R-mcp | anything | any | **Refuse** `invalid_target`: the CLI never holds work-plane tokens (unit 3.1) |
| M11 | any | R-admin, on the public listener or through the gateway | anything | any | **Not routable** (404): no admin route exists on `:8080`, and the gateway refuses `/api/control/v1/admin/*` (units 1.2, 1.3) |
| M12 | any | R-admin, TCP peer outside `VUORO_CLOUD_ADMIN_SOURCE_CIDRS` or `cf-*` header present | anything | any | **Refuse** 403 `admin-source-denied` (unit 1.3) |
| M13 | ≠ `vuoro-cli-admin` (≠ `vuoro-cli-service` from slice 6) | R-admin | anything | any | **Refuse** `invalid_client` (unit 1.3) |
| M14 | `vuoro-cli-admin` | R-admin | anything outside `ADMIN_SCOPES` currently shipped | admin | **Refuse** `invalid_scope` (unit 1.3) |
| M15 | `vuoro-cli-admin` | R-admin | ⊆ shipped `ADMIN_SCOPES` (none = `vuoro:admin.read vuoro:admin.audit.read`) | admin, active, `adm_epoch` current, WebAuthn assertion with UV from an enrolled, non-disabled credential | Grant: access 5 min, refresh rotating ≤ 1 h absolute (unit 1.3) |
| M16 | any | R-admin | anything | not admin (no such subject can present a WebAuthn assertion for an admin credential) | **Refuse** (structural) |
| M17 | `vuoro-cli-service` | R-admin | ⊆ {`admin.read`, `admin.audit.read`, `admin.backup`} | service (JWT-bearer, pinned issuer) | Grant, 5 min, no refresh (slice 6) |
| M18 | `vuoro-agent-delegate` | R-mcp | ⊆ delegation ceiling ⊆ {`work.read`, `evidence.record`} | agent | Grant ≤ 15 min, no refresh, `act` claim (slice 7, gated on plan item 7) |
| M19 | `vuoro-agent-delegate` or admin mint | R-mcp | `vuoro:work.claim` or `vuoro:effect.propose` | agent or test | **Refuse** by name, independently of M3 (slice 4/7) |
| M20 | any | any | none of the above | any | **Refuse** |

## 5. Reserved authorities

- `vuoro:effect.propose` stays reserved until a durable intent store exists **and** every tenant runtime serves the propose tools.
- `vuoro:work.claim` stays reserved until an exclusive, durable lease exists **and** every tenant runtime serves the claim tools.
- No row above grants either. Delegation ceilings and admin mints refuse them by name (M19), so a later edit to `RESERVED_SCOPES` alone does not open them to minted tokens. Lifting a reservation is its own reviewed change and must show both conditions.
- TS-16 is unamended: a cloud caller queues effects and never applies them; acceptance is trusted-side.

## 6. Rechecks

| When | What is rechecked |
|---|---|
| R-mcp refresh | `g.resource` equals the requested resource (`control.py:1142`), grant not revoked or idle-expired, principal epoch, scope narrowing through `evaluate_scopes(..., client_id=...)` (`:1189`) |
| R-control refresh (unit 3.1) | `g.resource` is R-control, client is `vuoro-cli`, principal kind human and subject pattern, principal epoch |
| R-control request (unit 3.1) | `aud`, `typ=at+jwt`, principal epoch, scope, `administrative_membership` for the target workspace; any session cookie on the request → 400 |
| R-admin refresh (unit 1.3) | token hash matches an unused member of a live family, absolute expiry, admin active, `adm_epoch`, credential not disabled; reuse revokes the family |
| R-admin request (unit 1.3) | TCP peer in tunnel CIDR, no `cf-*` header, `aud`, `typ=at+jwt`, admin active, `adm_epoch`, scope |

## 7. Conformance

Unit 1.3 adds `tests/test_scope_matrix.py` to vuoro-cloud. It encodes the rows of §4 that exist at that point (M1-M5, M11-M16) as table-driven cases against the real `evaluate_scopes`, the admin token endpoint and the gateway, so a code change that contradicts this addendum fails CI. Later units extend the same table for their rows.
