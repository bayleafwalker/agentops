# Design memo: separated admin identity and `vuoro-cli` for vuoro.cloud

Date: 2026-09-27. Status: **proposed**. This is a design pass and changes no code. Nothing here is adopted until the operator records it.

## Verification status (read first)

- **bayleafwalker/vuoro-cloud was not attached to this session.** The clone has no remote and no forge CLI. Every statement below about vuoro-cloud code (`control.py`, `oauth_scopes.py`, the users table, `operator()`, CNPG, the tenant controller) comes from the operator's 2026-09-27 brief. Each one is marked **[U]** (unverified in code). Line numbers are the brief's, not mine.
- The same **[U]** applies to vuoro-client (bayleafwalker/vuoro) and to cred-broker internals. The cred-broker **public README** was read on 2026-09-27. It says production use requires "verified mTLS and server-side session state", and that "provider adapters are disabled until an operator supplies dedicated provider identities, a protected signing/key substrate, enrolled client certificates, and live positive and negative canary evidence."
- **[A]** marks an inference or assumption: a claim about third-party behaviour (barman-cloud, S3 providers, WebAuthn clients) that this pass did not test.
- **Verified in this repo:**
  - TS-1 and TS-16 (`docs/plans/2026-09-17-target-state.md:30`, `:45`);
  - the effects decision and the "Required before slice 1" list (`docs/plans/2026-09-26-cloud-enablement-plan.md:31-59`);
  - the trusted-service design and its threat model (`docs/plans/2026-09-26-trusted-service-boundary-design.md`).

## Recommendation in one paragraph

- **Admin is a separate kind of principal.** It lives in its own table, uses the subject namespace `admin:<ulid>`, authenticates with WebAuthn only (YubiKey, PIN-verified), and has no membership rows. GitHub is never a factor.
- **The admin plane is a second protected resource on control**, reachable only over the operator WireGuard tunnel. Every mutation carries a WebAuthn assertion over the operation's digest. That assertion is the non-repudiation record.
- **The user plane gains a bearer path** (a second resource, membership still checked). `vuoro-cli` can then do what browser-console `fetch()` does today, without touching the cookie/CSRF routes.
- **Test principals** are a separate kind of principal (`test:<ulid>`). They are admin-minted, bound to test workspaces, expire, and are retired automatically. The "never `github:`" rule becomes a database constraint, which makes the blocker12 class of incident unrepresentable. Admin lifecycle operations give the cleanup path.
- **Minted tokens for agents are allowed in one narrow shape only:**
  - access tokens (no refresh token);
  - ≤ 15 minutes;
  - `aud=/mcp`, work-plane scopes only;
  - for a non-admin **agent principal**;
  - issued by control under an admin-authored delegation ceiling;
  - delivered by cred-broker to **perimeter** workloads that pass its mTLS workload auth.

  Cloud sessions never get them. They keep using the claude-connector OAuth grant. Control-plane and admin tokens are never mintable for workloads.
- **`vuoro-cli` is one distribution in vuoro-cloud with two faces:**
  - a human CLI (PKCE loopback; separate `login` and `admin login`);
  - a small trusted-side service in the appservice cluster. It holds only observe, backup and drill scopes, and never destructive ones.
- **The first slice** is the admin principal, WebAuthn login, read-only admin routes and the hash-chained audit trail. It depends on nothing in the "Required before slice 1" list except the multi-resource authorization spec (item 5), which this design has to feed.

---

## 1. Context

### Why now

- **One human, one account.** Sign-in is GitHub OAuth only (`github:<numeric id>`) **[U]**. The operator has one GitHub account, so the person who owns kotona is also the only possible administrator. Administration then either happens as a tenant member, or through a shared static secret.
- **Administration today is a shared secret plus copy-paste.**
  - The `operator()` bearer is a hash-checked static token with a CIDR allow-list and no per-person attribution **[U]**.
  - Workspace PATCH accepts only a browser cookie, CSRF and `administrative_membership` **[U]**. Operators paste `fetch()` calls into a browser console.
  - Backups are `kubectl` over the WireGuard tunnel **[U]**.
- **There is no sanctioned route to retire a workspace, transfer or recover ownership, or create a principal** **[U]**.
- **The orphan incident.**
  - Workspace `blocker12-canary` (`01M14W25EYKC…`) is owned only by `01M14W25EYSZ…`. That user's subject is `github:`-prefixed but non-numeric; it is a synthetic identity from a 2026-08-28 test run **[U]**.
  - Nobody can sign in as that user. The workspace cannot be rolled, drained by its owner or retired, and it sits on an old runtime at work schema 12 **[U]**.
  - Two defects produced it:
    1. nothing stops a non-OAuth writer from creating a `github:` subject;
    2. every lifecycle path goes through a member's session.

### Binding constraints this design must respect

| Constraint | Source | Consequence here |
|---|---|---|
| A cloud caller queues effects and never applies them. Acceptance happens on the trusted side; auto-accept is opt-in, off by default, trusted-side-set, asynchronous and recorded as the acceptor. | TS-16 (`2026-09-17-target-state.md:45`); cloud-enablement plan §"Effects" | The admin plane is trusted-side only. `vuoro-cli` is where the operator's interactive accept/reject lives, and where auto-accept policy is set. Nothing in this design gives a cloud caller a control-plane or admin audience. |
| C1: a synchronous propose is apply authority. | plan, decision 7 | Minted agent tokens carry no scope that performs an effect during the call. |
| H1: multi-resource authorization is a spec, not "one audience plus one table". | plan item 5 | The two new resources defined here (`/control`, `/control/admin`) are inputs to that spec. They are not added ad hoc. |
| H2: no bearer forwarding. Use one-use, body-bound internal proofs. | plan item 6 | No component forwards a caller's bearer. The CLI service and cred-broker authenticate as themselves. |
| H8: cred-broker workload auth is not deployment-ready. | plan item 7; README | Minting through cred-broker is gated on item 7. Nothing earlier depends on it. |
| Cloud sessions never hold CLI or admin credentials. | plan decision 4 | This is enforced structurally: loopback-only redirect URIs, client restrictions, tunnel-only admin ingress and WebAuthn. |
| Release promotion stays YubiKey-signed and operator-held. | plan decision 6 | Out of scope for `vuoro-cli`. The CLI never signs or promotes. |
| Cockpit writes go through the API, never raw DB writes. | `AGENTS.md` | This extends by analogy: blocker12 cleanup goes through the admin API, not psql. |

