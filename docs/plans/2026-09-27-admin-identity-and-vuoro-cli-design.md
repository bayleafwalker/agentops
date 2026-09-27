# Design memo: separated admin identity and `vuoro-cli` for vuoro.cloud

Date: 2026-09-27. Status: **decided, revision 7.** The operator's answers to the open questions are recorded in §7. Revision 2 addressed the first independent review on agentops#262 (6 major, 8 minor, 2 nit) and split; revision 3 addressed the re-review (4 major, 10 minor, 5 nit); revision 4 addressed the third review (1 blocker, 2 major, 8 minor, 5 nit); revision 5 reconciles the design with the operator's later answers on agentops#255 (§8); revision 6 addressed the fourth review; revision 7 addresses the review of revisions 5-6 (unit 1.5 ordering, leftover contradictions with §8, conflicts C8-C10). The memo splits the work into implementable units (§5, unit table). This memo changes no code; the units in §5 do.

## Verification status (read first)

- **Re-checked against:** vuoro-cloud Forgejo `main` at `332faa4` ("Release v0.1.0-poc.47 promotion candidate", 2026-09-27). Revision 1 read the GitHub mirror at `96684ad` (poc.46); between the two, `control.py` changed two lines (`evaluate_scopes(..., client_id=client.client_id)` at `:826` and `:1189`) and every citation below still holds. Paths cited as `vuoro-cloud:<file>:<line>` were read at `332faa4`.
- **vuoro-client** was read at bayleafwalker/vuoro `fd342e8` (`packages/vuoro-client` 0.1.1).
- **[U]** marks a claim that is still unverified in code: it comes from the operator's brief and was not found or not checked.
- **cred-broker internals** were not attached, so claims about them stay **[U]**. The cred-broker **public README** was read on 2026-09-27. It says production use requires "verified mTLS and server-side session state", and that "provider adapters are disabled until an operator supplies dedicated provider identities, a protected signing/key substrate, enrolled client certificates, and live positive and negative canary evidence."
- **[A]** marks an inference or assumption: a claim about third-party behaviour (barman-cloud, S3 providers, WebAuthn clients, k3s port mapping) that this pass did not test.
- **Verified in this repo:**
  - TS-1 and TS-16 (`docs/plans/2026-09-17-target-state.md:30`, `:45`);
  - the effects decision and the "Required before slice 1" list (`docs/plans/2026-09-26-cloud-enablement-plan.md:31-59`);
  - the trusted-service design and its threat model (`docs/plans/2026-09-26-trusted-service-boundary-design.md`).

### What the code check confirmed and corrected

| Brief claim | Result at `332faa4` |
|---|---|
| Workspace PATCH is browser-only: cookie, CSRF, `administrative_membership` | **Confirmed.** `control.py:3270-3283` (`Depends(browser)`); the CSRF double-submit check is at `control.py:271-300`. |
| `operator()` is a hash-checked static bearer with a CIDR allow-list | **Confirmed, with a correction.** The CIDR check reads the **`cf-connecting-ip` header** (`control.py:217-241`). Operator calls therefore arrive **through Cloudflare / cloudflared on `api.vuoro.cloud`** (`platform/cloudflared/deployment.yaml:33-36`), not over the WireGuard tunnel. Whoever can send traffic to control without passing through Cloudflare (a compromised cloudflared or any in-cluster pod with a route to control) can set that header. The audited actor is the literal string `"operator"` (`control.py:242`). |
| Admin routes would not be edge-reachable | **Wrong by default.** cloudflared sends `api.vuoro.cloud` to `vuoro-gateway`, and the gateway proxies every `/api/control/{path:path}` to control (`gateway.py:682-698`). Any new `/api/control/v1/admin/*` route on control's public listener would be publicly routable. Control's only ingress is from gateway pods and the observability namespace (`platform/policies/network-policies.yaml:18-24`, `:95-101`); no NetworkPolicy admits the WireGuard interface today, although `kubectl port-forward` over the tunnel (API server at `10.44.0.1:6443`) bypasses NetworkPolicy and reaches `:8080`, and `scripts/record_backup_observation.py:199-225` uses exactly that with a hand-set `CF-Connecting-IP`. This memo therefore adds an explicit gateway deny, a separate admin process and a tunnel ingress (D1, unit 1.3), and retires the header-trusting operator token (unit R). |
| Operator routes: rollout status, epoch bump, drain, backup observations, invitations, invite requests, service controls, analytics | **Confirmed, and there are more:** operator **tenant-migration** routes `…/migration/plan`, `start`, `retry` and `status` also exist, and require the workspace to be `DRAINING` (`control.py:1405-1650`). |
| No route to retire, delete, transfer or create principals | **Partly wrong.** The member-only PATCH accepts `desired_state=DELETED`. It sets `DELETION_REQUESTED` (`control.py:3292`), and the controller then scales the runtime to 0 and marks the workspace **`RETAINED`** (`controller.py:145-168`). Nothing ever tears down the namespace, database or roles. There is **no operator route** for this, and no route at all for transfer or principal creation. |
| users table `(id, external_subject, display_name, created_at)` | **Confirmed.** `migrations/001_control.sql:3-8`, no `CHECK` on `external_subject`. Principals are also registered in `principal_subjects(subject, kind IN ('user','connector'), actor, epoch)` (`migrations/008_principal_epoch.sql:6-13`); `subject` is CHECKed colon-free (`:7`), and migration 009 backfilled `kind='user'` rows keyed on `users.id`. |
| The only sign-in path is GitHub OAuth, subject `github:<numeric id>` | **Confirmed** for the callback (`oauth.py:94`, `f"github:{value['id']}"`). Invitation redemption checks only `subject.startswith("github:")` (`control.py:1896`). |
| `SCOPE_CLIENT_RESTRICTIONS` and the `claude-connector` client | **On `main`** (`oauth_scopes.py:49-51`): `vuoro:evidence.record → {claude-connector}`, and `vuoro:evidence.record` is grantable (`:19-30`). `evaluate_scopes` (`:137-177`) refuses an **explicit** request for a restricted scope by another client with `invalid_scope`; only the scope-less default grant drops it silently (`:154-163`). `vuoro:work.claim` and `vuoro:effect.propose` are reserved (`:34-37`), `vuoro:effect.apply` is permanently rejected (`:40`). |
| Access token 15 min | **Confirmed.** `oauth_server.py:35` (`ACCESS_TOKEN_TTL_SECONDS = 900`). |
| `audit_events` exists | **Confirmed, and weak.** `(id, workspace_id, actor text, action, target, request_id, details jsonb, created_at)` (`migrations/001_control.sql:173-182`). No hash chain, no insert-only guard, no credential or reason fields. Writers: control and the gateway (`gateway.py:1100`, `:1186`). |
| Control's DB role and the migration role | **Same role.** The migration Job and the control Deployment both take `envFrom: vuoro-control-runtime` (`apps/control/migration-job.yaml:21-23`, `apps/control/deployment.yaml`), so control's runtime role owns every table it created. |
| CNPG with barman to `s3://vuoro-cloud-poc-cnpg-backups`, daily | **Confirmed, and unencrypted.** `platform/cnpg/repository.yaml:23-43`: endpoint `https://hel1.your-objectstorage.com` (Hetzner Object Storage), `retentionPolicy: 14d`, gzip, daily `ScheduledBackup` at 02:15. There is **no `encryption` key** on `wal` or `data`. |
| vuoro-client provides HTTP, profiles, User-Agent and a keyring | **Partly.** `vuoro-client` 0.1.1 is the protocol-v1 transport for the Vuoro runtime. It sets `User-Agent: vuoro-client/<version>` on its own client (`client.py:41`, `:65`) and loads `Profile(name, endpoint, credential_ref, expected_environment)` (`profile.py:20-24`), refusing a production target when the profile sets `production_endpoint_denied` (`:52-53`). It has no keyring and does not speak the control API. |
| blocker12-canary origin | **Consistent.** `IMPLEMENTATION-STATUS.md:265, 395-405` describe the "blocker-12 canary" as the first live provisioning trial: generations 1-2 failed, and 3-5 reconciled to `READY` at observed generation 5. The owner's IDs, subject and schema-12 state are **[U]**: they are live database contents. |

**How the corrections change the design:**

- **The operator token is edge-reachable, and so would be any new control route.** The admin plane gets its own listener that the gateway cannot reach, an explicit gateway deny, and a tunnel ingress identified by the L3 peer (D1).
- **Operator drain and tenant migration already exist.** blocker12's schema lag could be fixed today without its owner. Retirement still cannot be done.
- **`DELETED` only retains.** "Retire" in this design is new teardown work on top of the existing `RETAINED` state.
- **Per-client scope restriction already exists and already refuses explicit requests.** What is new is refusal **by principal kind** and by **scope namespace** (`vuoro:control.*`, `vuoro:admin.*` are never grantable on the `/mcp` authorize/token path).
- **The control role owns `audit_events`.** An insert-only guard is a trigger until the owner/runtime role split lands (D7).
- **`vuoro-cli` does not build on vuoro-client.** It speaks the control API with its own small httpx client (D4, packaging).

## Recommendation in one paragraph

- **Admin is a separate kind of principal.** It lives in its own table, uses the actor namespace `admin:<ulid>`, authenticates with WebAuthn only (YubiKey, PIN-verified), and has no membership rows. GitHub is never a factor.
- **The admin plane is a separate control process** (`vuoro-control-admin`, same image and database), reachable only over the operator WireGuard tunnel: a hostIP-bound port on the tunnel address, admitted by NetworkPolicy from the operator's tunnel `/32` only, and checked again in the app against the TCP peer address. The gateway refuses `/api/control/v1/admin/*` explicitly. Every mutation carries a WebAuthn assertion over the operation's digest; that assertion is the record that the key was touched for exactly those parameters.
- **The user plane gains a bearer path** (a second resource, membership still checked). `vuoro-cli` can then do what browser-console `fetch()` does today, without touching the cookie/CSRF routes.
- **Test principals** are a separate kind of principal (`test:<ulid>`). They are admin-minted, bound to test workspaces, expire, and are retired automatically. The "never `github:`" rule becomes a database constraint, landed in two generations so blocker12's owner can be reclassified through the admin API first.
- **Minted tokens for agents are allowed in one narrow shape only:**
  - access tokens (no refresh token);
  - ≤ 15 minutes;
  - `aud=/mcp`, work-plane scopes only, and never a reserved authority (`vuoro:effect.propose`, `vuoro:work.claim`) while it is reserved;
  - for a non-admin **agent principal**;
  - issued by control under an admin-authored delegation ceiling;
  - delivered by cred-broker to **perimeter** workloads that pass its mTLS workload auth.

  Cloud sessions never get them. They keep using the claude-connector OAuth grant. Control-plane and admin tokens are never mintable for workloads.
- **`vuoro-cli` is one package in vuoro-cloud with two faces:**
  - a human CLI (PKCE loopback for the user face; a loopback-page WebAuthn challenge for the admin face; separate `login` and `admin login`);
  - a small trusted-side service in the appservice cluster. It holds only observe, backup and drill scopes, and never destructive ones.
- **The first slice** is the admin principal, WebAuthn login, read-only admin routes, the gateway deny and the hash-chained audit trail. It depends on nothing in the "Required before slice 1" list except the multi-resource authorization spec (item 5), whose addendum slice 0 delivers.

---

## 1. Context

### Why now

- **One human, one account.** Sign-in is GitHub OAuth only (`github:<numeric id>`, `vuoro-cloud:src/vuoro_cloud/oauth.py:94`). The operator has one GitHub account, so the person who owns kotona is also the only possible administrator. Administration then either happens as a tenant member, or through a shared static secret.
- **Administration today is a shared secret plus copy-paste.**
  - The `operator()` bearer is a hash-checked static token. Its CIDR allow-list is evaluated on Cloudflare's `cf-connecting-ip` header, and the audit actor is the literal `"operator"` (`control.py:217-242`).
  - Workspace PATCH accepts only a browser cookie, CSRF and `administrative_membership` (`control.py:3270-3283`). Operators paste `fetch()` calls into a browser console.
  - Backups are `kubectl` over the WireGuard tunnel **[U]** (operator practice; the tunnel is described in `08-K3S-POC-DEPLOYMENT.md:27-45`).
- **What is missing:**
  - Teardown: `desired_state=DELETED` only reaches `RETAINED` (`controller.py:145-168`).
  - Any operator or admin deletion path.
  - Ownership transfer or recovery.
  - Principal creation.
