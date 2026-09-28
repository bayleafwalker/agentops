# Contract addendum: vuoro.cloud multi-resource authorization

Date: 2026-09-27. Status: **addendum to cloud-enablement plan item 5** ("Freeze a multi-resource authorization spec: client, resource, scope, principal and role policy, with `g.resource` rechecks", `docs/plans/2026-09-26-cloud-enablement-plan.md`). It covers the two resources that the admin-identity design adds (`docs/plans/2026-09-27-admin-identity-and-vuoro-cli-design.md`, unit 0.1), and binds the rules for the operator resource of design units O.1-O.2 (§8). It does not cover the effects resource; item 5 still owes that part.

Code facts are cited at vuoro-cloud Forgejo `main` `2c58ce9` (v0.1.0-poc.50), which contains unit 1.1 (`migrations/014_audit_chain.sql`, #141) and the gateway half of M1 (unit 1.2, #139).

## 1. Resources

| Id | Resource indicator (RFC 8707) | Served on | Grant shape | Status |
|---|---|---|---|---|
| **R-mcp** | `https://api.vuoro.cloud/mcp` (`cfg.resolved_mcp_resource`) | gateway `/mcp` → tenant runtime, through the public edge | authorization code + PKCE; grant bound to **one** workspace (`oauth_grants.workspace_id NOT NULL`, `migrations/012_oauth_authorization_server.sql:53`) | live |
| **R-control** | `https://api.vuoro.cloud/control` | control public listener (`:8080`) under `/api/control/v1/cli/*`, through the public edge | authorization code + PKCE, loopback redirect (RFC 8252); grant spans the principal's memberships (workspace chosen per request, membership checked per request) | unit 3.1 |
| **R-admin** | `https://api.vuoro.cloud/control/admin` | control **admin listener** (`:8443`) under `/api/control/v1/admin/*`, WireGuard tunnel only; the gateway refuses the prefix | WebAuthn challenge grant (no authorize redirect); refresh token rotating, 1 h absolute | unit 1.3 |
| **R-operator** | `https://api.vuoro.cloud/control/operator` | control public listener under `/api/control/v1/ops/*`, through the public edge | Authentik OIDC, authorization code + PKCE; step-up for freeze/unfreeze (§8) | O.1-O.2 |

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

Until unit 2.1 adds `users.kind`, every `users` row is treated as `human` by R-mcp and R-control; R-control additionally requires the subject to match `^github:[0-9]+$` so a pattern violator (the blocker12 owner class) cannot obtain a control token. The pattern admits a leading zero (`github:01005`), which GitHub never issues; unit 2.4's CHECK design states whether it narrows to `^github:[1-9][0-9]*$`.

**Audit `actor_kind`.** The shipped `014` CHECKs `audit_events.actor_kind` to `admin`, `user`, `test`, `agent`, `service`, `policy`, `break-glass`, `anonymous`, `operator`, `connector`. A `human` principal is recorded as `user`; an R-operator subject (§8) as `operator`; `test`, `agent`, `connector`, `admin` and `service` are recorded as named. No writer copies `users.kind` into `actor_kind` unmapped: `'human'` fails the CHECK, and because the audit insert shares the request's transaction, the request fails with it.

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

`CONTROL_SCOPES` are member-plane operations: they act only on the caller's own memberships and credentials, with `administrative_membership` checked per request. #255 Q2's protected-only operations (credential/policy change, recovery and the rest) are operator operations and live on R-admin (design memo §8.2 C3, C7); member PATs under `vuoro:control.token.manage` are transitional (C7).

## 4. Decision matrix

Rows are evaluated top to bottom; the first matching row decides. Transport rows come first, then permanent refusals, then per-resource rows with the more specific client before the general one. "Refuse" means OAuth `invalid_scope` (or `invalid_target` for a resource mismatch, `invalid_client`, `invalid_grant`, `access_denied` as named) plus an audit row; on R-admin it means HTTP 400/401/403, audited under the named event once a principal or credential is identified.

| # | Client | Resource | Requested scope | Principal kind | Decision |
|---|---|---|---|---|---|
| M1 | any | R-admin path on the public listener or through the gateway | anything | any | **Not routable** (404): the gateway returns 404 `route-not-found` for `/api/control/v1/admin` and everything under it, case-insensitive and with repeated `/` collapsed, before auth and body read (**live**, unit 1.2, #139); control's public process has no admin route, and answers 404 (unit 1.3) |
| M2 | any | R-admin, TCP peer not an enrolled `/32` (the operator's; slice 6 adds the appservice peer's), or a `cf-*` header present | anything | any | **Refuse** 403 `admin-source-denied`, counted, not DB-audited (no principal yet) (unit 1.3) |
| M3 | any | any | `vuoro:effect.apply` | any | **Refuse**, audited `oauth.scope.rejected_requested` (live) |
| M4 | any | R-mcp | any `vuoro:control.*`, `vuoro:admin.*` or `vuoro:operator.*` | any | **Refuse** `invalid_scope`, audited `oauth.scope.rejected_requested` (unit 1.3, whose `FOREIGN_SCOPE_PREFIXES` therefore carries all three prefixes) |
| M5 | any | R-mcp | `vuoro:work.claim` or `vuoro:effect.propose` | any | **Refuse** `invalid_scope` while reserved (live); for minted tokens also by name (M12, M15) |
| M6 | ≠ `vuoro-cli-admin`, ≠ `vuoro-cli-service` | R-admin | anything | any | **Refuse** `invalid_client` (unit 1.3) |
| M7 | `vuoro-cli-service` | R-admin | ⊆ {`admin.read`, `admin.audit.read`, `admin.backup`} | service (JWT-bearer, pinned issuer) | Grant, 5 min, no refresh (slice 6); anything else **Refuse** |
| M8 | `vuoro-cli-admin` | R-admin | anything | admin inactive, `adm_epoch` stale, credential disabled or unknown, assertion without UV | **Refuse** 401, audited `admin.login.refused` / `admin.token.refused` with the reason code (unit 1.3) |
| M9 | `vuoro-cli-admin` | R-admin | anything outside the shipped `ADMIN_SCOPES` | admin | **Refuse** `invalid_scope` (unit 1.3) |
| M10 | `vuoro-cli-admin` | R-admin | ⊆ shipped `ADMIN_SCOPES` (none = `vuoro:admin.read vuoro:admin.audit.read`) | admin, active, `adm_epoch` current, WebAuthn assertion with UV from an enrolled, enabled credential listed in `allowCredentials` | Grant: access 5 min, refresh rotating ≤ 1 h absolute (unit 1.3) |
| M11 | `vuoro-cli-admin` | R-admin | anything | any non-admin (no WebAuthn credential exists for it) | **Refuse** (structural) |
| M12 | `vuoro-test-harness` or `vuoro-agent-delegate` (admin mint or delegated exchange) | R-mcp | names `vuoro:work.claim` or `vuoro:effect.propose` | any | **Refuse** by name, independently of M5 (slices 4, 7) |
| M13 | `vuoro-test-harness` via the admin mint endpoint | R-mcp | ⊆ {`vuoro:work.read`, `vuoro:evidence.record`} | test, not expired, member of a test workspace | Grant by admin mint only, ≤ min(24 h, expiry), no refresh (slice 4); other kinds **Refuse** |
| M14 | `vuoro-agent-delegate` via the RFC 8693 exchange | R-mcp | ⊆ delegation ceiling ⊆ {`work.read`, `evidence.record`}, workspace ∈ delegation workspaces, repos ⊆ delegation repos | agent, not expired, active membership with role ≤ `member` in that workspace | Grant ≤ 15 min, no refresh, `act` claim. The exchange inserts a row **in `oauth_grants`** carrying the delegation's `repo_ids` (grant id in the token), so the gateway's per-request grant, membership, workspace and epoch check (`gateway.py:903-921`) applies; slice 7 also makes the gateway intersect the repositories it forwards (today every repository in the workspace, `gateway.py:151-152`, `:1063`) with the grant's `repo_ids`. The row's `refresh_hash` (`NOT NULL`, `012`) is the hash of a secret that is never returned, and its `expires_at` equals the access token's expiry (≤ 15 min), so the live refresh path (`refresh_access_token`, `control.py:1146`) has nothing to redeem; `vuoro-agent-delegate` is refused at `/oauth/authorize` and `/oauth/token` (M16a). For `client_id = vuoro-agent-delegate`, a NULL or empty `repo_ids` refuses (a CHECK in migration `023`), so a row written without repositories never fails open to the whole workspace. Disabling the delegation revokes that row (slice 7, gated on plan item 7) |
| M15 | `vuoro-agent-delegate` via the RFC 8693 exchange | R-mcp | anything else, including a reserved scope in the ceiling | any | **Refuse** (slice 7) |
| M16a | `vuoro-cli-admin`, `vuoro-cli-service`, `vuoro-test-harness` or `vuoro-agent-delegate` on `/oauth/authorize` or `/oauth/token` (M12-M15 decide only the admin mint and the exchange) | R-mcp | anything | any | **Refuse** `unauthorized_client`: these clients never use the authorization-code path; unit 1.3 refuses them by id there, with a conformance case |
| M16b | `vuoro-cli` | R-mcp | anything | any | **Refuse** `invalid_target`: the CLI never holds work-plane tokens (unit 3.1; placed here so no later grant row can match it) |
| M16 | `claude-connector` | R-mcp | `vuoro:work.read`, `vuoro:evidence.record`, or none (default = both) | human (GitHub login), or test via a single-use test-login code (slice 4) | Grant, bound to one workspace the principal is an active member of (live for human) |
| M17 | other registered client | R-mcp | `vuoro:evidence.record` | any | **Refuse** `invalid_scope`; dropped silently from a scope-less default (live) |
| M17a | any registered client not named in M6-M17 (today none is registered besides `claude-connector`; `vuoro-cli`, `vuoro-cli-admin`, `vuoro-cli-service`, `vuoro-test-harness`, `vuoro-agent-delegate` are decided above; `vuoro-operator` and `vuoro-operator-step-up` are never registered here, §8, so this row must stay unmatched for them) | R-mcp | `vuoro:work.read` or none | human, active member of the workspace | Grant, bound to that one workspace (live: `evaluate_scopes` grants it to any registered client; `grant_usable` checks membership) |
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
| R-mcp refresh (live) | the request's `resource` parameter, if given, equals the configured MCP resource (`control.py:1147`); `client_id` matches the grant (`control.py:1159`); grant not revoked, idle-expired or past absolute expiry (`:1186`); the new token is stamped with the current principal epoch (not compared; the gateway compares it per request, `gateway.py:920`); scope narrowing through `evaluate_scopes(..., client_id=...)` (`:1194`) and still grantable (`:1202`); membership and workspace still active via `grant_usable` (`:1206`, `:662-665`). **Not** rechecked today: the grant's stored `resource`; `aud` is the MCP resource constant (`mint_access_token`, `:741-760`). This is correct only while every grant is an R-mcp grant. |
| R-mcp and R-control refresh (unit 3.1 obligation) | the grant's stored `resource` (`g.resource`) equals the resource being refreshed and the client's registered resource; `aud` of the minted token is taken from `g.resource`, never a constant; an R-control grant presented at the R-mcp token path is `invalid_grant` by name, not by accident. Unit 3.1 adds conformance cases for both directions. |
| R-control refresh (unit 3.1) | client is `vuoro-cli`, principal kind human and subject pattern, principal epoch |
| R-control request (unit 3.1) | `aud`, `typ=at+jwt`, principal epoch, scope, `administrative_membership` for the target workspace; any session cookie on the request → 400 |
| R-admin refresh (unit 1.3) | token hash matches an unused member of a live family, absolute expiry, admin active, `adm_epoch`, credential not disabled; reuse revokes the family |
| R-admin request (unit 1.3) | TCP peer is an enrolled `/32` (the operator's; slice 6 adds the appservice peer's), no `cf-*` header, `aud`, `typ=at+jwt`, admin active, `adm_epoch`, scope |
| R-operator freeze/unfreeze (O.2) | signature against the pinned Authentik JWKS, `iss`, `aud`, client `vuoro-operator-step-up`, subject not denied, the scope for exactly this action, `acr` equal to the step-up value, `auth_time` ≤ 5 min (or `iat`, §8.1 A2), `jti` unused (§8) |
| Delegated agent request (slice 7) | the gateway's grant query plus: forwarded repositories ⊆ the grant's `repo_ids`, and the membership role still ≤ `member` (M14 checks it at mint; the gateway returns `m.role` but does not limit it today); a request naming a repository outside them is refused (403). Slice-7 conformance cases: that refusal, and a refresh-token request for a delegated grant (refused) |

## 7. Conformance

Unit 1.3 adds `tests/test_scope_matrix.py` to vuoro-cloud. It encodes the rows of §4 that exist at that point (M1-M6, M8-M11, M16, M16a, M17, M17a) as table-driven cases against the real `evaluate_scopes`, the admin token endpoint and the gateway, so a code change that contradicts this addendum fails CI. Later units extend the same table for their rows. Where M4 or M5 precede M16b, a `vuoro-cli` request for R-mcp that names a control, admin, operator or reserved scope expects `invalid_scope`, not `invalid_target`. O.1-O.2 add the §8 cases.

## 8. R-operator: binding rules, rows to come

The public, Authentik-backed operator identity decided on agentops#255 (Q2) adds a fourth resource. Its matrix rows are added with design units O.1-O.2 (design memo §8.4); until then every R-operator request falls to M22. The rows must follow these rules, which bind now:

- **Resource.** R-operator = `https://api.vuoro.cloud/control/operator`, served on control's public listener under `/api/control/v1/ops/*` (not `/operator/`, which the Cloudflare edge rule restricts).
- **Issuer.** Tokens are issued by Authentik and verified against a JWKS pinned in Git-reviewed config, with the issuer and the step-up `acr` value. Two Authentik providers, each a public client with PKCE used by `vuoro-cli ops …` with a loopback redirect (CLI only, §8.1 A5): `vuoro-operator` issues `vuoro:operator.read` only, and `vuoro-operator-step-up` issues the step-up scopes only (§8.1 A2). Neither is **ever** a client of control's own authorization server: registered there, M17a would grant it an R-mcp `work.read` token. An R-operator token signed by control's authorization server is refused.
- **Read scope.** `vuoro:operator.read`, from the OIDC login flow of `vuoro-operator`: status, tenants, audit and health; tenant metadata and audit rows only, never tenant work content, and never a membership check.
- **Step-up scopes.** `vuoro:operator.freeze` and `vuoro:operator.unfreeze` (one per action):
  - never present in a `vuoro-operator` token; issued only by `vuoro-operator-step-up`, whose authorization flow runs a WebAuthn-with-UV stage on every request and whose property mapping emits the pinned step-up `acr`;
  - requested by a separate step-up authorization request for exactly one of them (the CLI also sends `prompt=login`, `max_age=0` and `acr_values=<step-up acr>`, which are not relied on);
  - accepted only from client `vuoro-operator-step-up`, when `acr` **equals** the pinned step-up value and `auth_time` is ≤ 5 min old (`iat` if O.1's acceptance shows Authentik does not refresh `auth_time` on the ceremony, §8.1 A2); otherwise 401 with an RFC 9470 `insufficient_user_authentication` challenge (`acr_values`, `max_age`);
  - `jti` required and single-use, bound to the action by the scope: a freeze token cannot unfreeze, a token carrying both is refused, and a used `jti` is refused until the token expires (≤ 5 min);
  - every call carries a reason and is audited (`actor_kind='operator'`, credential = client id and `jti`); a freeze set on the tunnel plane is lifted only there (§8.1 A3);
- **Namespace.** `vuoro:operator.*` is refused on R-mcp (M4), alongside `vuoro:control.*` and `vuoro:admin.*`.
- **Protected-only operations.** Nothing that #255 lists as protected-only (effect acceptance, credential/policy change, promotion, key rotation, recovery operations) gets an R-operator row, and no workspace lifecycle mutation does either: freeze/unfreeze are the only R-operator mutations (§8.1 C3).
- **Deny list.** Denied operator subjects are listed in the same Git-reviewed config as the pinned JWKS, written only through a reviewed change and a signed promotion; there is no database table for it (§8.1 A4).
- **Conformance cases (§7, with O.1-O.2).** A `vuoro-operator` token cannot freeze or unfreeze (403 `insufficient_scope`), and one carrying a step-up scope is refused; a step-up token with a wrong or missing `acr`, or a stale `auth_time`, is challenged (401); a replayed `jti` and a token without `jti` are refused; a freeze token presented to unfreeze is refused; `vuoro:operator.*` at R-mcp is `invalid_scope`; `vuoro-operator` or `vuoro-operator-step-up` at control's `/oauth/authorize` is refused; a public unfreeze of a tunnel-plane freeze is refused.

### 8.1 Decisions (2026-09-28)

Delegated by the operator to the planner and recorded with rationale in the design memo §8.5 (agentops#262); the memo and this addendum agree on each.

| # | Decision | Why (short) | Effect on this contract |
|---|---|---|---|
| A1 | Separate `vuoro:operator.freeze` / `vuoro:operator.unfreeze` scopes bind the action; no RFC 9396 `authorization_details`. | Authentik documents no RAR support; one scope per action plus a single-use `jti` gives the same binding with plain scopes. | §8 step-up bullets as written. |
| A2 | Two Authentik providers from the start: `vuoro-operator` (read) and `vuoro-operator-step-up` (freeze/unfreeze, WebAuthn-with-UV stage in its authorization flow). No single-provider path. | A provider has one authentication and one authorization flow, so a step-up on the login provider cannot be told apart from a login (#255 Q2). | §6 recheck and §8 accept freeze/unfreeze only from `vuoro-operator-step-up`. O.1's acceptance check: a step-up token obtained during a live, older Authentik session carries the pinned `acr` and a fresh `auth_time`; if `auth_time` is not refreshed, O.2 checks `iat` ≤ 5 min with a ≤ 5 min token validity instead. |
| A3 | A tunnel-plane freeze is lifted only on the tunnel plane. | The protected horizon owns authority; a lower-assurance identity must not undo it. | Conformance case added. |
| A4 | Operator deny list in Git-reviewed config beside the pinned JWKS, not a table. | A table in control's database is writable by a compromised public horizon; Git plus signed promotion is the protected write path. | §8 "Deny list"; no O.1 migration. |
| A5 | Operator surface CLI-only for O.1-O.2. | A page on the public horizon would hold a freeze-capable token. | §8 "Issuer". |
| C1 | The protected plane keeps its reads. | #255 permits reads anywhere; they work when Authentik is down. | None (R-admin `admin.read` as in §3-§4). |
| C3 | No workspace lifecycle mutation gets an R-operator row. | #255 names only freeze as a public mutation. | §8 "Protected-only operations". |
| C8 | Automated drills through the `vuoro:admin.backup` drill route, without an operation assertion, target fixed to `vuoro-restore-drill`. | Cheap, recurring check that backups restore; #255 allows drills with cluster-reaching credentials on the protected side. | M7 (`vuoro-cli-service`, `admin.backup`) as written; a drill targeting any other namespace is refused. |
| C9 | A second WireGuard peer for the appservice cluster, protected → public only, with Q5's AllowedIPs and drop rules applied to it. Flips to running `vuoro-ops` on the workstation only if no appservice host can hold a WireGuard key with UDP egress to the VPS allowed by OPNsense. | Pull-only preserves "no public → protected service path". | M2 and §6 "slice 6 adds the appservice peer's `/32`" as written. |
| Nit 6 | No operator audit row is written after a production classification run. | The run is superuser `kubectl exec`; a hand-written superuser `INSERT` is self-attested and is the unaudited-write path the chain exists to distrust (and the kind of kubectl-plus-SQL write §7 Q2 of the memo rules out). The output's sha256, database and time in the private evidence area are the check. | Runbook "Where to run it". |