---

## 2. Threat model

| Actor | What they hold | Worst case without this design | Mitigation in this design | Residual |
|---|---|---|---|---|
| **Operator, user identity** (GitHub OAuth, owns kotona) | Browser session, PATs | GitHub account takeover gives full control of kotona, and today of *administration by membership* | User identity has no admin authority. A GitHub compromise yields only tenant-level authority on kotona. | Kotona data and settings, until the principal epoch is bumped |
| **Operator, admin identity** | Two enrolled YubiKeys (FIDO2 plus PIN) | n/a (new) | Tunnel-only ingress. Per-mutation, digest-bound WebAuthn. PIN for destructive operations. Out-of-band notification. 24 h teardown hold. | A coerced or careless operator |
| **Test principals** | Admin-minted test-login codes or tokens | Synthetic `github:` owners create orphans (today's incident) | `test:` namespace enforced by a CHECK constraint. Test workspaces only. Expiry and reaper. | Test workspaces, until expiry |
| **Claude connector / cloud agents** | claude-connector access and refresh tokens (aud `/mcp`) | Scope creep into control through a default grant | Control and admin scopes sit in `SCOPE_CLIENT_RESTRICTIONS` for CLI clients only and are hard-refused for claude-connector. Admin routes are unreachable from the edge. | As today (TS-16 surface) |
| **Appservice-cluster workloads** (vuoro-cli service, cred-broker) | Workload identity to control | A static operator token in a pod equals administration | The service holds observe, backup-trigger and drill scopes only; no step-up is possible without a YubiKey. cred-broker can mint only within the control-side delegation ceiling. | Backup and drill noise. Work-plane read or record tokens for agent principals, ≤ 15 min each. |
| **Compromised edge** (cloudflared, gateway) | Gateway assertion key, public ingress | Reaches any operator route whose CIDR check it can satisfy | Admin resource is not routed through cloudflared; the ingress rule admits tunnel CIDRs only. Admin routes reject gateway assertions and cookies. | Same as today for the work plane |
| **Compromised operator laptop** | CLI keyring: user tokens, admin refresh token (≤ 1 h), a plugged-in YubiKey | Static operator token on disk equals administration indefinitely | No long-lived admin secret on disk. Mutations need a touch, destructive ones need touch plus PIN. Notifications. Teardown hold. | ≤ 1 h of admin reads. Malware can prompt touches while the key is plugged in, so the displayed-digest check and the phone notification are the backstop. |
| **Compromised control** (AS plus DB) | Everything | Total | Off-cluster audit mirror and chain verification by the appservice service. WebAuthn assertions are verifiable offline. | Total; detected after the fact |

---

## 3. Decisions

### D1. Identity model

**Options.**

| | Shape | Verdict |
|---|---|---|
| a | `is_admin` flag on the existing `users` row | **Reject.** Admin becomes GitHub-authenticated, it is one account for both roles (what the operator wants to escape), and every membership code path has to learn to ignore it. |
| b | Admin row in `users` with an `admin:` subject and a different login method | **Reject.** Membership queries, `ROLE_AUTHORITIES` and PAT issuance all key on `users`. Each would need an exclusion, and a missed one is a privilege bug. |
| c | **Separate `admin_principals` and `admin_credentials` tables, a separate subject namespace, and a separate AS resource** | **Recommend.** Being structurally absent from membership means no membership check can ever pass for an admin, and no admin check can pass for a user. |

**Schema sketch [A]:**

- `admin_principals(id ulid, subject 'admin:'||id, handle, created_at, disabled_at, epoch int)`
- `admin_credentials(id, admin_id, webauthn_credential_id, public_key, aaguid, sign_count, label, enrolled_at, enrolled_by_op, disabled_at)`

**Authentication.** Choose WebAuthn/FIDO2 on the YubiKey the operator already uses for promotion.

- Discoverable credential, `userVerification=required` (PIN), and attestation checked against an allow-list of YubiKey AAGUIDs.
- Enrol two keys: daily and safe.
- The CLI reaches WebAuthn through the browser during PKCE loopback (§D4). This reuses the AS and needs no native FIDO stack.
- **OpenPGP card** (the signing applet) is not used for login. Using it would need a bespoke signed-request protocol, and it would couple release-signing key custody with admin login. Keep the two applets' roles separate.
- **GitHub is never a factor** in admin login, recovery or step-up. A GitHub compromise or outage must neither grant admin access nor block it.

**Sessions and step-up.**

| Artifact | TTL | Notes |
|---|---|---|
| AS admin browser session (admin origin only) | 1 h absolute, 15 min idle | Separate cookie name and path. Never valid on user routes. |
| Admin access token (`aud=https://api.vuoro.cloud/control/admin`) | 5 min | Carries `adm_epoch`. |
| Admin refresh token (client `vuoro-cli-admin` only) | 1 h absolute, rotating, reuse revokes | Stored in the OS keyring under a namespace vuoro-client never reads. See open question 3. |
| **Operation assertion** | single use, ≤ 120 s | A WebAuthn `get()` whose challenge is `H(op_kind ‖ target ‖ params_digest ‖ reason ‖ nonce)`. **Required for every admin mutation.** Destructive operations (retire, restore, transfer, principal disable, token mint for others, credential enrol/disable, auto-accept policy change) also need UV (PIN) in the same assertion. Reads need none. |

The operation assertion — `authenticatorData`, `clientDataJSON`, signature, credential id — is stored with the audit row. It is a hardware signature over exactly what was done, and anyone can verify it offline against the enrolled public key. That is the non-repudiation property (D7).

**Break-glass and recovery.**

- **Primary:** the second enrolled YubiKey.
- **Break-glass (both keys lost or control's admin tables damaged):** run `kubectl -n vuoro-system create job admin-enrol --from=cronjob/admin-enrol-template` over the WireGuard tunnel with the operator's kubeconfig. The one-shot job:
  - prints a single-use enrolment URL, valid 10 minutes, for a new credential;
  - writes an audit row with `actor_kind=break-glass`, `credential=cluster-admin`;
  - disables every existing admin credential.

  Cluster admin already implies total control, so this adds no new root.
- **No recovery codes.** They would be a factor weaker than the hardware and would become the real attack target.

**Admin is not a member.**

- Admin routes use a new `admin()` dependency: bearer, `aud=control/admin`, admin subject, active, epoch matches, scope. It never calls `administrative_membership`.
- The admin plane operates *on* workspaces (lifecycle, principals, backups, tokens). It does **not** read tenant work content. It has no route into the runtime's work data. When the operator wants to read or act on work in kotona, they do it as their user identity.
- Every admin action on a workspace is audited as the admin principal. It is also mirrored into that workspace's own audit view, which members can see (open question 7).

**The static `operator()` token** is retired in slice 7. Each operator route maps to an admin scope (§D4), and both paths serve for one generation.

### D2. Test principals

**Model.** Add `kind` to users: `human | test | agent`. Agent principals are introduced in D3.

Enforced by database constraint, not by application code:

```
CHECK ( (kind='human' AND external_subject ~ '^github:[0-9]+$')
     OR (kind='test'  AND external_subject ~ '^test:[0-9A-HJKMNP-TV-Z]{26}$')
     OR (kind='agent' AND external_subject ~ '^agent:[0-9A-HJKMNP-TV-Z]{26}$') )
test and agent rows: expires_at NOT NULL, created_by_admin NOT NULL (FK admin_principals)
workspaces.is_test boolean NOT NULL DEFAULT false
membership trigger: kind='test' ⇒ workspace.is_test;  workspace.is_test ⇒ member.kind IN ('test','agent')
```

- Only the GitHub OAuth callback inserts `kind='human'`. The test harness gets a DB role or API path that can create `test` only **[A]** (depends on how the test harness seeds data today, which is **[U]**).
- **Migration.** The constraint cannot be added while blocker12's owner row violates it. Slice 0 first runs a read-only classification query. Violators are rewritten to `kind='test'`, subject `test:<new ulid>` with the original preserved in `legacy_subject`, `expires_at=now()`, and `created_by_admin=<bootstrap admin>` — through the admin API in slice 2, never by hand. After that, the constraint lands.

**Lifecycle.**

- `vuoro-cli admin test-principal create --ttl 7d [--workspace new|<test ws>]`. The default TTL is 7 days and the maximum 30.
- The **reaper** runs inside control as a scheduled task with actor `policy:test-expiry@v1`. When a principal expires, it retires that principal's test workspaces through the same retire operation (D5), with backup skipped unless `--keep-backup` was set at creation, and then disables the principal.
- The reaper is platform lifecycle, not Vuoro intent handling. TS-1's "never expires" rule is about `EffectIntent` and does not apply here.

**MCP gateway tokens for test principals.** Two needs, two mechanisms.

- **(a) Gateway and tool tests from CI or the perimeter:**
  - `vuoro-cli admin token mint --principal test:… --client vuoro-test-harness --aud /mcp --scope vuoro:work.read --ttl 15m`;
  - client `vuoro-test-harness` is new and restricted to test principals;
  - no refresh token.
- **(b) Exercising the real Claude connector path:**
  - The admin mints a **test-login code**: single use, 15-minute TTL, bound to one test principal. It is shown once.
  - The AS authorization page gets a "test login" method, next to GitHub, that accepts only such codes and only for `kind='test'`.
  - The operator adds the connector in Claude and uses the code at the consent screen. The full authorize → code → token → refresh flow then runs with a test principal as resource owner.
  - Tokens carry `tst=true`. The gateway rejects `tst=true` on a non-test workspace as defence in depth; the constraint already makes it impossible.

**Recommend both.** (b) is the only way to test claude-connector end to end without a second GitHub account. (a) keeps CI off claude-connector.

### D3. Token minting

**What the admin can mint.**

| Subject | Client | Audience and scopes | Refresh | TTL | Revocation |
|---|---|---|---|---|---|
| test principal | `vuoro-test-harness` | `/mcp`, work-plane scopes | trusted-side harness only | ≤ min(24 h, principal expiry) | principal epoch bump; expiry |
| test principal | `claude-connector` | via test-login code only (D2b) | normal connector rules | normal | grant revoke; epoch; expiry |
| agent principal | `vuoro-agent-delegate` (cred-broker) | `/mcp`; `vuoro:work.read` now, E2 record scopes when they exist | **never** | ≤ 15 min | agent epoch; delegation disable; grant revoke |
| human principal | — | **not mintable by admin** | — | — | — |
| admin principal | — | **never minted**, only obtained by WebAuthn login | — | — | — |

- **No impersonation.** An admin minting tokens *as* the operator's user identity, or any human, would undo the separation. Humans mint their own PATs through the user plane (D4).
- **Epochs.** The principal epoch bump exists today **[U]**. Add epochs per agent principal, per delegation and per admin principal.

**Agent principals** (`agent:<ulid>`):

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
   - **control delegation (set with an admin mutation, audited):** client `vuoro-agent-delegate` may mint for `agent:X` with scope ceiling `{vuoro:work.read[, E2 record scopes]}`, audience `/mcp`, workspaces `{W}`, repos `{R…}`, TTL ceiling 15 min, rate N/h.
2. **cred-broker authenticates to control as itself.**
   - It uses `private_key_jwt` (RFC 7523) with its key in cred-broker's protected key substrate (a README production gate).
   - The request is RFC 8693 token exchange with `requested_subject=agent:X`, `resource=/mcp`, the narrowed scope and repo set, `run_id` once E2 exists, and `actor_token` = a one-use cred-broker decision proof. The proof is a signed JWT carrying `receipt_id`, request digest, `jti` and a 60-second expiry, in the shape of item 6.
3. **Control intersects the request with the delegation.** It issues an access token with `act={sub: client vuoro-agent-delegate}`, `run_id`, `repo_ids`, `jti` and a TTL of 15 minutes or less. It never issues a refresh token. Minting is refused if any part of the request exceeds the ceiling.
4. **cred-broker delivers the token** to the authenticated perimeter session, never to disk config. Its receipt records the `jti`, never the value. Control's audit records the mint with delegation id and version.
5. **The token is used directly against the gateway** by the workload. Internal hops use the gateway's one-use assertion as today.

**Why this passes the constraints.**

- **TS-16:** a work-plane token confers read, coordinate, record and propose at most, and no apply exists.
- **C1:** no scope in the ceiling performs an effect in-call. `vuoro:effect.propose` stays out of the ceiling until E3's queued path exists (open question 5).
- **H2:** nothing forwards a bearer; the proof is one-use and body-bound.
- **H8:** step 2 needs cred-broker's mTLS workload auth and key substrate, so this is the last slice and gated on item 7.
- **Decision 4:** cloud sessions are excluded by construction. Only mTLS-enrolled perimeter hosts can ask.

**Until item 7 closes:** the operator mints agent-principal tokens interactively with `vuoro-cli admin token mint --principal agent:X --ttl 15m` (touch plus PIN) and hands them to a perimeter session. This is the same authority with a human in the loop.

### D4. `vuoro-cli`

**Face (b): the operator's CLI.**

| Command group | Plane | Scope | Step-up |
|---|---|---|---|
| `login`, `logout`, `whoami` | user | — | — |
| `workspace list/status`, `workspace roll --wait` (own workspaces) | user (membership-checked) | `vuoro:control.workspace.read` / `.write` | — |
| `repo bind/unbind/list` | user | `vuoro:control.workspace.write` | — |
| `token pat create/list/revoke`, `grant list/revoke` (own) | user | `vuoro:control.token.manage` | — |
| `admin login` | admin | — | WebAuthn |
| `admin workspace list/show`, `admin audit tail/show/verify`, `admin backup list`, `admin rollout status` | admin | `vuoro:admin.read`, `vuoro:admin.audit.read` | — |
| `admin workspace create/roll/drain` | admin | `vuoro:admin.workspace.lifecycle` | touch |
| `admin workspace retire/transfer`, `admin principal disable` | admin | `vuoro:admin.workspace.lifecycle` / `vuoro:admin.principal` | touch + PIN |
| `admin test-principal create/retire`, `admin test-login-code` | admin | `vuoro:admin.principal` | touch |
| `admin token mint`, `admin delegation set/disable` | admin | `vuoro:admin.token.mint` | touch + PIN |
| `admin backup create`, `admin restore-drill run` | admin | `vuoro:admin.backup` | touch |
| `admin restore` | admin | `vuoro:admin.restore` | touch + PIN |
| `admin invitations …`, `admin service-controls …`, `admin analytics` (today's operator routes) | admin | `vuoro:admin.read` / `.workspace.lifecycle` | as class |
| `intent list/accept/reject`, `auto-accept set/show` (TS-16 reconciler, once E3 exists) | trusted side (the E3 lifecycle owner's API, item 4) | owned by that spec | accept: touch; policy change: touch + PIN |

**Protocol.** Two public clients use OAuth 2.1 authorization code with PKCE and a loopback redirect (`http://127.0.0.1:<ephemeral>/cb`, RFC 8252).

- **`vuoro-cli`** gets `resource=https://api.vuoro.cloud/control` and GitHub login.
- **`vuoro-cli-admin`** gets `resource=https://api.vuoro.cloud/control/admin` and WebAuthn login.
- Loopback-only redirects mean a cloud session cannot complete either flow for someone else. A cloud session also has no YubiKey.
- Operation assertions are fetched with a short browser round trip: the CLI opens `/admin/confirm?op=<id>`, which renders the digest, and the operator touches the key. **[A]:** a native libfido2 path can replace this later without protocol change, because the challenge format is the same.

**Face (a): the trusted-side service.**

- **Runs in** the appservice cluster, in namespace `vuoro-ops`, next to but separate from cred-broker. **[U]:** this assumes the appservice cluster reaches control over the operator tunnel CIDR.
- **Jobs:**
  1. mirror and verify the audit hash chain off-cluster (D7);
  2. run scheduled restore drills and backup-freshness checks (D6);
  3. later, evaluate the TS-16 auto-accept policy asynchronously, only if the operator enables it and only as the owner that item 4 names.
- **Authentication:** client `vuoro-cli-service` using the RFC 7523 JWT-bearer grant.
  - **Recommended:** a projected ServiceAccount token from the appservice cluster's issuer. Control pins that issuer's JWKS in Git-reviewed config.
  - **Fallback:** `private_key_jwt` with a SOPS-held key.
  - Access tokens last 5 minutes, with no refresh token.
- **Scopes:** `vuoro:admin.read`, `vuoro:admin.audit.read`, `vuoro:admin.backup` (on-demand plus drill namespace only). It can never produce an operation assertion, so no destructive route is reachable from it by construction.

**Scopes and client restrictions** (additions to `oauth_scopes.py` **[U]**):

- `vuoro:control.workspace.read`, `vuoro:control.workspace.write` and `vuoro:control.token.manage` are restricted to `vuoro-cli`.
- `vuoro:admin.*` is restricted to `vuoro-cli-admin`. A subset (`read`, `audit.read`, `backup`) is also restricted to `vuoro-cli-service`.
- None appears in any default grant.
- Add a **per-client rejected set**: claude-connector requesting any `vuoro:control.*` or `vuoro:admin.*` gets `invalid_scope`. This is a hard failure, not a silent drop, so misconfiguration is loud.
- Admin scopes are issued only when the authenticated subject is an admin principal, and user-plane scopes only for human principals. The AS checks the principal kind as well as the client.
- **A single umbrella `vuoro:control.admin` is rejected.** Narrow scopes let the service hold observe and backup without lifecycle.

**Bearer path next to the browser session.**

- **Keep every existing cookie route as is.** Cookie plus CSRF plus `administrative_membership`, `Depends(browser)` **[U]**.
- **Add separate routers:**
  - `/api/control/v1/cli/...` uses `Depends(control_bearer(scope))`: bearer only, `aud=/control`, human subject, `administrative_membership(workspace, token.sub)` still required.
  - `/api/control/v1/admin/...` uses `Depends(admin(scope, op_assertion=…))`.
  - The handler bodies share service functions with the browser routes. Authentication is the only fork.
- **Why CSRF is not weakened.** CSRF exists because cookies are ambient. The bearer routers:
  - ignore and **reject** any request that also carries a session cookie (400), so a browser can never reach them ambiently;
  - send no CORS allow-origin;
  - accept only `Authorization: Bearer` with `typ=at+jwt`.
- Gateway assertions and PATs minted for `/mcp` are refused on both routers by audience.

**Packaging.**

| Option | Verdict |
|---|---|
| Subcommands in vuoro-client (bayleafwalker/vuoro) | **Reject.** It would put vuoro.cloud control/admin surface into the product client that agents and sprintctl import. Admin credential handling would then share a process and profile store with agent tooling. |
| **Separate distribution `vuoro-cloud-cli` (command `vuoro-cli`) in vuoro-cloud**, depending on vuoro-client for HTTP, profiles and User-Agent | **Recommend.** The control API and its client ship together. Admin credentials live in a keyring namespace vuoro-client never reads. `admin` can never be the default profile. The service face is the same package with a `serve` entry point and its own image. |

### D5. Workspace lifecycle as audited operations

**Operation record.** Each lifecycle action is an `operations` row:

- `id`, `kind`, `target`, `actor{kind,id}`;
- `credential{client_id, token_jti, webauthn_cred_id, assertion_id}`;
- `reason` (required for admin, ≥ 10 characters);
- `params_digest`, `idempotency_key`;
- `state requested→running→succeeded|failed|cancelled`;
- `steps[]` with timestamps.

Control executes operations and the tenant controller performs the cluster steps, as rollouts do today **[U]**. This is platform lifecycle. It is **not** an effects state machine, so item 4 ("no temporary Vuoro execution state machine") does not apply to it.

| Operation | Actor | Steps | Guards |
|---|---|---|---|
| **create / onboard** | admin (or a user via invitation, as today) | create workspace row → owner membership → desired_state READY → controller provisions | Owner must be `kind=human` with a valid subject, or `test` for `is_test`. Workspace creation and owner membership happen in one transaction, so a workspace with no owner cannot exist. |
| **repo bind** | user (owner/admin member) | record binding → verify provider reachability **[U]**: current binding mechanics unknown | Effects allowlists stay Git-reviewed (trusted-service design §T4). A CLI binding never widens effects. |
| **roll** | user (own) or admin | if the target image's migration set changes the schema: on-demand backup, wait for completion → PATCH READY → watch `vuoro-migrate-<gen>` → Deployment ready | Migrations are forward-only **[U]**, so a pre-roll backup is mandatory when schema changes. `--wait` exits non-zero on migrate failure and prints the restore point. |
| **drain** | admin | existing maintenance drain **[U]** | touch |
| **retire** | admin | `retire --plan` prints plan and digest → `retire --apply <digest>` (touch + PIN) → backup (skipped for test unless kept) → drain → revoke all grants and PATs scoped to the workspace → scale to zero → **24 h hold** (non-test; cancellable) → delete namespace, DB, roles, secrets → workspace row becomes `retired` tombstone (id never reused) → audit | Plan digest binds the assertion. Teardown refuses unless the backup's `status=completed` and WAL is archived past the drain LSN. |
| **transfer ownership** | admin | add new owner → remove or downgrade old owner, in one transaction | touch + PIN. The new owner must be able to authenticate. |
| **principal disable** | admin | epoch bump → revoke grants → for each workspace where the principal is the sole owner, **refuse** unless `--disposition <ws>=transfer:<p>|retire` is given for each | Makes new orphans impossible through the admin path. |
| **orphan recovery** | admin | `admin workspace list --orphaned` (owner kind invalid, disabled, expired, or no authenticable owner) → transfer or retire | — |

**Invariant, checked by a trigger plus a nightly report:** every non-retired workspace has at least one owner who is (a) human with a valid subject and not disabled, or (b) test, not expired, in a test workspace. Because the admin plane never needs membership, a violated invariant is always recoverable.

**Worked example: `blocker12-canary`.** All identifiers **[U]**.

1. **Slice 0 report.** `01M14W25EYSZ…` fails the subject pattern, and `01M14W25EYKC…` has no authenticable owner. Also check whether that principal owns or belongs to anything else.
2. **Slice 2 prerequisite:**

   ```
   vuoro-cli admin principal reclassify 01M14W25EYSZ… --as test --expire now \
       --reason "synthetic github: subject seeded by 2026-08-28 test run; blocker12 orphan"
   ```

   This is touch + PIN. The subject becomes `test:<ulid>`, `legacy_subject` is kept, and the workspace is marked `is_test`. Now the constraint can land.
3. `vuoro-cli admin workspace show 01M14W25EYKC…` shows the runtime image, work schema 12, and the last backup.
4. `vuoro-cli admin workspace retire 01M14W25EYKC… --keep-backup 30d --plan --reason "orphaned test canary, schema 12, no authenticable owner"` prints the plan digest.
5. `… --apply <digest>` (touch + PIN):
   1. on-demand backup, kept 30 days as evidence even though it is a test workspace;
   2. drain;
   3. revoke;
   4. scale to zero;
   5. teardown without the 24 h hold, because the workspace is now `is_test`;
   6. tombstone.
6. The expired test principal is disabled by the reaper, with actor `policy:test-expiry@v1` and the linked operation.
7. **Root cause.** Find the 2026-08-28 seeding test and move it to `admin test-principal create`. The CHECK constraint makes a repeat fail at insert time.

**Interim:** leave the canary parked (see open question 2).

### D6. Encrypted backups

**Facts [U]:**

- CNPG with barman-cloud writes to `s3://vuoro-cloud-poc-cnpg-backups`;
- backups are daily plus on-demand Backup CRs created with kubectl over the tunnel;
- the S3 provider and any current encryption setting are unknown.

**Encryption options.**

| | Mechanism | Protects against | Verdict |
|---|---|---|---|
| a | Provider server-side encryption (barman-cloud `encryption: AES256` / `aws:kms` **[A]**, if the provider supports it) | Provider media theft only. Anyone with bucket credentials reads plaintext. | Turn on if supported; it costs nothing, but it is **not** the control. |
| b | Client-side encryption in the primary backup path | Bucket-credential or provider compromise | **[A]:** barman-cloud, as CNPG drives it, has no client-side encryption. It would mean a CNPG plugin or a switch away from barman. Defer. |
| c | **Immutable primary plus client-side-encrypted offsite copy** | Credential compromise (ciphertext only in the copy), cluster compromise destroying backups (object lock), provider loss (second provider) | **Recommend.** |

**Recommended shape.**

- **Primary bucket:**
  - SSE if available;
  - versioning plus object lock (compliance mode, 35-day retention) **[A: provider support]**;
  - cluster credentials that can put and get but **not** delete. Lifecycle expiry does the deleting.

  A compromised cluster can then read backups (it can read the database anyway) but cannot destroy them.
- **Offsite copy:**
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

**On-demand trigger.** `vuoro-cli admin backup create` (touch) causes control to create the Backup CR. This needs new RBAC on control's ServiceAccount: create `backups.postgresql.cnpg.io` in the data namespace only **[U]**. Pre-roll and pre-retire backups use the same path, and kubectl becomes break-glass.

### D7. Audit and non-repudiation

- **Store:** an `audit_events` table (it exists **[U]**; the trusted-service design references it).
  - **Insert only:** control's DB role has INSERT but not UPDATE or DELETE, and a trigger rejects both.
  - Each row carries `prev_hash`, `row_hash = H(prev_hash ‖ canonical_json(row))`.
  - This closes item 10's "insert-only, tamper-evident" requirement for the admin plane.
- **Row:**
  - `event_id`, `at`, `actor_kind` (admin, user, test, agent, service, policy, break-glass), `actor_id`;
  - `credential` (client_id, token jti, webauthn credential id, operation-assertion blob);
  - `reason`, `operation_id`, `target`, `params_digest`, `outcome`, `source_ip`, `request_id`.
  - Secret values are never recorded. A strict output schema applies (item 10).
- **Off-cluster anchor:**
  - the `vuoro-ops` service pulls new rows every 5 minutes, verifies the chain and the WebAuthn signatures, and stores a copy in the appservice cluster;
  - weekly, `vuoro-cli admin audit checkpoint` has the operator sign the chain head with the YubiKey.

  A compromised control can then append lies but cannot rewrite history undetected.
- **What the operator sees:**
  - `admin audit tail|show <op>|verify [--since]`;
  - a push notification for every admin mutation and break-glass event (channel: open question 8);
  - each workspace's members see admin operations on their workspace, with actor, reason and time.

---

## 4. Target architecture

```
 Operator laptop                                   Claude / Routines / cloud agents
 ┌───────────────────────────────┐                 (claude-connector grant, aud=/mcp only)
 │ vuoro-cli  (vuoro-cloud-cli)  │                          │ HTTPS
 │  user face: PKCE loopback,    │                          v
 │    GitHub login, aud=/control │                 Cloudflare ─► cloudflared ─► gateway ─► tenant runtime
 │  admin face: PKCE loopback,   │                 (NO route to /control/admin; admin routes refuse
 │    WebAuthn(YubiKey), aud=/control/admin        gateway assertions and cookies)
 │  keyring: user ns │ admin ns  │
 └──────┬────────────────┬───────┘
        │ public HTTPS   │ WireGuard operator tunnel only
        v                v
 ┌──────────────────────── vuoro-system : vuoro-control (AS + control API) ───────────────────────┐
 │ resources: /mcp (existing)   /control (new, user)   /control/admin (new, admin, tunnel-CIDR)    │
 │ routers:   browser (cookie+CSRF+membership, unchanged)                                          │
 │            /v1/cli/*   bearer aud=/control, human sub, membership required, cookies rejected    │
 │            /v1/admin/* bearer aud=/control/admin, admin sub, epoch, scope, op-assertion         │
 │ tables:    users(kind human|test|agent, CHECK subject), admin_principals, admin_credentials,    │
 │            delegations, operations, audit_events (insert-only, hash-chained)                    │
 │ jobs:      test-expiry reaper (policy:test-expiry@v1), orphan invariant report                  │
 │ creates:   Backup CRs (new narrow RBAC); tenant controller executes lifecycle steps             │
 └───────────────▲─────────────────────────────────────▲──────────────────────────────────────────┘
                 │ JWT-bearer (projected SA), 5 min     │ RFC 8693 exchange, private_key_jwt,
                 │ admin.read/audit.read/backup         │ one-use decision proof → ≤15 min
                 │                                      │ /mcp token for agent:X (no refresh)
 ┌───────────────┴────────── appservice cluster ────────┴─────────────────────────────┐
 │ vuoro-ops (vuoro-cli serve): audit mirror+verify, restore drills, backup freshness,│
 │   offsite age-encrypted copy (public recipient only); later: auto-accept evaluator │
 │ cred-broker: mTLS workload auth (gate H8/item 7), policy (host,subject,repo)→      │
 │   vuoro.token/work, receipts (jti only) ──► perimeter agent sessions (homelab)     │
 └────────────────────────────────────────────────────────────────────────────────────┘
 CNPG ─barman─► primary bucket (SSE?, versioned, object-lock, no-delete creds)
                    └─ vuoro-ops copy ─age(YubiKey recipient)─► offsite bucket (second provider)
 Out of band, operator only: YubiKey promotion signing, SOPS keys, kubeconfig break-glass.
```

---

## 5. Phased slices

Every slice lands in vuoro-cloud (control, controller, platform) plus the new `vuoro-cloud-cli` package. No slice changes the `/mcp` behaviour, the browser routes or promotion signing. Each generation is operator-signed.

**Slice 0: classification and spec input (read-only).**
- Deliver:
  - the item 5 spec addendum (two resources, the client × scope × principal-kind matrix, per-client rejected sets);
  - a read-only report of invalid subjects, orphaned workspaces and test data in non-test workspaces.
- Accept:
  - the report lists blocker12 and its owner, and nothing unexplained;
  - the spec addendum is reviewed together with item 5.
- Forced failure: none (read-only). The report query runs against a restore-drill copy, not production.

**Slice 1: admin principal, WebAuthn, read-only admin, audit chain.**
- Deliver:
  - `admin_principals` and `admin_credentials`;
  - the bootstrap enrolment job (the break-glass job, first run);
  - the `vuoro-cli-admin` client and the `/control/admin` resource, tunnel-CIDR only;
  - `admin login/whoami/workspace list/show/audit tail/verify`;
  - the insert-only hash-chained audit table.
- Accept:
  - login with the daily key works, and so does login with the safe key;
  - each admin read is audited with the admin subject and credential id.
- Forced failures (each must be refused and audited):
  - a user session cookie on `/v1/admin/*`;
  - a user PAT or `/mcp` token on `/v1/admin/*`;
  - claude-connector requesting `vuoro:admin.read` (`invalid_scope`);
  - `vuoro-cli` (user client) requesting admin scopes;
  - a non-YubiKey authenticator (AAGUID) at enrolment;
  - a request from outside the tunnel CIDR;
  - an admin token after an `adm_epoch` bump;
  - `UPDATE audit_events` as control's role;
  - a hand-edited row detected by `audit verify`.

**Slice 2: admin lifecycle and the orphan fix.**
- Deliver:
  - operation assertions;
  - `operations`;
  - `admin workspace create/roll/drain/retire/transfer`, `admin principal disable/reclassify`;
  - the `kind` column plus the CHECK constraint (after reclassifying violators), the owner invariant trigger, and `list --orphaned`;
  - migration of the operator routes for drain, epoch and invitations.
- Accept:
  - blocker12-canary retired per D5, with the full audit chain and a stored WebAuthn assertion verifiable offline;
  - the 24 h hold is observed on a non-test canary.
- Forced failures:
  - retire without an assertion;
  - an assertion for a different plan digest;
  - a replayed assertion;
  - a destructive operation with touch but no PIN;
  - teardown when the backup failed (aborts before any delete);
  - disabling a sole owner with no disposition;
  - `INSERT users … 'github:abc'`;
  - a test member added to a non-test workspace;
  - a workspace insert with no owner.

**Slice 3: user-plane CLI (replaces browser-console `fetch()`).**
- Deliver:
  - the `/control` resource and the `vuoro-cli` client;
  - `/v1/cli/*` routers for workspace read/roll, repo bind and PAT/grant management;
  - pre-roll backup when the schema changes, and `roll --wait`.
- Accept:
  - the operator onboards a repository to kotona and rolls it end to end from the CLI with no browser console.
- Forced failures:
  - a bearer from a non-member (403);
  - a bearer request that also carries a session cookie (400);
  - a browser route without CSRF (still 403);
  - a `/control` token on `/mcp` and the reverse (audience);
  - a claude-connector request for `vuoro:control.*` (`invalid_scope`);
  - a migrate Job failure makes `roll --wait` exit non-zero and print the restore point.

**Slice 4: test principals.**
- Deliver:
  - `admin test-principal create/retire`, the reaper, the `vuoro-test-harness` client, and test-login codes on the authorize page;
  - the `tst` claim check at the gateway.
- Accept:
  - a claude-connector OAuth flow completed with a test principal;
  - a CI gateway test with a harness token;
  - expiry retires the test workspace automatically.
- Forced failures:
  - reuse of a test-login code;
  - an expired code;
  - a code for a human principal;
  - a token for an expired principal;
  - a `tst=true` token on a non-test workspace;
  - a harness token with a TTL above the ceiling;
  - a test principal requesting `vuoro:control.*`.

**Slice 5: backups and restore.**
- Deliver:
  - `admin backup create/list`, `admin restore` (to a new target), and the drill namespace plus scheduled drill;
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

**Slice 6: `vuoro-ops` service.**
- Deliver: service identity (JWT-bearer from the projected SA), the audit mirror and verifier, drills moved to the service, and weekly signed checkpoints.
- Accept: a chain mismatch injected on a drill copy is detected within one interval.
- Forced failures:
  - the service requesting `admin.workspace.lifecycle`;
  - the service calling a route that needs an operation assertion;
  - a token from an unpinned issuer;
  - a replayed client assertion.

**Slice 7: agent principals and cred-broker minting (gated).**
- Deliver:
  - `kind=agent`, delegations, the RFC 8693 exchange for `vuoro-agent-delegate`, and cred-broker capability `vuoro.token/work`;
  - retirement of the static `operator()` token.
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
  - `vuoro:effect.propose` before E3;
  - the old operator token after removal.

---

## 6. Dependency map against "Required before slice 1"

Those items gate the **effects** slice. This design is mostly independent of them. Where it touches one, the relation is below.

| # | Item | Relation to this design |
|---|---|---|
| 1 | TS-16 retained | **Consistent.** The admin plane is trusted-side. The reconciler's accept/reject and auto-accept policy live in the CLI (touch / touch + PIN). No cloud path reaches it. |
| 2 | E2 run identity and evidence | Slice 7 binds `run_id` into minted tokens once it exists. Before E2, slice 7 does not ship run-unbound tokens beyond `work.read`. |
| 3 | Exact repository subsets | Slice 7 delegations carry `repo_ids`, so they depend on the same grant plumbing. Slices 0-6 are unaffected. |
| 4 | Lifecycle owner, no temporary Vuoro state machine | The `intent accept/reject` commands wait for this. `operations` is platform lifecycle, not effects (D5). |
| 5 | Multi-resource authorization spec | **Hard prerequisite for slice 1.** Slice 0 writes the addendum for `/control` and `/control/admin`. |
| 6 | One-use body-bound internal proof | Slice 7's cred-broker decision proof uses the same format. The admin operation assertion is the human-side analogue. |
| 7 | cred-broker workload auth, release, isolation | **Hard prerequisite for slice 7 only** (H8). |
| 8 | Crash-safe idempotency | `operations.idempotency_key` follows the same spec. Required for slice 2 retire, and borrowed from item 8's spec when it lands. |
| 9 | Executor DNS and egress gaps | Not applicable, since no executor exists here. The same test discipline applies to `vuoro-ops` egress (control, S3 buckets only). |
| 10 | Insert-only tamper-evident audit, non-secret outputs | **Delivered for the admin plane by slice 1.** Effects can reuse it. |
| 11 | Image supply chain | `vuoro-ops` and the CLI image are pinned and verified the same way. Required for slice 6. |
| 12 | k3s only | Tunnel-CIDR and NetworkPolicy claims are k3s-only. Talos claims no conformance. |

---

## 7. Open questions for the operator

1. **Admin plane reachability.**
   - (a) WireGuard tunnel only, plus WebAuthn.
   - (b) Public behind WebAuthn only.
   - (c) Public behind Cloudflare Access plus WebAuthn.

   **Recommend (a).** The tunnel already gates kubectl and the operator token, and it keeps a compromised edge out of the admin plane entirely. The cost is no admin access from the phone.
2. **blocker12-canary before slice 2.**
   - (a) Leave it parked until slice 2 retires it through the API.
   - (b) An audited one-off now: kubectl plus SQL over the tunnel, with a written runbook.

   **Recommend (a),** unless it blocks a fleet-wide roll or gen-46. It is harmless while parked, and (b) is exactly the unsanctioned path this design removes.
3. **Admin session renewal.**
   - (a) A rotating admin refresh token with a 1-hour absolute lifetime.
   - (b) No refresh: a WebAuthn touch every 5 minutes.
   - (c) An 8-hour absolute lifetime.

   **Recommend (a).** Mutations need a touch anyway, so the refresh only extends reads.
4. **Offsite encrypted copy.**
   - (a) A second provider's bucket.
   - (b) Homelab NAS.
   - (c) Skip; object lock only.

   **Recommend (a).** It survives the loss of both the homelab and the primary provider. (b) is fine if egress from the appservice cluster to a second provider is unwanted.
5. **`vuoro:effect.propose` in agent delegations after E3.**
   - (a) Allow within the delegation ceiling once E3's queued path is proven.
   - (b) Never for minted tokens; only claude-connector and interactive sessions propose.

   **Recommend (a).** Propose only queues (TS-16), and acceptance stays trusted-side.
6. **CLI packaging.**
   - (a) `vuoro-cloud-cli` in vuoro-cloud.
   - (b) Subcommands in vuoro-client.

   **Recommend (a),** as reasoned in D4.
7. **Tenant visibility of admin actions.**
   - (a) Members see admin operations on their workspace (actor, reason, time).
   - (b) Operator only.

   **Recommend (a).** It is cheap now, and it is expected once there are non-operator tenants.
8. **Notification channel for admin mutations.**
   - (a) ntfy or a push service to the operator's phone.
   - (b) Email.
   - (c) An issue comment on a private repo.

   **Recommend (a).** It is the only one fast enough to catch a malicious touch within the 24 h hold.
9. **Agent principal granularity.**
   - (a) One agent principal per perimeter host.
   - (b) One per (host, repo).
   - (c) One per harness kind.

   **Recommend (a),** with repo narrowing in the delegation. Attribution by host matches cred-broker's session model.