- **The orphan incident.**
  - Workspace `blocker12-canary` (`01M14W25EYKC…`) is owned only by `01M14W25EYSZ…`. That user's subject is `github:`-prefixed but non-numeric; it is a synthetic identity from the supervised canary trial of 2026-08-29 (`IMPLEMENTATION-STATUS.md:532-541` records workspace `01M14W25EYKCEX0BTYK1WHJAAK` and that trial, at work schema 7). The owner's id and subject and the current schema 12 remain **[U]**.
  - Nobody can sign in as that user. The workspace cannot be rolled, drained by its owner or retired, and it sits on an old runtime at work schema 12 **[U]**.
  - Two defects produced it:
    1. nothing stops a non-OAuth writer from creating a `github:` subject;
    2. every lifecycle path goes through a member's session.
  - It stays parked, with no bypass of membership checks, until the audited admin retirement path in this design exists (slice 2, §7 Q2).

### Binding constraints this design must respect

| Constraint | Source | Consequence here |
|---|---|---|
| A cloud caller queues effects and never applies them. Acceptance happens on the trusted side; auto-accept is opt-in, off by default, trusted-side-set, asynchronous and recorded as the acceptor. | TS-16 (`2026-09-17-target-state.md:45`), unamended; cloud-enablement plan §"Effects" | The admin plane is trusted-side only. `vuoro-cli` is where the operator's interactive accept/reject lives, and where auto-accept policy is set. Nothing in this design gives a cloud caller a control-plane or admin audience. |
| C1: a synchronous propose is apply authority. | plan, decision 7 | Minted agent tokens carry no scope that performs an effect during the call. |
| **Reserved authorities.** `vuoro:effect.propose` stays reserved until a durable intent store exists **and** every tenant runtime serves the propose tools. `vuoro:work.claim` stays reserved until an exclusive, durable lease exists **and** every tenant runtime serves the claim tools. | operator decisions 2026-09-26; `oauth_scopes.py:22-29`, `:34-37` | No unit in this memo grants either scope to any client, principal kind or delegation. Delegation ceilings refuse them by name (D3), and slice 7's forced failures test both. A later change that ungates either one edits `oauth_scopes.py` under its own review, not this design. |
| H1: multi-resource authorization is a spec, not "one audience plus one table". | plan item 5 | The two new resources defined here (`/control`, `/control/admin`) are inputs to that spec (slice 0). They are not added ad hoc. |
| H2: no bearer forwarding. Use one-use, body-bound internal proofs. | plan item 6 | No component forwards a caller's bearer. The CLI service and cred-broker authenticate as themselves. |
| H8: cred-broker workload auth is not deployment-ready. | plan item 7; README | Minting through cred-broker is gated on item 7. Nothing earlier depends on it. |
| Cloud sessions never hold CLI or admin credentials. | plan decision 4 | This is enforced structurally: loopback-only redirect URIs, client restrictions, tunnel-only admin ingress and WebAuthn. |
| No bypass of membership checks. | operator policy | The admin plane never reads or writes tenant work data and never calls `administrative_membership`; it operates on workspaces as platform lifecycle. User-plane bearer routes keep `administrative_membership`. |
| Release promotion stays YubiKey-signed and operator-held. | plan decision 6 | Out of scope for `vuoro-cli`. The CLI never signs or promotes. |
| Cockpit writes go through the API, never raw DB writes. | `AGENTS.md` | This extends by analogy: blocker12 cleanup goes through the admin API, not psql. |

---

## 2. Threat model

| Actor | What they hold | Worst case without this design | Mitigation in this design | Residual |
|---|---|---|---|---|
| **Operator, user identity** (GitHub OAuth, owns kotona) | Browser session, PATs | GitHub account takeover gives full control of kotona, and today of *administration by membership* | User identity has no admin authority. A GitHub compromise yields only tenant-level authority on kotona. | Kotona data and settings, until the principal epoch is bumped |
| **Operator, admin identity** | Two enrolled YubiKeys (FIDO2 plus PIN) | n/a (new) | Tunnel-only ingress. Per-mutation, digest-bound WebAuthn. PIN for destructive operations. Out-of-band notification. 24 h teardown hold for human-owned workspaces. | A coerced or careless operator |
| **Test principals** | Admin-minted test-login codes or tokens | Synthetic `github:` owners create orphans (today's incident) | `test:` namespace enforced by a CHECK constraint. Test workspaces only. Expiry and reaper. | Test workspaces, until expiry |
| **Claude connector / cloud agents** | claude-connector access and refresh tokens (aud `/mcp`) | Scope creep into control through a default grant | `vuoro:control.*` and `vuoro:admin.*` are never grantable on the `/mcp` authorize/token path: any request naming them is `invalid_scope` for every client. Control scopes are issued only on the `/control` resource to `vuoro-cli` for human principals; admin scopes only on the admin listener. | As today (TS-16 surface) |
| **Appservice-cluster workloads** (vuoro-cli service, cred-broker) | Workload identity to control | A static operator token in a pod equals administration | The service holds observe, backup-trigger and drill scopes only; no step-up is possible without a YubiKey. cred-broker can mint only within the control-side delegation ceiling. | Backup and drill noise. Work-plane read or record tokens for agent principals, ≤ 15 min each. |
| **Compromised edge** (cloudflared, gateway) | Gateway assertion key, public ingress, and (today) the database role it shares with control | **Today:** operator routes are served on `api.vuoro.cloud` through cloudflared. The CIDR check trusts `cf-connecting-ip`, so a compromised cloudflared can pass it and needs only the static token. | Admin routes exist only in the `vuoro-control-admin` process. The gateway refuses `/api/control/v1/admin/*` (404) before proxying, and its upstream is the public control process, which has no admin routes. NetworkPolicy admits the admin port from the operator's `/32` only; the admin app checks the TCP peer (not a header) and refuses any request carrying `cf-*` headers. After unit 1.5 the gateway has its own database role with no access to admin tables. The static operator token is retired after slices 2 and 3 (§5). | Same as today for the work plane, and for operator routes until the token retires |
| **In-cluster pod with a route to control** | Pod network | Sets `cf-connecting-ip` and uses a leaked operator token | Admin listener: NetworkPolicy has no pod or namespace selector for the admin port, and the peer check refuses pod-network sources. | Operator routes until the token retires |
| **Compromised operator laptop** | CLI credential store: user tokens, admin refresh token (≤ 1 h), a plugged-in YubiKey | Static operator token on disk equals administration indefinitely | No long-lived admin secret on disk. Mutations need a touch, destructive ones need touch plus PIN. Notifications. Teardown hold. | ≤ 1 h of admin reads. Malware can prompt touches while the key is plugged in and can render a misleading confirmation page: the YubiKey has no display, so the operator cannot see what the key signs. The phone notification (which shows control's own record of the operation) and the 24 h hold are the backstop. |
| **Public operator identity** (O.1-O.2, Authentik OIDC) | Operator read token; step-up token for freeze | n/a (new) | Reads only; freeze/unfreeze needs step-up with `auth_time` ≤ 5 min and a phishing-resistant factor; each call audited with reason; no admin-plane or acceptance authority | An attacker with a stolen step-up session can freeze or **unfreeze during an incident** within the step-up window; the tunnel-plane twin can re-freeze |
| **Tenant controller** (holds the CNPG superuser, `platform/cnpg/repository.yaml:7-9`) | Superuser on the control database | Could insert an admin credential or rewrite audit | Not closed by this design; listed so it is not mistaken for covered. The off-cluster audit mirror detects rewrites. Narrowing the controller to a tenant-provisioning role is follow-up **F-1** (§5), outside these units. | As compromised control |
| **Compromised control** (AS plus DB, or the control DB role) | Everything | Total | Off-cluster audit mirror and chain verification by the appservice service. WebAuthn assertions are verifiable offline. | Total; detected after the fact. Until the owner/runtime role split lands, the control role can also disable the insert-only trigger; the hash chain plus the off-cluster mirror detect a rewrite. |

---

## 3. Decisions

### D1. Identity model

**Options.**

| | Shape | Verdict |
|---|---|---|
| a | `is_admin` flag on the existing `users` row | **Reject.** Admin becomes GitHub-authenticated, it is one account for both roles (what the operator wants to escape), and every membership code path has to learn to ignore it. |
| b | Admin row in `users` with an `admin:` subject and a different login method | **Reject.** Membership queries, `ROLE_AUTHORITIES` and PAT issuance all key on `users`. Each would need an exclusion, and a missed one is a privilege bug. |
| c | **Separate `admin_principals` and `admin_credentials` tables, a separate actor namespace, and a separate resource and listener** | **Recommend.** Being structurally absent from membership means no membership check can ever pass for an admin, and no admin check can pass for a user. |

**Schema (unit 1.3, migration `015`):**

- `admin_principals(id ulid PK colon-free, handle, epoch bigint, created_at, disabled_at)`. The audit actor string is `'admin:' || id`.
- `admin_credentials(id, admin_id, credential_id, public_key (COSE), alg, aaguid, sign_count, label, enrolled_at, enrolled_by, disabled_at)`.
- `admin_enrolment_tokens`, `admin_webauthn_challenges` (single use, ≤ 120 s) and `admin_refresh_tokens` (hashed, family id, absolute expiry, used/revoked).
- `principal_subjects.kind` widens to `('user','connector','admin')`. The admin row's `subject` is `admin_principals.id` (the column is CHECKed colon-free, `008_principal_epoch.sql:7`) and its `actor` is `admin:<id>`. `principal_subjects` keeps `kind='user'` for every `users` row; the human/test/agent distinction lives on `users.kind` (D2), so no existing `principal_subjects` row is rewritten.

**Authentication.** WebAuthn/FIDO2 on the YubiKey the operator already uses for promotion.

- `userVerification=required` (PIN) for enrolment, login and destructive operations; touch-only mutations request `discouraged` (so the key does not prompt for a PIN), and control checks UV server-side against the operation class (UV must be set for a destructive class, may be absent otherwise). Attestation format `packed` only, verified to a pinned Yubico root, and the authenticator AAGUID checked against an allow-list. `none` attestation is refused.
- Enrol two keys: daily and safe.
- **RP ID and origin.** The admin process is tunnel-only and has no public TLS name, and a browser only runs WebAuthn in a secure context. The CLI therefore serves the ceremony page itself on `http://localhost:<ephemeral>` (a secure context) and relays challenge and response to control over the tunnel. The RP ID is `localhost`; control accepts only an origin matching `^http://localhost:[0-9]{1,5}$`, and the challenge is always server-issued and single-use. The RP ID and origin rule add nothing against malware on the laptop, and every localhost page shares the RP ID; phishing resistance comes from the tunnel plus the server-issued challenge. Login therefore names the admin (`admin login --handle <h>`) and control sends `allowCredentials` with that admin's enrolled credential ids, so other localhost tooling registered on the key cannot be confused with, or used to enumerate, admin credentials. **[A]:** a native libfido2 path can replace the page later without protocol change, because control checks the same challenge, RP ID hash and origin.
- **OpenPGP card** (the signing applet) is not used for login. Using it would need a bespoke signed-request protocol, and it would couple release-signing key custody with admin login. Keep the two applets' roles separate.
- **GitHub is never a factor** in admin login, recovery or step-up. A GitHub compromise or outage must neither grant admin access nor block it.

**Sessions and step-up.**

| Artifact | TTL | Notes |
|---|---|---|
| Admin access token (`aud=https://api.vuoro.cloud/control/admin`, client `vuoro-cli-admin`) | 5 min | JWT signed by a **dedicated admin signing key** (own kid, mounted only in the admin process, never in public control or the gateway, so a compromised public control process cannot mint admin tokens), `typ=at+jwt`, carries `adm_epoch` and the admin scopes. Issued only by the admin process after a WebAuthn login assertion; there is no authorize redirect, cookie or browser session on the admin plane. |
| Admin refresh token (client `vuoro-cli-admin` only) | 1 h absolute from the login ceremony, rotating, reuse revokes the family | Stored by the CLI in the admin credential namespace. Never extends past the absolute expiry (§7 Q3). |
| **Operation assertion** (slice 2) | single use, ≤ 120 s | A WebAuthn `get()` whose challenge is `H(op_kind ‖ target ‖ params_digest ‖ reason ‖ nonce)`. **Required for every admin mutation.** Destructive operations (retire, restore, transfer, principal disable, principal reclassify, token mint for others, credential enrol/disable) also need UV (PIN) in the same assertion. Reads need none. |

The operation assertion (`authenticatorData`, `clientDataJSON`, signature, credential id) is stored with the audit row. Anyone can verify it offline against the enrolled public key. **What it proves:** the enrolled key was touched (and, with UV, unlocked with its PIN) to sign a challenge that commits to exactly these parameters. **What it does not prove:** that the operator read them. A YubiKey has no display; the parameters are shown by the CLI's loopback page on the laptop, which malware on the laptop could falsify. The out-of-band notification and the teardown hold cover that gap (§2).

**Break-glass and recovery.**

- **Primary:** the second enrolled YubiKey.
- **Break-glass (both keys lost or control's admin tables damaged):** run `kubectl -n vuoro-system create job admin-enrol-<n> --from=cronjob/admin-enrol-break-glass-template` over the WireGuard tunnel with the operator's kubeconfig (a Job's pod template is immutable, so the two modes are two suspended CronJob templates: `admin-enrol-template` for enrolling another key and `admin-enrol-break-glass-template`). The one-shot job:
  - prints a single-use enrolment token, valid 10 minutes, for a new credential;
  - with `--break-glass`: disables every existing admin credential, **bumps `adm_epoch`** (so every outstanding admin access and refresh token dies), and revokes every admin refresh-token family;
  - writes an audit row with `actor_kind=break-glass`.
- **Precondition to verify, not assume:** only the operator can create Jobs in `vuoro-system`. Unit 1.3 records `kubectl auth can-i create jobs -n vuoro-system --as=system:serviceaccount:<ns>:<sa>` for every ServiceAccount in the cluster in its PR (control and the tenant controller must answer `no`); both template CronJobs are `suspend: true`, so it never runs on a schedule. Cluster admin already implies total control, so with that verified this adds no new root.
- **No recovery codes.** They would be a factor weaker than the hardware and would become the real attack target.

**Admin ingress (unit 1.3; §7 Q1).**

- The admin app runs as a **separate process and Deployment**, `vuoro-control-admin` (same image, console script `vuoro-control-admin`, port `VUORO_CLOUD_ADMIN_LISTEN_PORT`, 8443, `proxy_headers=False`), sharing control's database but **not** its signing key: admin tokens are signed by a dedicated admin key mounted only here, and the admin verifier accepts only that key's kid and refuses the AS kid. The public control process (8080), which is the gateway's upstream, has no admin routes. The admin app has no user, cookie, OAuth-authorize or gateway-assertion routes. A separate Deployment gives the admin pod its own NetworkPolicy selector and keeps `access_log.serve` (`access_log.py:101-110`, one app on 8080) unchanged for control.
- The admin pod (label `app.kubernetes.io/name: vuoro-control-admin`) binds 8443 with `hostPort` on `hostIP: 10.44.0.1`, the node's WireGuard address (`CLAUDE.md` "Reaching the live PoC cluster"). The Deployment uses `strategy: Recreate` with one replica: a hostPort on a single node cannot surge, so RollingUpdate would hang every roll; the cost is a brief admin-plane outage on each roll, which only affects the operator. **[A]:** k3s's portmap plugin DNATs without SNAT for non-hairpin traffic, so the admin app sees the operator's tunnel address as the TCP peer. The first deploy records the peer address observed on a live tunnel request. **If it is SNATed, the admin plane fails closed** (every request refused) and the unit is reworked; there is no fallback to a node address or a header.
- Kubelet probes come from the node, not the operator `/32`, so the admin Deployment uses `tcpSocket` probes (or the two health paths are exempt from the source check and return no data); unit 1.3's acceptance includes a second image roll of the admin Deployment completing under `Recreate`.
- NetworkPolicy `allow-admin-tunnel` admits TCP 8443 on `vuoro-control-admin` only from the enrolled operator peer addresses as `/32`s (today `10.44.0.2/32`); there is no pod or namespace selector, and the policy does not list the node's own tunnel address `10.44.0.1` (`terraform/environments/poc/cloud-init.yaml.tftpl:23`). k3s NetworkPolicy admits node-local traffic regardless, so it is the app's source check that refuses the node address. A future appservice-cluster peer gets its own `/32` in slice 6, not a range.
- Control's admin app refuses any request whose TCP peer (`request.client.host`, uvicorn runs with `proxy_headers=False`, `access_log.py:106`) is not one of `VUORO_CLOUD_ADMIN_SOURCE_CIDRS` (default `10.44.0.2/32`; a configured network that contains `10.44.0.1` or a loopback address is refused at startup), and any request carrying `cf-connecting-ip` or `cf-ray`. No header is ever trusted for source identity. This also refuses `kubectl port-forward` to the admin pod (peer is loopback) and connections originating on the node.
- **Gateway deny (unit 1.2):** the gateway refuses `/api/control/v1/admin/*` with 404 before `forward_to_control`, matching on normalised path segments (case-folded, empty segments collapsed, so `/api/control/v1//admin/x` is caught; percent-encoded and dot-segment variants are already rejected by `_unsafe_path`), and counts it as `unexpected_route`. The Cloudflare edge rule script (`scripts/apply-cloudflare-edge-rules.py:91`, which already guards `/api/control/v1/operator/`) also blocks `/api/control/v1/admin/` unconditionally. This is defence in depth: the public control process has no admin routes either.
- **Talos:** no claim (plan item 12). The tunnel address and port mapping are k3s-PoC facts.

**Admin is not a member.**

- Admin routes use an `admin()` dependency: bearer, `aud=/control/admin`, `typ=at+jwt`, admin subject, principal active, `adm_epoch` matches, scope. It never calls `administrative_membership`.
- The admin plane operates *on* workspaces (lifecycle, principals, backups, tokens). It does **not** read tenant work content. It has no route into the runtime's work data. When the operator wants to read or act on work in kotona, they do it as their user identity.
- Every admin action on a workspace is audited as the admin principal. It is also visible to that workspace's members (§7 Q7): the audit row carries the `workspace_id`, and unit 2.2 adds a view of admin rows readable by every active member (today's audit view, `control.py:3425`, is owner/admin only).

**The static `operator()` token** is retired by unit **R** (§5), which depends on slices 2 and 3 only: slice 2 gives every operator route an admin twin (drain, tenant migration plan/start/retry/status, epoch bump, invitations, invite requests, service controls, analytics, backup observations, rollout status), both paths serve for one generation, and R removes `operator()` and its routes. Slice 7 (gated on cred-broker) is not on this path.

### D2. Test principals

**Model.**

- Add `kind` to `users`: `human | test | agent`. Agent principals are introduced in D3. Existing rows default to `human`.
- `principal_subjects.kind` is **not** widened for these: it stays `user` for every `users` row (see D1), so the epoch machinery is unchanged and no `principal_subjects` row is rewritten.
- The namespace rule applies to `users.external_subject`, which is the actor string. The opaque `users.id` stays colon-free as today.

Enforced by database constraint, not by application code (generation B, below):

```
CHECK ( (kind='human' AND external_subject ~ '^github:[0-9]+$')
     OR (kind='test'  AND external_subject ~ '^test:[0-9A-HJKMNP-TV-Z]{26}$')
     OR (kind='agent' AND external_subject ~ '^agent:[0-9A-HJKMNP-TV-Z]{26}$') )
test and agent rows: expires_at NOT NULL, created_by_admin NOT NULL (FK admin_principals)
workspaces.is_test boolean NOT NULL DEFAULT false
membership trigger: kind='test' ⇒ workspace.is_test;  workspace.is_test ⇒ member.kind IN ('test','agent')
```

- Only the GitHub OAuth callback (`oauth.py:94`) inserts `kind='human'`. Test principals are created only through `admin test-principal create` (slice 4). How the blocker-12 trial seeded its owner is **[U]**; `IMPLEMENTATION-STATUS.md:265` records only that the canary ran.
- Invitation redemption's `startswith("github:")` check (`control.py:1896`) is tightened to the same pattern in generation A (application check; the CHECK follows in B).

**Migration in two generations (migrations are forward-only).**

1. **Generation A (unit 2.1, migration `018`):** add `users.kind` (default `human`), `legacy_subject`, `expires_at`, `created_by_admin`, `workspaces.is_test`, **without** the CHECK or the membership trigger. Ship `admin principal reclassify` and `admin principal disable` (unit 2.2).
2. **Production step (operator, through the admin API):** run slice 0's classification report against production (read-only), then reclassify each violator it lists (blocker12's owner) with `admin principal reclassify … --as test` (touch + PIN), and re-run the report until it lists no pattern violator.
3. **Generation B (unit 2.4, migration `020`):** add the CHECK, the NOT NULLs for test/agent rows and the membership trigger. The migration first runs the violator query and aborts with the offending ids if any row would fail, so a missed reclassify fails the migrate Job rather than half-applying.

**Reclassify is narrow.** It exists to repair pattern violators, not to relabel people.

- Only a principal whose `external_subject` fails the pattern for its current kind can be reclassified. A subject matching `^github:[0-9]+$` is refused (`reclassify-valid-human`), whatever the reason text says.
- Target kind `test` only. It sets `legacy_subject`, a fresh `test:<ulid>` subject, `expires_at` (≤ 30 days; `now` allowed), and `created_by_admin`, and in the same transaction **explicitly revokes** every credential the principal holds: OAuth grants and refresh tokens, PATs, web sessions, and connectors it enrolled (an epoch bump alone does not revoke them at `332faa4`: refresh and PAT checks stamp but do not compare the epoch, and sessions are keyed by user id). It also bumps the epoch and updates `principal_subjects.actor` to the new subject (the `008` trigger forbids a subject change, not an actor change).
- Touch + PIN; it is in the D4 command table and the destructive-operations list.
- Workspaces owned by the principal become `is_test` **but keep the human teardown hold**: the operation records `prior_kind`, and retire honours the 24 h hold and takes the dump for any workspace whose owner was reclassified from a prior kind of `human` (every reclassify does, today). A reclassify therefore never shortens the path to teardown.

**Lifecycle.**

- `vuoro-cli admin test-principal create --ttl 7d [--workspace new|<test ws>]`. The default TTL is 7 days and the maximum 30.
- The **reaper** (slice 4) runs inside control as a scheduled task with actor `policy:test-expiry@v1`. When a principal expires, it retires that principal's test workspaces through the same retire operation (D5), and then disables the principal. It calls retire, so it inherits retire's rules: the dump is skipped only for a test workspace whose owner was never reclassified from `human` and that was not created with `--keep-backup`.
- The reaper is platform lifecycle, not Vuoro intent handling. TS-1's "never expires" rule is about `EffectIntent` and does not apply here.

**MCP gateway tokens for test principals.** Two needs, two mechanisms.

- **(a) Gateway and tool tests from CI or the perimeter:**
  - `vuoro-cli admin token mint --principal test:… --client vuoro-test-harness --aud /mcp --scope vuoro:work.read --ttl 15m`;
  - client `vuoro-test-harness` is new and restricted to test principals;
  - no refresh token.
- **(b) Exercising the real Claude connector path:**
  - The admin mints a **test-login code**: single use, 15-minute TTL, bound to one test principal, shown once. It carries 128 bits from the CSPRNG (26 Crockford base32 characters); control stores only its keyed hash.
  - The AS authorization page gets a "test login" method, next to GitHub, that accepts only such codes and only for `kind='test'`. Attempts are limited by the existing pre-auth limiter per connecting IP, plus a global budget of 20 failed code attempts per hour; exceeding it disables test login until an admin re-enables it (audited). A failed attempt never reveals whether a code exists. The budget is an unauthenticated off-switch for test login; that is acceptable because test login exists only for testing.
  - The operator adds the connector in Claude and uses the code at the consent screen. The full authorize → code → token → refresh flow then runs with a test principal as resource owner.
  - Tokens carry `tst=true`. The gateway rejects `tst=true` on a non-test workspace as defence in depth; the constraint already makes it impossible.

**Recommend both.** (b) is the only way to test claude-connector end to end without a second GitHub account. (a) keeps CI off claude-connector.

### D3. Token minting

**What the admin can mint.**

| Subject | Client | Audience and scopes | Refresh | TTL | Revocation |
|---|---|---|---|---|---|
| test principal | `vuoro-test-harness` | `/mcp`, granted work-plane scopes | trusted-side harness only | ≤ min(24 h, principal expiry) | principal epoch bump; expiry |
| test principal | `claude-connector` | via test-login code only (D2b) | normal connector rules | normal | grant revoke; epoch; expiry |
| agent principal | `vuoro-agent-delegate` (cred-broker) | `/mcp`; `vuoro:work.read` and `vuoro:evidence.record` (granted today); **never** `vuoro:effect.propose` or `vuoro:work.claim` while reserved | **never** | ≤ 15 min | agent epoch; delegation disable; grant revoke |
| human principal | — | **not mintable by admin** | — | — | — |
| admin principal | — | **never minted**, only obtained by WebAuthn login | — | — | — |

- **No impersonation.** An admin minting tokens *as* the operator's user identity, or any human, would undo the separation. Humans mint their own PATs through the user plane (D4).
- **Epochs.** The principal epoch bump exists today (`control.py:1331`, monotonic by trigger in `migrations/008_principal_epoch.sql:15-30`). Add epochs per agent principal, per delegation and per admin principal.
- **Reserved authorities are refused by name.** A delegation whose ceiling names `vuoro:effect.propose` or `vuoro:work.claim` is refused when it is set, and a mint request naming either is refused, independently of `oauth_scopes.RESERVED_SCOPES`. Removing that refusal is a separate change that must show both reserved-authority conditions (§1) hold.

**Agent principals** (`agent:<ulid>`, §7 Q9: one per perimeter host):

- created by an admin and bound to one human sponsor;
- members of named workspaces with role ≤ `member`, never `owner`/`admin`, enforced by a trigger;
- given an `expires_at`.

They exist so that work done by a delegate is attributable to the delegate rather than smeared onto the operator's user identity.

**The operator's idea: agents obtain minted tokens through cred-broker in the appservice cluster.**

| Reading | Verdict |
|---|---|
| Cloud sessions or Routines authenticate to cred-broker and receive a Vuoro token | **Out of bounds.** A cloud session has no workload identity that cred-broker can verify. Whatever secret it would present is itself a CLI credential, which decision 4 forbids and which H8 says cred-broker cannot verify anyway. It would also create a second, unaudited path around the claude-connector grant. Cloud sessions keep using claude-connector OAuth: the Claude-held grant, TS-16 surface only. |
| cred-broker returns an admin token, a control-plane token, or any refresh token to a workload | **Out of bounds.** Control or admin authority in a workload violates TS-16's trusted/untrusted split. A refresh token in a workload is a long-lived credential in effect. |
| cred-broker *proxies* calls with a token it holds (bearer forwarding) | **Out of bounds (H2).** |
| **Perimeter workloads** (homelab Claude Code or Codex sessions, CI in the appservice cluster) authenticate to cred-broker over mTLS with server-side sessions. cred-broker authorizes the capability `vuoro.token/work` for (subject, session, host, canonical repo) under an operator-authored policy, and obtains a short-lived access token for an agent principal from control. | **Allowed, gated.** This is the safe shape; detail follows. |

**Safe shape.**

1. **Operator authors two policies, one on each side:**
   - **cred-broker policy (Git-reviewed):** `(host, subject, repo) → capability vuoro.token/work → agent principal agent:X, workspace W`.
   - **control delegation (set with an admin mutation, audited):** client `vuoro-agent-delegate` may mint for `agent:X` with scope ceiling ⊆ {`vuoro:work.read`, `vuoro:evidence.record`}, audience `/mcp`, workspaces `{W}`, repos `{R…}`, TTL ceiling 15 min, rate N/h.
2. **cred-broker authenticates to control as itself.**
   - It uses `private_key_jwt` (RFC 7523) with its key in cred-broker's protected key substrate (a README production gate).
   - The request is RFC 8693 token exchange with `requested_subject=agent:X`, `resource=/mcp`, the narrowed scope and repo set, `run_id` once E2 exists, and `actor_token` = a one-use cred-broker decision proof. The proof is a signed JWT carrying `receipt_id`, request digest, `jti` and a 60-second expiry, in the shape of item 6.
3. **Control intersects the request with the delegation.** It issues an access token with `act={sub: client vuoro-agent-delegate}`, `run_id`, `repo_ids`, `jti` and a TTL of 15 minutes or less. It never issues a refresh token. Minting is refused if any part of the request exceeds the ceiling.
4. **cred-broker delivers the token** to the authenticated perimeter session, never to disk config. Its receipt records the `jti`, never the value. Control's audit records the mint with delegation id and version.
5. **The token is used directly against the gateway** by the workload. Internal hops use the gateway's one-use assertion as today.

**Why this passes the constraints.**

- **TS-16:** a minted work-plane token confers read and evidence recording at most. It cannot propose, claim or apply: propose and claim are reserved and refused by name, and no apply exists.
- **C1:** no scope in the ceiling performs an effect in-call.
- **H2:** nothing forwards a bearer; the proof is one-use and body-bound.
- **H8:** step 2 needs cred-broker's mTLS workload auth and key substrate, so this is the last slice and gated on item 7.
- **Decision 4:** cloud sessions are excluded by construction. Only mTLS-enrolled perimeter hosts can ask.

**Until item 7 closes:** the operator mints agent-principal tokens interactively with `vuoro-cli admin token mint --principal agent:X --ttl 15m` (touch plus PIN) and hands them to a perimeter session. This is the same authority with a human in the loop, under the same reserved-authority refusal.

### D4. `vuoro-cli`

**Face (b): the operator's CLI.**

| Command group | Plane | Scope | Step-up | Slice |
|---|---|---|---|---|
| `login`, `logout`, `whoami` | user | — | — | 3 |
| `workspace list/status`, `workspace roll --wait` (own workspaces) | user (membership-checked) | `vuoro:control.workspace.read` / `.write` | — | 3 |
| `repo bind/list` | user | `vuoro:control.workspace.write` / `.read` | — | 3 |
| `token pat create/list/revoke` (**transitional**, #255 Q1; no new long-lived credential type), `grant list/revoke` (own) | user | `vuoro:control.token.manage` | — | 3 |
| `admin enrol`, `admin login`, `admin logout`, `admin whoami` | admin | — | WebAuthn | 1 |
| `admin workspace list/show`, `admin audit tail/verify` | admin | `vuoro:admin.read`, `vuoro:admin.audit.read` | — | 1 |
| `admin backup list`, `admin rollout status`, `admin invitations list`, `admin service-controls show`, `admin analytics`, `admin migration status` (read twins of operator routes) | admin | `vuoro:admin.read` | — | 2 |
| `admin workspace create/roll/drain`, `admin migration plan/start/retry` | admin | `vuoro:admin.workspace.lifecycle` | touch | 2 |
| `admin workspace retire/transfer`, `admin principal disable`, `admin principal reclassify` | admin | `vuoro:admin.workspace.lifecycle` / `vuoro:admin.principal` | touch + PIN | 2 |
| `admin principal epoch-bump`, `admin invitations create`, `admin invite-requests update`, `admin service-controls set` (write twins of operator routes) | admin | `vuoro:admin.principal` / `vuoro:admin.workspace.lifecycle` | touch (epoch bump: touch + PIN, a credential change) | 2 |
| `admin test-principal create/retire`, `admin test-login-code` | admin | `vuoro:admin.principal` | touch | 4 |
| `admin token mint`, `admin delegation set/disable` | admin | `vuoro:admin.token.mint` | touch + PIN | 4 (test), 7 (agent) |
| `admin backup create`, `admin restore-drill run` | admin | `vuoro:admin.backup` | touch | 5 |
| `admin restore` | admin | `vuoro:admin.restore` | touch + PIN | 5 |
| intent acceptance (TS-16 reconciler, once E3 exists) | **protected horizon only**: `credctl accept <intent-digest>` on the workstation (#255 Q4), not `vuoro-cli` and not the vuoro.cloud admin plane | owned by the E3 lifecycle spec (item 4) | the acceptance binds the canonical intent digest (§8), never the intent id | — |

**Protocol.**

- **User face, client `vuoro-cli`:** OAuth 2.1 authorization code with PKCE and a loopback redirect (`http://127.0.0.1:<ephemeral>/cb`, RFC 8252), `resource=https://api.vuoro.cloud/control`, GitHub login through the existing AS. Loopback-only redirects mean a cloud session cannot complete the flow for someone else.
- **Admin face, client `vuoro-cli-admin`:** no authorize redirect. Over the tunnel, the CLI asks the admin process for a login challenge, serves the WebAuthn page on `http://localhost:<ephemeral>` (D1, RP ID), and posts the assertion back; control verifies it and returns a 5-minute admin access token plus a rotating refresh token (1 h absolute). A cloud session has no tunnel and no YubiKey.
- Operation assertions (slice 2) use the same loopback page: the CLI fetches the operation challenge, the page renders the operation, the operator touches the key.

**Face (a): the trusted-side service.**

- **Runs in** the appservice cluster, in namespace `vuoro-ops`, next to but separate from cred-broker. **[U]:** this assumes the appservice cluster reaches control over the operator tunnel CIDR; slice 6 verifies it before relying on it.
- **Jobs:**
  1. mirror and verify the audit hash chain off-cluster (D7);
  2. run scheduled restore drills and backup-freshness checks (D6);
  3. ~~later, evaluate the TS-16 auto-accept policy~~ removed in revision 7: acceptance and auto-accept are protected-horizon (credctl) only (§8 C5).
- **Authentication:** client `vuoro-cli-service` using the RFC 7523 JWT-bearer grant.
  - **Recommended:** a projected ServiceAccount token from the appservice cluster's issuer. Control pins that issuer's JWKS in Git-reviewed config.
  - **Fallback:** `private_key_jwt` with a SOPS-held key.
  - Access tokens last 5 minutes, with no refresh token.
- **Scopes:** `vuoro:admin.read`, `vuoro:admin.audit.read`, `vuoro:admin.backup` (on-demand plus drill namespace only). It can never produce an operation assertion, so no destructive route is reachable from it by construction.

**Scopes and client restrictions.** `oauth_scopes.py` already has per-client restriction with hard refusal of explicit requests (`SCOPE_CLIENT_RESTRICTIONS`, `evaluate_scopes`, `:49-51`, `:137-177`). This design adds:

- **Namespace refusal on the `/mcp` path.** Any `vuoro:control.*` or `vuoro:admin.*` scope in an `/oauth/authorize` or `/oauth/token` request for the `/mcp` resource is `invalid_scope`, for every client, audited as `oauth.scope.rejected_requested`. These scopes never enter `SCOPE_TO_AUTHORITIES` (which is the `/mcp` authority table), so no default grant can include them.
- **Admin scopes** (`vuoro:admin.read`, `vuoro:admin.audit.read` in slice 1; `.workspace.lifecycle`, `.principal`, `.token.mint`, `.backup`, `.restore` later) live in a separate `ADMIN_SCOPES` registry and are issued only by the admin listener, only to client `vuoro-cli-admin` (and a subset to `vuoro-cli-service` in slice 6), and only when the authenticated subject is an active admin principal.
- **Control scopes** (`vuoro:control.workspace.read`, `.workspace.write`, `vuoro:control.token.manage`) live in a `CONTROL_SCOPES` registry, are issued only on the `/control` resource, only to client `vuoro-cli`, and only for human principals (checked at authorize and at every refresh). Until unit 2.1 adds `users.kind`, "human" means the subject matches `^github:[0-9]+$`; 2.1 switches the check to `kind='human'` plus the pattern.
- **Refusal by principal kind:** the AS checks the principal kind as well as the client: admin scopes for admin principals only, control scopes for human principals only.
- **Reserved `/mcp` authorities stay reserved:** nothing here edits `RESERVED_SCOPES`.
- **A single umbrella `vuoro:control.admin` is rejected.** Narrow scopes let the service hold observe and backup without lifecycle.

**Bearer path next to the browser session.**

- **Keep every existing cookie route as is.** Cookie plus CSRF plus `administrative_membership`, `Depends(browser)` (`control.py:268-300`, `:3270-3283`).
- **Add separate routers:**
  - `/api/control/v1/cli/...` on the public control process uses `Depends(control_bearer(scope))`: bearer only, `aud=/control`, human subject, principal epoch current, `administrative_membership(workspace, token.sub)` still required.
  - `/api/control/v1/admin/...` exists only in the admin process and uses `Depends(admin(scope))` (slice 1) and `Depends(admin(scope, op_assertion=…))` (slice 2).
  - The handler bodies share service functions with the browser routes. Authentication is the only fork.
- **Why CSRF is not weakened.** CSRF exists because cookies are ambient. The bearer routers:
  - ignore and **reject** any request that also carries a session cookie (400), so a browser can never reach them ambiently;
  - send no CORS allow-origin;
  - accept only `Authorization: Bearer` with `typ=at+jwt`.
- Gateway assertions and PATs minted for `/mcp` are refused on both routers by audience.

**Packaging (§7 Q6).**

| Option | Verdict |
|---|---|
| Subcommands in vuoro-client (bayleafwalker/vuoro) | **Reject.** It would put vuoro.cloud control/admin surface into the product client that agents and sprintctl import. Admin credential handling would then share a process and profile store with agent tooling. vuoro-client also speaks the runtime protocol, not the control API. |
| **Package `vuoro_cloud_cli` (command `vuoro-cli`) in vuoro-cloud**, with its own small httpx client and User-Agent `vuoro-cli/<version>` | **Recommend.** The control API and its client ship and test together; CI covers it with the existing `tests/` and ruff targets. It does not import vuoro-client. Credentials live in `$XDG_CONFIG_HOME/vuoro-cli/` in two separate mode-0600 files (user, admin) that vuoro-client never reads; an OS keyring backend can replace the files later behind the same interface. `admin` is never a default profile. The service face (slice 6) is the same package with a `serve` entry point and its own image. A separate distribution can be split out later without changing the command. |

### D5. Workspace lifecycle as audited operations

**Operation record (unit 2.1, migration `019`).** Each lifecycle action is an `operations` row:

- `id`, `kind`, `target`, `actor{kind,id}`;
- `credential{client_id, token_jti, webauthn_cred_id, assertion_id}`;
- `reason` (required for admin, ≥ 10 characters);
- `params_digest`, `idempotency_key`;
- `state requested→running→succeeded|failed|cancelled`;
- `steps[]` with timestamps.

Control executes operations and the tenant controller performs the cluster steps, as rollouts do today (outbox claim and reconcile, `controller.py:79-200`). This is platform lifecycle. It is **not** an effects state machine, so item 4 ("no temporary Vuoro execution state machine") does not apply to it.

**Destructive operations** (touch + PIN): retire, restore, transfer, principal disable, principal reclassify, token mint for others, credential enrol/disable, delegation set. Auto-accept policy is not an admin-plane operation: it belongs to the protected horizon (credctl, §8 C5).

| Operation | Actor | Steps | Guards |
|---|---|---|---|
| **create / onboard** | admin (or a user via invitation, as today) | create workspace row → owner membership → desired_state READY → controller provisions | Owner must be `kind=human` with a valid subject, or `test` for `is_test`. Workspace creation and owner membership happen in one transaction, so a workspace with no owner cannot exist. |
| **repo bind** | user (owner/admin member) | today's browser-only `POST …/projects/current/repositories` (`control.py:2324-2390`, inserts `repositories(git_remote, commit_sha)`) gets a bearer twin; provider reachability check **[A]** | Effects allowlists stay Git-reviewed (trusted-service design §T4). A CLI binding never widens effects. |
| **roll** | user (own) or admin | PATCH READY → watch `vuoro-migrate-<gen>` → Deployment ready; from slice 5, a pre-roll backup first when the target image's migration set changes the schema | Migrations are forward-only (the controller's migrate Job precedes the Deployment, `controller.py:200-246`). Until slice 5, `roll --wait` prints the latest completed backup as the restore point before rolling and exits non-zero on migrate failure. |
| **drain** | admin | existing operator drain (`control.py:1369-1403`, `READY → DRAINING`) and tenant migration plan/start (`control.py:1405+`), given admin twins | touch |
| **retire** | admin | Builds on today's `DELETED → RETAINED` path (`controller.py:145-168`), which scales to 0 and stops there. `retire --plan` prints plan and digest → `retire --apply <digest>` (touch + PIN) → per-workspace logical dump, age-encrypted (D6), **unless** the workspace is `is_test`, its owner was never reclassified from `human`, and `--keep-backup` was not given → drain → revoke all grants and PATs scoped to the workspace → scale to zero → **24 h hold** (unless `is_test` with no reclassified-human owner; cancellable) → delete namespace, DB, roles, secrets → workspace row becomes a `RETIRED` tombstone (new `workspace_state` value and tombstone columns, migration `019`; id never reused) → audit | Plan digest binds the assertion. **When a dump is taken**, teardown refuses unless it is verified (restorable header and digest recorded). A cluster base backup newer than the drain with `status=completed` is required in every case. |
| **transfer ownership** | admin | add new owner → remove or downgrade old owner, in one transaction | touch + PIN. The new owner must be able to authenticate. |
| **principal disable** | admin | epoch bump → explicit revocation of grants, refresh tokens, PATs, web sessions and enrolled connectors (the epoch bump alone revokes none of them today) → for each workspace where the principal is the sole owner, **refuse** unless `--disposition <ws>=transfer:<p>|retire` is given for each | touch + PIN. Makes new orphans impossible through the admin path. |
| **principal reclassify** | admin | pattern-violator check → `kind=test`, `legacy_subject`, new `test:<ulid>`, `expires_at`, `created_by_admin` → owned workspaces `is_test`, `prior_kind` recorded | touch + PIN. Only subjects that fail their kind's pattern; never a valid `github:<digits>`. Keeps the teardown hold and dump for workspaces whose owner's prior kind was `human` (D2). |
| **orphan recovery** | admin | `admin workspace list --orphaned` (owner kind invalid, disabled, expired, or no authenticable owner) → transfer or retire | — |

**Invariant, checked by a trigger plus a nightly report:** every non-retired workspace has at least one owner who is (a) human with a valid subject and not disabled, or (b) test, not expired, in a test workspace. Because the admin plane never needs membership, a violated invariant is always recoverable.

**Worked example: `blocker12-canary`.** The identifiers, owner subject and schema version are live data, **[U]**. Until step 2 it stays parked (§7 Q2); nothing here bypasses membership.

1. **Slice 0 report** (read-only, restore-drill copy first, then production). `01M14W25EYSZ…` fails the subject pattern, and `01M14W25EYKC…` has no authenticable owner. Also check whether that principal owns or belongs to anything else.
2. **After generation A (units 2.1-2.2 deployed):**

   ```
   vuoro-cli admin principal reclassify 01M14W25EYSZ… --as test --expire now \
       --reason "synthetic github: subject seeded by 2026-08-29 test run; blocker12 orphan"
   ```

   Touch + PIN. The subject becomes `test:<ulid>`, `legacy_subject` is kept, `prior_kind=human` is recorded, and the workspace is marked `is_test`. The report is re-run and lists no pattern violator.
3. `vuoro-cli admin workspace show 01M14W25EYKC…` shows the runtime image, work schema 12, and the last backup.
4. `vuoro-cli admin workspace retire 01M14W25EYKC… --keep-backup 30d --plan --reason "orphaned test canary, schema 12, no authenticable owner"` prints the plan digest.
5. `… --apply <digest>` (touch + PIN):
   1. logical dump, kept 30 days as evidence, verified;
   2. drain;
   3. revoke;
   4. scale to zero;
   5. **24 h hold**, because the owner's prior kind was `human`; the operator is notified and can cancel;
   6. teardown and tombstone.
6. `vuoro-cli admin principal disable <principal> --reason "blocker12 orphan owner, workspace retired"` (touch + PIN). This is explicit in slice 2; the reaper (slice 4) is not needed.
7. **Generation B** (unit 2.4) lands: the CHECK makes a repeat fail at insert time.
8. **Root cause.** Find the 2026-08-29 seeding test and move it to `admin test-principal create` (slice 4).

**Interim.** Two things are true today, verified at `332faa4`:

- the static operator token can already drain the canary and run a tenant migration on it (`control.py:1369-1650`), so the schema-12 lag can be fixed without its owner;
- no route can retire it.

The canary stays parked (§7 Q2), unless the stale schema blocks a fleet-wide roll. In that case, use the existing operator drain and migration routes, with the reason written into the handoff, because the static token records no reason.

### D6. Encrypted backups

**Facts:**

- **Verified** (`vuoro-cloud:platform/cnpg/repository.yaml:1-43`):
  - one CNPG `Cluster`, `vuoro-postgres`, in `vuoro-data`;
  - barman-cloud writes to `s3://vuoro-cloud-poc-cnpg-backups/vuoro-cloud-poc` on **Hetzner Object Storage** (`hel1.your-objectstorage.com`);
  - `retentionPolicy: 14d`, gzip, a daily `ScheduledBackup` at 02:15;
  - **no `encryption` setting on `wal` or `data`.**
- **[A]:** tenant databases live in the same cluster. It is the only `Cluster` manifest, and the controller provisions through `tenant_database_admin_url` (`config.py:27`), whose value is SOPS-encrypted. If so, a CNPG backup is **cluster-wide**: restoring one workspace means a point-in-time recovery of the whole cluster into a new cluster, followed by extracting that workspace's database. That is why retire (D5) takes a **per-workspace logical dump** as well.
- **[U]:** on-demand Backup CRs are created with kubectl over the tunnel (operator practice).

**Encryption options.**

| | Mechanism | Protects against | Verdict |
|---|---|---|---|
| a | Provider server-side encryption (barman-cloud `encryption: AES256` / `aws:kms` **[A]**; whether Hetzner Object Storage honours SSE headers is **[A]**, unverified) | Provider media theft only. Anyone with bucket credentials reads plaintext. | Turn on if supported; it costs nothing, but it is **not** the control. |
| b | Client-side encryption in the primary backup path | Bucket-credential or provider compromise | **[A]:** barman-cloud, as CNPG drives it, has no client-side encryption. It would mean a CNPG plugin or a switch away from barman. Defer. |
| c | **Immutable primary plus client-side-encrypted offsite copy** | Credential compromise (ciphertext only in the copy), cluster compromise destroying backups (object lock), provider loss (second provider) | **Recommend.** |

**Recommended shape.**

- **Primary bucket:**
  - SSE if available;
  - versioning plus object lock (compliance mode), with retention ≥ the 14-day barman retention plus margin, e.g. 21 days. Hetzner support for object lock and delete-denying key policies is **[A]** and has to be probed first.
  - cluster credentials that can put and get but **not** delete. Lifecycle expiry does the deleting.

  A compromised cluster can then read backups (it can read the database anyway) but cannot destroy them.
- **Offsite copy (§7 Q4: a second provider):**
  - the `vuoro-ops` service copies each completed base backup and WAL segment;
  - it encrypts with `age` to a recipient whose identity is held on the operator's YubiKey (`age-plugin-yubikey`) **[A]**, plus a paper-escrowed second identity in the safe;
  - it writes to a second provider's bucket.

  The service holds only the **public** recipient.
- **Key custody:**
  - operator hardware for the offsite copy;
  - no KMS, because none exists in the estate and adding one adds a root.
  - If a KMS is adopted later, it replaces SSE in (a) and nothing else.

**Restore authority.**

- `vuoro-cli admin restore --workspace|--cluster --to <new target> --point <time|backup>` needs touch + PIN.
- It always restores to a **new** cluster or database. Cutover is a separate `roll`-class operation with its own assertion. There is no in-place overwrite.
- Restore from the offsite copy is attended: the operator decrypts with the YubiKey.
- kubectl restore is break-glass only and is audited as such when observed (the service watches for Backup and Cluster CRs not created by control).

**Drills.**

- **Monthly automated:** the service restores the latest primary backup into namespace `vuoro-restore-drill` and runs schema-version, row-count and `pg_amcheck` checks. The evidence goes to the audit trail.
- **Quarterly attended:** an offsite-copy restore with YubiKey decrypt.
- `admin backup list` shows the last successful drill. The CLI warns after 35 days with no success.

**Existing scripts.** `scripts/restore_drill.py` and `scripts/record_backup_observation.py` are today's drill and observation path; slice 5 replaces them (the latter also depends on the operator token, unit R).

**On-demand trigger.** `vuoro-cli admin backup create` (touch) causes control to create the Backup CR. This needs new RBAC on control's ServiceAccount: create `backups.postgresql.cnpg.io` in the data namespace only **[U]**. Pre-roll and pre-retire backups use the same path, and kubectl becomes break-glass.

### D7. Audit and non-repudiation

- **Store:** extend `audit_events` (unit 1.1, migration `014`).
  - Today it is `(id, workspace_id, actor text, action, target, request_id, details jsonb, created_at)` with no integrity protection (`migrations/001_control.sql:173-182`), written by control and the gateway.
  - The static-token routes write `actor="operator"` (`control.py:242`).
  - Add the columns below. Existing writers are unchanged: they leave the new columns null.
- **One global chain, serialized.** A `BEFORE INSERT` trigger (`SECURITY DEFINER`, fixed `search_path`) locks the single row of `audit_chain_head` `FOR UPDATE`, assigns `chain_seq = head + 1`, builds `chain_payload` (the row's fields as a canonical JSON text, timestamps in UTC microseconds) and sets `row_hash = sha256(prev_hash ‖ '\n' ‖ chain_payload)`. Concurrent inserts from control and the gateway therefore serialize on the head row and cannot fork the chain. The migration chains existing rows in `(created_at, id)` order from a fixed genesis hash. Workspace views filter the global chain; a per-workspace chain is not needed, because verification is over the whole table.
- **Insert only, in two layers.**
  1. **Trigger (unit 1.1):** `BEFORE UPDATE OR DELETE` (row) and `BEFORE TRUNCATE` (statement) triggers raise on `audit_events` and `audit_chain_head` (the head row can only move forward through the insert trigger). This stops any application path and any SQL issued by the runtime role that does not first `ALTER TABLE … DISABLE TRIGGER`.
  2. **Role split (unit 1.5):** the runtime role `vuoro_control` is today the owner of the whole database and of every object (`platform/cnpg/repository.yaml:13-17`), and an owner can disable triggers. Control, the gateway and the tenant controller all open the control database, very likely with the same role (the three encrypted URLs have the same length; unconfirmed without decrypting; the controller opens it at `controller.py:371`). Target roles:
     - `vuoro_control_owner`: owns every object; used only by the migration Job. Declared in CNPG `spec.managed.roles` and set as the `bootstrap.initdb.owner` for new clusters, so a fresh cluster or an initdb restore starts split. (CNPG keeps role passwords in `vuoro-data`; the app connection-string secrets in `vuoro-system` are separate SOPS files, as today.)
     - `vuoro_control` (public control process), `vuoro_gateway`, `vuoro_controller` (tenant controller) and `vuoro_control_admin` (admin process): each gets exactly the privileges in a **per-role grant matrix** that unit 1.5 derives from the code (every table each process reads or writes; the gateway alone touches about nine tables), with `SELECT, INSERT` only on `audit_events` for every runtime role, and **no** privilege on `admin_*` tables for any role but `vuoro_control_admin`. `vuoro_control_admin` gets exactly what slices 1-2 use, including `UPDATE` on `oauth_grants`, `api_tokens` and `web_sessions` for revocation.
     - No default privileges. Every migration that creates a table **or adds a new access path to an existing table** extends the matrix in the same migration; a CI test compares the matrix with `information_schema.role_table_grants` after migrating, and the app test suites connect as the matching runtime role (not the superuser that `tests/conftest.py:66-83` uses today), so a missing grant fails CI instead of production.
     - The break-glass enrol Job runs as `vuoro_control_admin`.
     The in-place PoC upgrade moves ownership **last**, so no process loses access at any point: (i) CNPG managed roles are declared in Git and reconciled (roles exist, nothing uses them); (ii) while `vuoro_control` still owns everything, the operator (CNPG superuser, over the tunnel) grants `vuoro_gateway`, `vuoro_controller` and `vuoro_control_admin` their matrix rows, including sequence privileges; (iii) the gateway, tenant controller and admin Deployments switch to their own secrets, one generation, and run on their own roles while control and the migration Job still use `vuoro_control`; (iv) in one superuser transaction with `SET lock_timeout = '5s'` (retried off-peak; `REASSIGN OWNED` takes exclusive locks until commit): `REASSIGN OWNED BY vuoro_control TO vuoro_control_owner` (which also moves the database owner), then `vuoro_control`'s own matrix rows including schema `USAGE` and sequence privileges; (v) immediately after, with no promotion in between, the migration Job switches to `vuoro-control-migrate` (the owner role), since as `vuoro_control` it would now fail at `CREATE TABLE IF NOT EXISTS schema_migrations` (`scripts/migrate.py:12`); (vi) migration `016` re-applies the matrix idempotently and asserts it (it fails if a runtime role owns any object, if a non-admin role can write an `admin_*` table, or if any runtime role can UPDATE `audit_events`), and where the roles do not exist it fails naming them. Steps (iv)-(v) are the only coupled pair; a CNPG dry run (`kubectl apply --dry-run=server`) of the managed-roles change and a check of the bootstrap secret's username (`vuoro_control`) precede step (i). Until 1.5 lands, the insert-only property holds against application bugs and injected DML but **not** against a compromised control role; the hash chain plus the off-cluster mirror (slice 6) are what detect a rewrite.
- **Row (new columns):**
  - `actor_kind` (admin, user, test, agent, service, policy, break-glass, anonymous, operator, connector), `actor_id`;
  - `credential` (client_id, token jti, webauthn credential id, operation-assertion blob);
  - `reason`, `operation_id`, `params_digest`, `outcome`, `source_ip`;
  - `chain_seq`, `prev_hash`, `row_hash`, `chain_payload`.
  - Secret values are never recorded. A strict output schema applies (item 10).
- **Verification.** `audit_chain.verify(rows)` recomputes each `row_hash` byte-exactly from `prev_hash` and the stored `chain_payload`, checks `chain_seq` is gapless, and checks the payload's fields equal the row's columns. `admin audit verify` runs it server-side (slice 1); the off-cluster mirror runs the same function (slice 6).
- **Off-cluster anchor:**
  - the `vuoro-ops` service pulls new rows every 5 minutes, verifies the chain and the WebAuthn signatures, and stores a copy in the appservice cluster;
  - weekly, `vuoro-cli admin audit checkpoint` has the operator sign the chain head with the YubiKey.

  A compromised control can then append lies but cannot rewrite history undetected.
- **What the operator sees:**
  - `admin audit tail|verify [--since]` (slice 1), `admin audit show <op>` (slice 2);
  - a push notification for every admin mutation and break-glass event (§7 Q8: ntfy to the operator's phone; slice 2);
  - each workspace's members see admin operations on their workspace, with actor, reason and time. The existing audit view (`control.py:3425-3435`) is owner/admin only, so unit 2.2 adds a view of admin rows readable by every active member, and its CLI twin.

---

## 4. Target architecture

```
 Operator laptop                                   Claude / Routines / cloud agents
 ┌───────────────────────────────┐                 (claude-connector grant, aud=/mcp only)
 │ vuoro-cli  (vuoro_cloud_cli)  │                          │ HTTPS
 │  user face: PKCE loopback,    │                          v
 │    GitHub login, aud=/control │                 Cloudflare ─► cloudflared ─► gateway ─► tenant runtime
 │  admin face: localhost page,  │                 gateway: 404 on /api/control/v1/admin/*;
 │    WebAuthn(YubiKey, rp=      │                 upstream = control :8080 (no admin routes)
 │    localhost), aud=/control/admin
 │  creds: user file │ admin file│
 └──────┬────────────────┬───────┘
        │ public HTTPS   │ WireGuard tunnel only: 10.44.0.1:8443 (hostIP) ─ NetworkPolicy ipBlock 10.44.0.2/32
        v                v
 ┌──────────────────────── vuoro-system : vuoro-control (AS + control API) ───────────────────────┐
 │ :8080 public control   resources /mcp (existing), /control (new, user)                          │
 │   browser (cookie+CSRF+membership, unchanged); /v1/cli/* bearer aud=/control, human, membership │
 │ vuoro-control-admin :8443  resource /control/admin; TCP-peer /32 check, cf-* refused          │
 │   /v1/admin/* bearer aud=/control/admin, admin sub, epoch, scope (+ op-assertion from slice 2)  │
 │ tables:  users(kind human|test|agent, CHECK subject in gen B), admin_principals,                │
 │          admin_credentials, delegations, operations, audit_events (insert-only, hash-chained)   │
 │ jobs:    test-expiry reaper (policy:test-expiry@v1), orphan invariant report                    │
 │ creates: Backup CRs (new narrow RBAC); tenant controller executes lifecycle steps               │
 └───────────────▲─────────────────────────────────────▲──────────────────────────────────────────┘
                 │ JWT-bearer (projected SA), 5 min     │ RFC 8693 exchange, private_key_jwt,
                 │ admin.read/audit.read/backup         │ one-use decision proof → ≤15 min
                 │                                      │ /mcp token for agent:X (no refresh,
                 │                                      │ never effect.propose / work.claim)
 ┌───────────────┴────────── appservice cluster ────────┴─────────────────────────────┐
 │ vuoro-ops (vuoro-cli serve): audit mirror+verify, restore drills, backup freshness,│
 │   offsite age-encrypted copy (public recipient only)                                │
 │ cred-broker: mTLS workload auth (gate H8/item 7), policy (host,subject,repo)→      │
 │   vuoro.token/work, receipts (jti only) ──► perimeter agent sessions (homelab)     │
 └────────────────────────────────────────────────────────────────────────────────────┘
 CNPG ─barman─► primary bucket (SSE?, versioned, object-lock, no-delete creds)
                    └─ vuoro-ops copy ─age(YubiKey recipient)─► offsite bucket (second provider)
 Out of band, operator only: YubiKey promotion signing, SOPS keys, kubeconfig break-glass.
```

---

## 5. Phased slices and units

No slice changes the `/mcp` behaviour, the browser routes or promotion signing. Each vuoro-cloud generation is operator-signed. Units in the same repo that touch the same file run **sequentially** (a later unit's PR is based on the earlier unit's branch until it merges); units in different files or repos run in parallel.

### Unit table

Migration numbers are reserved here, in expected landing order, so parallel units cannot collide; `013` is the last on `main` at `332faa4`. The runner applies files in name order and skips applied ones (`scripts/migrate.py`), so an upgraded database silently applies a late, earlier-sorting file out of order. Rule: a unit whose migration would sort before a migration already on `main` renumbers at rebase to the next number above the highest on `main` (so no two files share a prefix), and every **not-yet-merged** unit whose reserved number is now below that shifts up by the same amount, preserving dependency order (a migration never lands after one that needs its tables); a reserved number that is not needed stays a gap. Unit 1.3 adds a CI check that every migration added by a branch sorts after every migration on the merge base.

| Unit | Repo | Owns (files / migrations) | Depends on | Parallel with |
|---|---|---|---|---|
| **0.1** multi-resource authorization addendum + classification report | agentops | `docs/contracts/vuoro-cloud-multi-resource-authorization.md`, `docs/runbooks/vuoro-cloud-principal-classification.md` | — | 1.1, 1.2 |
| **1.1** audit hash chain + insert-only trigger | vuoro-cloud | `migrations/014_audit_chain.sql`, `src/vuoro_cloud/audit_chain.py`, `tests/test_audit_chain*.py`, `tests/conftest.py` (audit reset fixture), `control.py` (explicit columns in the member audit view) | — | 0.1, 1.2 |
| **1.2** gateway deny for `/api/control/v1/admin/*` | vuoro-cloud | `src/vuoro_cloud/gateway.py` (deny only), `tests/test_gateway_admin_deny.py` | — | 0.1, 1.1 |
| **1.3** admin principal, WebAuthn, admin process, read-only admin routes, tunnel ingress | vuoro-cloud | `migrations/015_admin_identity.sql`; `src/vuoro_cloud/{webauthn,admin,cbor}.py`; `oauth_scopes.py` (namespace refusal, `ADMIN_SCOPES`); `control.py` (namespace refusal wiring); `config.py`; `pyproject.toml` (`vuoro-control-admin`, `vuoro-admin-enrol` scripts); `apps/control-admin/` (Deployment with `Recreate`, two suspended CronJob templates, WebAuthn ConfigMap); `clusters/vuoro-cloud-poc-apps/kustomization.yaml`; `platform/policies/network-policies.yaml`; `scripts/validate-deployment-distribution.py`; `scripts/apply-cloudflare-edge-rules.py` (admin path block); a migration-order CI check; `tests/test_admin*.py`, `tests/test_webauthn.py`, `tests/test_scope_matrix.py` | 1.1 (chained audit columns, `control.py`), 0.1 (matrix, merged or in review) | 1.2 |
| **1.4** CLI package, admin face (`admin enrol/login/logout/whoami/workspace list/show/audit tail/verify`) | vuoro-cloud | `src/vuoro_cloud_cli/`, `pyproject.toml` (`vuoro-cli` script, wheel packages), `tests/test_cli_admin.py` | 1.3 (API contract) | — (same `pyproject.toml` as 1.3) |
| **1.5** DB role split: owner, control, admin, gateway, controller roles; per-role grant matrix | vuoro-cloud | `platform/cnpg/repository.yaml` (`managed.roles`, initdb owner), `apps/control/migration-job.yaml`, admin, gateway and controller Deployment secrets, `migrations/016_role_grants.sql`, `tests/conftest.py` (roles and per-role test connections), a grant-matrix CI test; SOPS secrets (operator creates the values) | 1.1, 1.3 (admin tables exist) | 1.4 |
| **2.1** operations, operation assertions, users/workspace columns (generation A, no CHECK); switch 3.1's human check from the subject pattern to `kind='human'` plus the pattern | vuoro-cloud | `migrations/018_principal_kinds.sql`, `019_operations.sql` (the `RETIRED` workspace state is added by `ALTER TYPE … ADD VALUE` with no use of the value in the same file; tombstone columns); `admin.py` (assertion dependency); `webauthn.py` (UV by operation class); `cli_routes.py` (human check) | 1.3, 3.1 | — |
| **2.2** admin twins of operator routes; `principal disable/reclassify`; `workspace create/drain/transfer`; ntfy notifier; member-readable view of admin actions (browser route + CLI twin) | vuoro-cloud | `admin.py`, `control.py` (shared service functions, member admin-action view), CLI admin and user commands | 2.1 | — |
| **2.3** retire pipeline (plan/apply, dump, hold, teardown, tombstone) | vuoro-cloud | `controller.py`, `admin.py`, controller RBAC | 2.2 | — |
| **2.4** subject CHECK + membership triggers (generation B) | vuoro-cloud | `migrations/020_principal_subject_check.sql` | 2.2 **deployed** and blocker12's owner reclassified in production | — |
| **3.1** `/control` resource, `vuoro-cli` client, `CONTROL_SCOPES`, `/v1/cli/*` bearer routers | vuoro-cloud | `src/vuoro_cloud/cli_routes.py`; `control.py` (authorize/token accept `/control` for `vuoro-cli`, router include); `oauth_scopes.py`; `tests/test_cli_routes*.py`; `migrations/017_control_grants.sql` (`oauth_grants.workspace_id` is `NOT NULL`, `012_oauth_authorization_server.sql:53`; a `/control` grant spans the principal's memberships, so it gets `workspace_id` nullable only when `resource` is `/control`) | 1.3 (shares `oauth_scopes.py`, `control.py`); interim human check = subject `^github:[0-9]+$` (no `users.kind` yet) | — (lands before 2.1, which switches the check to `kind`) |
| **3.2** CLI user face (`login/logout/whoami/workspace list/status/roll --wait/repo bind/list/token/grant`) | vuoro-cloud | `src/vuoro_cloud_cli/` (user commands), `tests/test_cli_user.py` | 1.4, 3.1 | 2.x |
| **R** retire the static `operator()` token and its routes | vuoro-cloud | `control.py`, `config.py`, gateway operator-path counters, `scripts/record_backup_observation.py`, `scripts/rotate-operator-token.py`, `scripts/apply-cloudflare-edge-rules.py`, runbooks | 2.2 and 3.1 (every operator route has an admin or CLI twin, served for one generation) | 4, 5 |
| **4** test principals, reaper, harness client, test-login codes, `tst` gateway check | vuoro-cloud | `admin.py`, `control.py` (authorize page), `gateway.py`, migration `021` | 2.4 | 5 |
| **5a** backup create/list, restore, drills (control side) | vuoro-cloud | `admin.py`, controller RBAC, `platform/cnpg/`, migration `022` | 2.1 | 4 |
| **5b** primary bucket object lock + no-delete credentials; offsite bucket | bucket provider config (Terraform in vuoro-cloud `terraform/`, second provider account) | `terraform/…` | — (probe first) | everything |
| **6** `vuoro-ops` service | vuoro-cloud (`vuoro_cloud_cli serve`) + appservice cluster manifests (gitops repo for that cluster) | service code, image, manifests | 1.1, 1.4, 5a | 4 |
| **7** agent principals + cred-broker minting (gated on plan item 7 / H8) | vuoro-cloud + cred-broker | `admin.py`, `oauth_server.py`, migration `023`; cred-broker capability `vuoro.token/work` | 2.4, 4, cred-broker item 7 | — |

### Slice 0: classification and spec input (unit 0.1)

- Deliver:
  - the item 5 spec addendum: the three resources, the client × resource × scope × principal-kind matrix, the namespace refusals, the reserved-authority rule, and the admin listener's source rule;
  - a read-only classification query and runbook listing invalid subjects, orphaned workspaces and test data in non-test workspaces.
- Accept (done-check for slice 1): the addendum and runbook are on agentops `main` (or in an open PR that unit 1.3 cites), and unit 1.3 carries a test (`test_scope_matrix`) that encodes the matrix rows it implements, so drift between spec and code fails CI. Running the report is **not** a slice-1 gate; it gates generation B (unit 2.4).
- Forced failure: none (read-only). The report runs against a restore-drill copy first, then read-only against production before reclassification.

### Slice 1: admin principal, WebAuthn, read-only admin, audit chain (units 1.1-1.5)

- Deliver:
  - the insert-only hash-chained audit table (1.1);
  - the gateway deny (1.2);
  - `admin_principals`, `admin_credentials`, the `vuoro-admin-enrol` bootstrap/break-glass command and its two suspended CronJob templates, the `vuoro-control-admin` process with the tunnel ingress, the `vuoro-cli-admin` client and the `/control/admin` resource, and admin routes `auth/*`, `whoami`, `workspaces` (list/show), `audit` (tail/verify) (1.3);
  - `vuoro-cli admin enrol/login/logout/whoami/workspace list/show/audit tail/verify` (1.4);
  - the DB role split (1.5, operator-applied).
- Accept:
  - login with the daily key works, and so does login with the safe key;
  - each admin read is audited with the admin subject and credential id;
  - `admin audit verify` passes on production after the migration.
- Forced failures (each must be refused; refusals past authentication are audited, and edge refusals are counted in gateway security events):
  - a user session cookie on `/v1/admin/*`;
  - a user PAT or `/mcp` token on `/v1/admin/*`;
  - `/api/control/v1/admin/*` through the gateway (404, never proxied);
  - an admin route on the public control process (404);
  - claude-connector requesting `vuoro:admin.read` (`invalid_scope`);
  - any client requesting `vuoro:control.*` or `vuoro:admin.*` on `/oauth/authorize` or `/oauth/token` (`invalid_scope`);
  - a non-allow-listed AAGUID, a `none` attestation, or an attestation not chaining to the pinned root at enrolment;
  - an assertion without UV, with a wrong RP ID hash, a foreign origin, a replayed challenge, or a non-increasing sign count;
  - a request whose TCP peer is not an enrolled operator `/32`, including one from the node's own tunnel address `10.44.0.1`, one through `kubectl port-forward` (loopback peer), and one carrying `cf-connecting-ip`;
  - an admin-source configuration containing `10.44.0.1` or a loopback network (refused at startup);
  - an admin token after an `adm_epoch` bump, and a reused refresh token (family revoked);
  - `UPDATE`/`DELETE`/`TRUNCATE audit_events` as control's role;
  - a hand-edited row (trigger disabled by the owner in the test) detected by `audit verify`.

### Slice 2: admin lifecycle and the orphan fix (units 2.1-2.4)

- Deliver:
  - operation assertions and `operations` (2.1);
  - generation A columns (2.1); `admin principal disable/reclassify`, `admin workspace create/drain/transfer`, admin twins for every operator route, ntfy notifications (2.2);
  - `admin workspace retire` (2.3);
  - generation B: the CHECK, the owner invariant trigger, and `list --orphaned` (2.4).
- Accept:
  - blocker12-canary retired per D5, with the full audit chain and a stored WebAuthn assertion verifiable offline;
  - the 24 h hold is observed (blocker12 itself exercises it, since its owner's prior kind is human);
  - generation B's migrate Job succeeds on production.
- Forced failures:
  - retire without an assertion;
  - an assertion for a different plan digest;
  - a replayed assertion;
  - a destructive operation with touch but no PIN;
  - teardown when the dump or base backup failed (aborts before any delete);
  - disabling a sole owner with no disposition;
  - reclassifying a subject that matches `^github:[0-9]+$`;
  - generation B against a database that still has a violator (migrate aborts, names the id);
  - `INSERT users … 'github:abc'` after generation B;
  - a test member added to a non-test workspace;
  - a workspace insert with no owner.

### Slice 3: user-plane CLI (units 3.1-3.2; replaces browser-console `fetch()`)

- Deliver:
  - the `/control` resource and the `vuoro-cli` client;
  - `/v1/cli/*` routers for workspace read/roll, repo bind/list and PAT/grant management;
  - `roll --wait` (restore point printed; pre-roll backup from slice 5).
- Accept:
  - the operator onboards a repository to kotona and rolls it end to end from the CLI with no browser console.
- Forced failures:
  - a bearer from a non-member (403);
  - a bearer from a non-human principal kind (403);
  - a bearer request that also carries a session cookie (400);
  - a browser route without CSRF (still 403);
  - a `/control` token on `/mcp` and the reverse (audience);
  - a claude-connector request for `vuoro:control.*` (`invalid_scope`);
  - a `vuoro-cli` request for a `/mcp` scope or `vuoro:admin.*` on `/control` (`invalid_scope`);
  - a migrate Job failure makes `roll --wait` exit non-zero and print the restore point.

### Follow-ups outside these units

- **F-1:** narrow the tenant controller from the CNPG superuser to a tenant-provisioning role (§2 threat row). Not scheduled by this design.
- **F-2:** make the R-mcp refresh and PAT paths compare the principal epoch (today they only stamp it), so an epoch bump is a revocation in itself.

### Unit R: retire the static operator token

- Deliver: removal of `operator()`, its routes and `VUORO_CLOUD_OPERATOR_TOKEN_HASH`; runbooks switched to `vuoro-cli admin …`.
- Precondition (checked, not gated on anything else): each operator route has had an admin twin (or CLI twin) served for one generation, and control's audit shows no successful operator-route call (rows with actor `operator`) during that generation. (The gateway's `operator_path_rejected` counter counts only 401/403 and cannot show legitimate use.)
- Forced failure: the old operator token on any former operator route (404 / 401).

### Slice 4: test principals

- Deliver:
  - `admin test-principal create/retire`, the reaper, the `vuoro-test-harness` client, and test-login codes on the authorize page (D2b entropy and rate limits);
  - the `tst` claim check at the gateway.
- Accept:
  - a claude-connector OAuth flow completed with a test principal;
  - a CI gateway test with a harness token;
  - expiry retires the test workspace automatically.
- Forced failures:
  - reuse of a test-login code;
  - an expired code;
  - a code for a human principal;
  - 21 failed codes in an hour disable test login;
  - a token for an expired principal;
  - a `tst=true` token on a non-test workspace;
  - a harness token with a TTL above the ceiling;
  - a test principal requesting `vuoro:control.*`.

### Slice 5: backups and restore (units 5a, 5b)

- Deliver:
  - `admin backup create/list`, `admin restore` (to a new target), and the drill namespace plus scheduled drill; pre-roll backup in `roll`;
  - object lock and no-delete credentials on the primary bucket;
  - the offsite age copy;
  - the kubectl-created-CR detector.
- Accept:
  - the first automated drill passes with evidence;
  - an attended offsite restore passes;
  - restore-then-cutover is exercised on a test workspace.
- Forced failures:
  - a delete with cluster credentials (refused by the provider);
  - `admin restore` without PIN;
  - an in-place restore target (refused);
  - offsite decrypt without the YubiKey fails;
  - a corrupted drill backup raises an alert;
  - a kubectl-created Backup is flagged.

### Slice 6: `vuoro-ops` service

- Deliver: service identity (JWT-bearer from the projected SA), the audit mirror and verifier, drills moved to the service, and weekly signed checkpoints.
- Accept: a chain mismatch injected on a drill copy is detected within one interval.
- Forced failures:
  - the service requesting `admin.workspace.lifecycle`;
  - the service calling a route that needs an operation assertion;
  - a token from an unpinned issuer;
  - a replayed client assertion.

### Slice 7: agent principals and cred-broker minting (gated)

- Deliver: `kind=agent`, delegations, the RFC 8693 exchange for `vuoro-agent-delegate`, and cred-broker capability `vuoro.token/work`.
- Accept:
  - a perimeter Claude Code session obtains a ≤ 15-minute `/mcp` token for `agent:X` through cred-broker, and uses it;
  - the control audit and the cred-broker receipt link by `jti`.
- Forced failures:
  - a refresh-token request;
  - a scope, audience, workspace or repo outside the delegation;
  - a TTL above 15 minutes;
  - a missing, replayed or body-mismatched decision proof;
  - a caller without an enrolled mTLS certificate (the cloud-session case);
  - a disabled delegation;
  - a delegation ceiling or mint request naming `vuoro:effect.propose` (refused while reserved);
  - a delegation ceiling or mint request naming `vuoro:work.claim` (refused while reserved).

---

## 6. Dependency map against "Required before slice 1"

Those items gate the **effects** slice. This design is mostly independent of them. Where it touches one, the relation is below.

| # | Item | Relation to this design |
|---|---|---|
| 1 | TS-16 retained | **Consistent.** Acceptance and auto-accept policy live on the protected horizon (`credctl accept <intent-digest>`, #255 Q4), not in `vuoro-cli` or the vuoro.cloud admin plane (§8 C5). No cloud path reaches them. |
| 2 | E2 run identity and evidence | Slice 7 binds `run_id` into minted tokens once it exists. Before E2 run binding, slice 7 does not ship run-unbound tokens beyond `work.read`. |
| 3 | Exact repository subsets | Slice 7 delegations carry `repo_ids`, so they depend on the same grant plumbing. Slices 0-6 are unaffected. |
| 4 | Lifecycle owner, no temporary Vuoro state machine | Protected-side acceptance (credctl) waits for this. `operations` is platform lifecycle, not effects (D5). |
| 5 | Multi-resource authorization spec | **Prerequisite for unit 1.3.** Slice 0 writes the addendum for `/control` and `/control/admin`; 1.3's `test_scope_matrix` keeps code and addendum aligned. |
| 6 | One-use body-bound internal proof | Slice 7's cred-broker decision proof uses the same format. The admin operation assertion is the human-side analogue. |
| 7 | cred-broker workload auth, release, isolation | **Hard prerequisite for slice 7 only** (H8). |
| 8 | Crash-safe idempotency | `operations.idempotency_key` follows the same spec. Required for unit 2.3 retire, and borrowed from item 8's spec when it lands. |
| 9 | Executor DNS and egress gaps | Not applicable, since no executor exists here. The same test discipline applies to `vuoro-ops` egress (control, S3 buckets only). |
| 10 | Insert-only tamper-evident audit, non-secret outputs | **Delivered for the admin plane by units 1.1 and 1.5.** Effects can reuse it. |
| 11 | Image supply chain | `vuoro-ops` and the CLI image are pinned and verified the same way. Required for slice 6. |
| 12 | k3s only | Tunnel address, hostIP port mapping and NetworkPolicy claims are k3s-only. Talos claims no conformance. |

---

## 7. Operator decisions (recorded 2026-09-27)

The operator took the memo's recommended option for each question, with Q5 replaced by the full reserved-authority condition.

1. **Admin plane reachability: (a) WireGuard tunnel only, plus WebAuthn.** Delivered by unit 1.3 (admin process, hostIP on the tunnel address, NetworkPolicy, TCP-peer check) and unit 1.2 (gateway deny). Cost: no admin access from the phone. **Amended by the later #255 Q2 answer (§8):** the tunnel-only WebAuthn plane is the *protected* operator plane; read-only operator views and freeze/unfreeze additionally get a public, Authentik-OIDC operator identity. That is a change to this decision, recorded in §8, not a silent reinterpretation.
2. **blocker12-canary: (a) parked until slice 2 retires it through the admin API.** No kubectl-plus-SQL one-off, no bypass of membership checks. If it blocks a fleet-wide roll first, the existing operator drain and migration routes may be used with the reason written into the handoff.
3. **Admin session renewal: (a) a rotating admin refresh token with a 1-hour absolute lifetime.** Reuse revokes the family.
4. **Offsite encrypted copy: (a) a second provider's bucket.**
5. **`vuoro:effect.propose` in agent delegations: not until the reserved-authority condition holds.** `vuoro:effect.propose` (and likewise `vuoro:work.claim`) stays out of every delegation ceiling and mint until a durable intent store (respectively an exclusive, durable lease) exists **and** every tenant runtime serves the corresponding tools. "Once E3's queued path is proven" is not sufficient. Lifting it is a separate, reviewed change to `oauth_scopes.py` and the delegation refusal.
6. **CLI packaging: (a) in vuoro-cloud** (package `vuoro_cloud_cli`, command `vuoro-cli`).
7. **Tenant visibility of admin actions: (a) members see admin operations on their workspace** (actor, reason, time). Today's workspace audit view is limited to owner/admin members (`control.py:3425-3435`), so unit 2.2 adds a member-readable view of admin rows (every active member, any role) and its CLI twin.
8. **Notification channel: (a) ntfy or a push service to the operator's phone** (slice 2).
9. **Agent principal granularity: (a) one agent principal per perimeter host,** with repo narrowing in the delegation.

---

## 8. Reconciliation with the operator's answers on agentops#255 (2026-09-27)

The operator's answers on the split-horizon architecture (#255) postdate §7 and bind this design. #255 is being revised separately; this section records how this design follows it and where the two conflicted.

### 8.1 What #255 decides that applies here

- **Q2, modified (c): a separate Authentik-backed operator identity**, with its own client, audience and scopes, separate from the connector identity. Operations are classified:
  - **OIDC anywhere:** read status, inspect tenants, inspect audit/health.
  - **OIDC plus explicit operator step-up:** `mutations_frozen` freeze/unfreeze. "Reversible" is not enough; freeze is a powerful availability action.
  - **Protected only:** effect acceptance, credential/policy change, promotion, key rotation, recovery operations.
- **Q4:** `credctl accept` binds the **canonical intent digest**, not the intent id.
- **Principle:** nothing originating in the coordination plane becomes an effect merely because the coordination plane says it should. Proposals are untrusted input; protected acceptance is digest-bound.
- **Q1:** long-lived PATs are transitional; the long-term plan is a proper local identity/token flow.
- **Q5:** there is no service path from the public Vuoro horizon into the protected horizon.

### 8.2 Conflicts, stated explicitly

| # | This design (§7) said | #255 says | Resolution in this memo |
|---|---|---|---|
| C1 | Q1: the admin plane is reachable **only** over the WireGuard tunnel, including reads (slice 1 admin reads). | Reads of status, tenants, audit and health are "OIDC anywhere" through a separate Authentik operator identity. | **Two operator planes.** The tunnel-only WebAuthn plane (units 1.1-1.5, slice 2) stays as the **protected** plane: it may also serve reads, and slice 1 ships only reads, which the #255 classification permits there. A new **public operator plane** (units O.1-O.2 below) serves the "OIDC anywhere" reads and step-up freeze. §7 Q1 is amended accordingly. The operator should confirm that the protected plane keeps its reads (it costs nothing and gives the operator a view that does not depend on Authentik). |
| C2 | Slice 2 put `admin service-controls set` (freeze) on the tunnel plane with a touch. | Freeze/unfreeze is OIDC plus explicit step-up (so reachable publicly). | Freeze/unfreeze moves to the public operator plane with step-up (O.2). The tunnel-plane twin stays as the protected fallback when Authentik is unavailable. |
| C3 | Several slice-2 lifecycle mutations (create, roll, drain, migration plan/start/retry, invitations, invite requests) are touch-only on the tunnel plane. | #255 names only freeze as a public mutation; everything it lists as protected (acceptance, credential/policy change, promotion, key rotation, recovery) is protected only. It does not classify workspace lifecycle. | **Unclassified mutations default to protected-only** (tunnel plane), which is the conservative reading. Retire, restore, transfer, principal disable/reclassify, token mint, delegation set, credential enrol/disable, epoch bump and break-glass are credential/policy change or recovery, and are protected only by #255 itself. **Operator to confirm** whether any workspace lifecycle mutation (e.g. `roll`) should become "OIDC plus step-up"; until then none does. |
| C4 | D1: "GitHub is never a factor" in admin login; the design has no IdP besides GitHub (user plane) and WebAuthn (admin). | Operator identity is Authentik-backed. | Compatible if Authentik's operator login does not federate from GitHub. **Requirement for O.1:** the Authentik operator flow must use a non-GitHub source with a phishing-resistant factor (WebAuthn in Authentik), or a GitHub compromise would again yield operator reads and freeze. |
| C5 | D4: `intent accept/reject` lived in `vuoro-cli`, with the E3 lifecycle owner's API. | Acceptance is `credctl accept` on the protected side, bound to the canonical intent digest. | `vuoro-cli` and the vuoro.cloud admin plane never accept intents (D4 row changed). Acceptance is protected-horizon only, via credctl, digest-bound. |
| C6 | D3/slice 7: control (public horizon) mints agent tokens on a cred-broker (protected) exchange carrying a one-use decision proof. | Don't elevate one-use proofs into the cross-horizon security primitive; no service path from public into protected. | Compatible in direction: cred-broker calls control (protected → public), control never calls into the protected horizon, and the minted token carries work-plane authority only (no acceptance). The decision proof is an authentication of cred-broker to control, not an effect authorization. Slice 7 stays gated; it is re-checked against #255's revised §3.2 before it starts. |
| C7 | D4 user face: `token pat create/list/revoke` as a first-class CLI command. | Long-lived PATs are transitional. | `vuoro-cli login` (PKCE loopback, short access token + rotating refresh) is the intended local identity/token flow. `token pat …` stays for existing integrations and is marked transitional; slice 3 adds no new long-lived credential type. |
| C8 | D6: monthly **automated** restore drills run by the `vuoro-ops` service. | #255 treats restore drills as a hardware-presence process on the protected side. | Automated drills restore only the **primary** (non-offsite) backup into a drill namespace, need no key material and change no production state; attended offsite restores keep the hardware presence. **Operator to confirm** that automated primary-backup drills are acceptable. |
| C9 | Slice 6: the appservice cluster (protected) reaches control over the tunnel as a `/32` peer. | #255 Q5: packet-level WireGuard rules so there is no service path from the public horizon into the protected horizon. | Direction is protected → public only (the service pulls). The Q5 WireGuard rules must allow that outbound flow and still drop anything initiated from the vuoro.cloud node toward the protected side; slice 6 verifies both directions before it ships. |
| C10 | §7 Q8: ntfy push notifications for admin mutations. | #255 Q5 (no public → protected service path). | The notifier must publish to an ntfy endpoint outside the protected horizon (a hosted ntfy or a public relay), never a homelab-hosted ntfy reached from vuoro.cloud. Unit 2.2 names the endpoint. |

### 8.3 Digest binding and untrusted proposals in this design

- **Admin operation assertions (slice 2)** already bind `H(op_kind ‖ target ‖ params_digest ‖ reason ‖ nonce)`. Following #255's principle, the **CLI computes `params_digest` itself** from the canonical parameters the operator typed and refuses a challenge from control that does not commit to that digest. Control's rendering of an operation (plan, target description) is shown as untrusted context; the assertion is over the locally computed digest. A compromised control can therefore refuse or misreport, but cannot get a touch over parameters the operator did not enter.
- **Retire plans** (`retire --plan` → `--apply <digest>`): the plan is produced by control and is untrusted input. The digest the operator applies is the CLI's hash of the canonical plan it displayed; control must execute exactly that plan or fail.
- **Intent acceptance** is not in this design (C5); when E3 lands, `credctl accept` hashes the canonical proposal (intent type, exact parameters, source run, immutable evidence refs) on the protected side, and any change is a new intent and a new digest.

### 8.4 New units

| Unit | Repo | Owns | Depends on | Parallel with |
|---|---|---|---|---|
| **O.1** public operator identity (Authentik OIDC): resource `https://api.vuoro.cloud/control/operator`, client `vuoro-operator` (separate from `claude-connector` and `vuoro-cli`), scopes `vuoro:operator.read` and `vuoro:operator.freeze`, JWKS **pinned in Git-reviewed config** (control never fetches from the protected horizon, #255 Q5), read routes for status, tenants, audit and health under `/api/control/v1/ops/*` (not `/operator/`, which the Cloudflare edge rule restricts, `scripts/apply-cloudflare-edge-rules.py:91`); `vuoro-operator` is never a client of control's own authorization server and operator tokens never enter membership checks; JWKS rotation is a Git change, so revocation relies on short token lifetimes (≤ 5 min) plus a control-side deny list of operator subjects; acceptance includes proof that the Authentik flow has no GitHub source (C4) | vuoro-cloud (+ Authentik config in the homelab gitops repo) | new `operator_oidc.py`, routes on the public control process, migration `024` | 1.1 (audit), 0.1 addendum row update | 1.3-1.5, 3.x |
| **O.2** freeze/unfreeze with explicit step-up: requires an OIDC token whose `auth_time` is ≤ 5 min old and whose `acr`/`amr` shows the phishing-resistant factor; each call audited with reason | vuoro-cloud | `operator_oidc.py`, service-controls route twin | O.1 | — |

The authorization addendum (unit 0.1) gains rows for R-operator in the same pass as O.1. Neither O unit is in the current implementation batch (slices 0, 1, 3). The amendment of §7 Q1 (C1) follows #255 Q2 and is recorded; what waits for the operator is only whether the protected plane keeps its reads (C1, last sentence) and the C3 classification of lifecycle mutations.

