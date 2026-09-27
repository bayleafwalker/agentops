# vuoro.cloud as the primary operator endpoint: workflow experience, UI/UX enablement, documentation library (2026-09-27)

Status: proposal (read-only ideation pass, session bef3ec08). Nothing here is adopted; §4 items are candidates for sprintctl once the operator picks them. Inferences are marked **Assumption**.

Operator direction this responds to: vuoro.cloud becomes the primary endpoint through which the whole agentic workflow is run; supplemental `vuoro-shared` / `vuoro-self-hosted` endpoints carry the high-sensitivity and horizon-protected services (interactive admin operations, cred-broker and the like). The split-horizon architecture is being documented in a separate session and is referenced here, not redone.

Companion documents (reference, do not duplicate):

- `docs/plans/2026-09-27-backlog-ideation.md` (agentops PR #253): H1/H2/H3 items, incl. H1-7 fleet drift report on `/admin`, H2-3 pending intents in `next-work`, H2-6 onboarding gate closure, H3-2 `vuoro provenance`, H3-5 settlement view in the dashboard.
- `docs/plans/2026-09-27-admin-identity-and-vuoro-cli-design.md` (branch `docs/admin-identity-vuoro-cli-design`, PR pending): admin principal with WebAuthn, admin plane over WireGuard, bearer path on the user plane, `vuoro-cli` (slices 0-7).
- `docs/plans/2026-09-26-cloud-enablement-plan.md` §"Effects: queued intents and acceptance" and `docs/plans/2026-09-17-target-state.md:45` (TS-16).
- The split-horizon architecture memo (separate session, title TBD) and the telemetry/audit companion pass.

Evidence base: vuoro-cloud `origin/main` (poc.44 tagged, 47 candidate signed 2026-09-27) — `apps/web/deployment.yaml`, `src/vuoro_cloud/control.py`, `oauth_scopes.py`, `gateway.py`, `docs/GETTING-STARTED.md`, `docs/runbooks/operator-actions.md`, `IMPLEMENTATION-STATUS.md`; agentops handoffs `docs/dispatch/handoffs/2026-09-2{3,4,5,6}-program-long-goal-handler.v*.md`; audit `_artifacts/agentops/audit/events-2026-09-2{6,7}.ndjson` (sampled); session scratchpads `OPERATOR-ACTIONS.md`, `CLOUD-RUNS.md`, `brief-*.txt`.

---

## 0. What vuoro.cloud is today (baseline)

| Surface | Implementation | What it can do |
|---|---|---|
| `vuoro.cloud` | `vuoro-web`: Chainguard nginx, two ConfigMaps (`apps/web/deployment.yaml` L17-32). Cloudflared routes `vuoro.cloud` → `vuoro-web`, `api.vuoro.cloud` → `vuoro-gateway` (`platform/cloudflared/deployment.yaml` L33-37); no k8s Ingress. | Landing + 4 static concept pages (`mental-model`, `architecture`, `ecosystem`, `alternatives`); an inline SPA (`index.html` + `app.js` in the ConfigMap) for `/join`, `/dashboard`, `/activate`, `/admin`. |
| `/dashboard` | `app.js` `dashboard()` | GitHub sign-in, list/create workspaces, bind one repository (owner/admin), logout, 10 s poll. **No** tokens, grants, sessions, audit, roll, or connect-a-client panel. Signed-out state is a bare "Sign in required" (onboarding gap 1). |
| `/admin` | `app.js` `admin()` | "Operator console": the shared static operator bearer pasted into a form, kept in `sessionStorage`; reads `service-controls`, `product-analytics`, `invite-requests`, `rollout/status`; can mark invite requests "invited". |
| `api.vuoro.cloud` control routes | `control.py` | Browser-session (cookie + CSRF) user plane: workspaces, tokens (create/rotate/revoke), grants (list/revoke), sessions, memberships, connectors, `audit-events`, `PATCH /workspaces/{id}` (the roll). Operator-bearer plane: invitations, epoch bump, drain, migration plan/start/retry/status, backup observations, service controls. Workspace-bearer plane: `doctor`, `handshake`, `metrics`, artifact receipts/probes. No `/releases`, `/promotions`, `/effects`, `/intents`, `/approvals` routes exist. |
| `/mcp` | `gateway.py` → tenant `vuoro-service mcp-serve` | Grantable scopes `vuoro:work.read`, `vuoro:evidence.record`; tools `list_ready_work`, `describe_work`, `register_run`, `append_evidence`, `write_session_note`. `vuoro:effect.propose` reserved (commented out), `vuoro:effect.apply` rejected forever (`oauth_scopes.py` L20-73). |
| Docs | `docs/*.md` in the repo; four static HTML concept pages | No docs site, no generator, no `llms.txt`, no per-generation versioning, no MCP tool reference (survey: no mkdocs/docusaurus/sphinx/vitepress/hugo anywhere). |

---

## 1. Workflow experience today

Surfaces used, abbreviated: **T** terminal (operator's shell), **Y** YubiKey, **DC** browser devtools console on `api.vuoro.cloud`, **DB** `vuoro.cloud/dashboard`, **CA** claude.ai UI, **GH/FJ** GitHub / Forgejo web or API, **WG** WireGuard + kubectl (+ psql), **SP** scratchpad markdown, **CH** agent chat relay (operator types a result back to the agent).

### 1.1 Release and promotion of a vuoro-cloud generation

| # | Step | Surface | Evidence |
|---|---|---|---|
| 1 | Agent merges code PRs and cuts `vuoro-service` release (tag, ghcr image); operator re-grants merge/publish/deploy approval **once per session**, it does not carry over | GH/FJ, CH | handoff 09-26 v2:24; 09-24 v1:24 |
| 2 | Agent pins four `apps/*` manifests to the digest; classifier has blocked this as `[Production Deploy]`, operator pastes `!` command | T, CH | 09-24 v3:8 |
| 3 | Operator runs `scripts/promote-release.sh <digest> <gen>` on clean main: PIN + two touches; agent hands it over marked "RUN NOW" | T, Y | 09-26 v2:28; 09-23 v6:27 |
| 4 | Agent dispatches promote-deployment via raw Forgejo API (`fj actions dispatch` returns 500); sometimes classifier-blocked, then operator `!` | FJ, T, CH | 09-23 v6:60; 09-24 v1:41 |
| 5 | Verification: `nmcli connection up vuoro-cloud-operator`, kubectl imageIDs/readiness, tunnel down | WG | 09-25 v1:34 |
| 6 | Evidence written by hand into IMPLEMENTATION-STATUS / handoff | SP | H1-8 in #253 |

Seven or more promotions in five days (36/37 botched by an early preview, 38, 39, 40, 44, 45, 47). Each has two operator interruptions minimum (approval re-grant, YubiKey) and usually a third (classifier paste or verification relay).

### 1.2 Tenant workspace roll (after every runtime release)

| # | Step | Surface | Evidence |
|---|---|---|---|
| 1 | Agent writes a `fetch()` snippet: `PATCH /api/control/v1/workspaces/{id} {"desired_state":"READY"}` with `X-CSRF-Token` read from the `vuoro_csrf` cookie | CH | 09-26 v2:8; `operator-actions.md` L171-175 |
| 2 | Operator opens an `api.vuoro.cloud` tab and pastes into devtools console. An expired session gives a 401 with no re-sign-in prompt; operator must detour via `vuoro.cloud/dashboard` to refresh the cookie | DC, DB | first-hand 09-26/27 |
| 3 | Operator relays the status line ("200") back | CH | audit 09-26 07:41 raw_tail |
| 4 | Agent watches the migrate Job and the pod image (kubectl over WG), then `claude mcp list` | WG, T | same |

Roughly 3 in the window (one done: kotona → 0.1.74 / gen 3; one carried through two handoffs; one planned after gen 47). Every roll needs the console paste **and** a kubectl verification, because the dashboard shows `state` but not the running image, the workspace generation, or the migrate Job outcome.

### 1.3 Dispatching cloud work

| # | Step | Surface | Evidence |
|---|---|---|---|
| 1 | Brief written to `scratchpad/brief-*.txt` | SP | S2 `brief-2519.txt`, `brief-e2-*`, `brief-e3-fixup*`, `brief-admin-identity-design.txt` |
| 2 | `claude --cloud "<brief>"` from the target repo checkout, wrapped in `script -qec` for a pseudo-TTY | T | S1 `CLOUD-RUNS.md`:9-18 |
| 3 | First eight dispatches on 09-26 were Routines by mistake and billed the five-hour window, found only via `get_session` | CA | `CLOUD-RUNS.md`:7, 26-33 |
| 4 | Operator relays the `claude.ai/code/session_…` URL, or attaches a repository to the cloud session after a push 403 | CA, CH | audit 09-26 12:51, 17:59; memory `cloud-session-repo-sources.md` |
| 5 | Results arrive as GitHub PRs; for vuoro-cloud they are hand-carried to Forgejo (`git fetch github`, push, `fj pr create --repo`, CI, credctl ff-merge, close replica PR) | GH, FJ, T | 09-26 v2:8, 26; `CLOUD-RUNS.md`:22 |
| 6 | Run inventory maintained by hand | SP | `CLOUD-RUNS.md`:24-33 |

About 14 dispatches in the window. Nothing in the substrate records them: `workflow.session` and `dispatch.exit` audit events cover local subagents only.

### 1.4 Reviewing and merging

- Independent review subagents post GitHub reviews; the agent's Forgejo token **cannot** post reviews on Forgejo PRs, so vuoro-cloud reviews live on the GitHub replica or in scratchpad (`pr128-review.md`).
- Merges are credctl ff-only after CI on the head sha. About 3-5 merges in the window needed an operator paste after a classifier denial (#119, the #102-105 bookkeeping call that then returned 405, a combined push). Denials are inconsistent with granted approvals (09-26 v2:25; 09-24 v5:25).
- Memory rule: any commit the agent authors needs an independent review posted on the PR before merge — currently impossible for Forgejo-only PRs from the agent's identity.

### 1.5 Other operator actions

| Action | Surface | State |
|---|---|---|
| Revoke drill PAT and two test grants (`DELETE /tokens/{id}`, `/grants/{id}`) | DC | pending since 09-25, carried three days (`OPERATOR-ACTIONS.md`:33-39; 09-25 v1:77) |
| Mint PATs and invitation codes | T (operator's own, never `!`) | 09-24 v5:27 |
| OAuth grant for the isolation proof (PKCE loopback) | browser | 09-24 v5:74 |
| Register the claude.ai connector; create a Routine in the web UI because the schedule API cannot attach Vuoro | CA | 09-25 v1:45, 54 |
| SOPS clients-file rewrite (agent denied `[Secret-Store Writes]`) | T | 09-25 v1:53 |
| NOLOGIN on six legacy roles | psql | 09-24 v1:43 |
| Reinstall local sprintctl (`uv tool install`, failed on agent's syntax) | T | `OPERATOR-ACTIONS.md`:21-31 |
| Operator to-do list | SP | `OPERATOR-ACTIONS.md` is the de facto inbox |

### 1.6 Incident and verification checks

Pod imageIDs, restarts, `/mcp` 401, token endpoint `invalid_client` (09-26 v2:6): all kubectl/curl over WireGuard. `kubectl exec`, drain, `talosctl reboot`, bulk pod delete are operator-only (09-24 v1:56). Backups are CNPG `Backup` CRs created over WireGuard. `/operator/rollout/status` exists but is only visible from `/admin` with the pasted operator bearer.

### 1.7 Pain points ranked by frequency × cost

Frequency = occurrences in the 5-day window; cost = operator interruptions and context switches per occurrence (1 = a click, 3 = a device or a tunnel, plus 1 per relay).

| Rank | Pain point | Freq | Cost | Score | Root cause |
|---|---|---|---|---|---|
| 1 | Status/result relays typed back to the agent (console "200", command output, PR URLs) | ~17+ | 1 | 17 | No shared read model the agent and the operator both see |
| 2 | Classifier denials → operator pastes a command | ~8 | 2 | 16 | Effects and approvals are terminal-bound; approval does not persist across sessions |
| 3 | YubiKey promotion with agent-authored command handed over | 7 | 2 | 14 | Correct by design (signing stays with the operator) but preview/execution confusion has cost two generations |
| 4 | Per-session merge/publish/deploy approval re-grant | 5+ | 2 | 10 | No durable, scoped approval record |
| 5 | Workspace roll via devtools `fetch()` + CSRF cookie + kubectl verification | 3 | 4 | 12 | No roll action or roll status in the dashboard; no bearer path (admin design D4/slice 3 addresses the CLI side) |
| 6 | Cloud dispatch bookkeeping by hand; repo attach in claude.ai; wrong billing bucket | 14 | 1 | 14 | Dispatches are not runs in the substrate yet (E2/H1-3 changes this) |
| 7 | WireGuard + kubectl for every verification | ~10 | 3 | 30 raw, but shared with #5/#1 | Controller-observed state is not exposed to any UI |
| 8 | Revocations pending for three days | 3 | 3 | 9 | Only reachable from a browser session; no list/revoke UI |
| 9 | Session expiry with no re-auth prompt | 2 | 2 | 4 | App shell treats 401 as an error string |
| 10 | Forgejo review cannot be posted by agent token; GitHub→Forgejo hand-carry | 5 | 2 | 10 | Identity/permissions on Forgejo; out of scope for the web, noted for H3-1 |
| 11 | Runbook drift (`fj actions dispatch`, promote printout) | 2 | 2 | 4 | Docs are not verified against what actually runs |

Reading of the table: the biggest single lever is a **shared read model** (rank 1, 5, 6, 7, 8 all collapse into "the operator and the agent can both see fleet, roll, run, and pending-action state on vuoro.cloud without a tunnel or a relay"). The second lever is **moving user-plane writes that already have routes into the dashboard** (rank 5, 8, 9). The third is documentation that is generated and checked (rank 11, and onboarding).

---

## 2. Target experience: vuoro.cloud as the primary endpoint

### 2.1 Principles

1. **TS-16 is the floor.** Cloud callers (claude.ai, Routines, cloud sessions) reach only the `/mcp` surface with read/coordinate/record/propose tools. The web is a *human* surface authenticated by browser session; it never becomes a path through which a cloud caller applies an effect, and it never proxies MCP calls with elevated authority. Effect *acceptance* remains a trusted-side act (`2026-09-26-cloud-enablement-plan.md` §Effects).
2. **User plane on vuoro.cloud, admin plane on the protected horizon.** Anything the admin-identity design puts behind WireGuard + WebAuthn (admin mutations, principal lifecycle, backups, intent acceptance by the operator) is *shown* on vuoro.cloud and *performed* on `vuoro-shared`/`vuoro-self-hosted`. vuoro.cloud deep-links to the protected action and shows the exact CLI command (the #253 "show the command, do not run it" rule, extended: show it *and* link to where it can be run).
3. **Every action card has the same three renderings**: the button (when the route is user-plane and session-authenticated), the `vuoro-cli` command, and the raw HTTP call. The agent and the operator read the same card, so relays disappear.
4. **Observed state beats reported state.** The controller's view (running image, generation, Job outcome, pod readiness, canary) is exposed as read routes and rendered; kubectl becomes the exception.
5. **Retire the pasted operator bearer in the browser.** The current `/admin` pattern (static shared secret in `sessionStorage`) is not extended; it is replaced by the admin principal when slice 1 of the admin design lands, and until then `/admin` stays read-only.

### 2.2 Screens and flows

| Screen | Purpose | Data | Writes allowed on vuoro.cloud | Requires protected horizon / step-up |
|---|---|---|---|---|
| **Home / inbox** (`/`, signed in) | The operator's required actions, replacing `OPERATOR-ACTIONS.md`: rolls due (runtime pin newer than workspace generation), revocations due, bootstrap approvals waiting, proposed intents (from H2-3's `proposed_intents` bucket), promotions awaiting signature, stale sessions. Each item is an action card (§2.1 rule 3). | control DB + controller read model + intent store (H1-1) | Cards whose route is user-plane (roll, revoke token/grant/session, approve bootstrap) | Intent accept/reject, promotion, principal ops: link out |
| **Fleet & rolls** (`/workspaces`, `/workspaces/{id}`) | Per workspace: desired vs observed state, workspace generation, pinned runtime vs running image digest, last migrate Job (status, duration), pod readiness, canary result; roll timeline. Fleet view is the web form of H1-7's drift report. | controller observations (new read route), `rollout/status` | `Roll now` = existing `PATCH` with confirm dialog and generation diff | none for roll; drain/migration retry (operator routes) link out until admin plane |
| **Runs & evidence** (`/runs`, `/runs/{id}`) | Runs registered via `register_run`, their evidence and session notes, the `Vuoro-Run:` trailer → PR link, runtime/model/profile revision. Run detail is the web form of H3-2; the list is H3-5's "last 20 runs" pane. Also lists cloud dispatches once they register runs (§4 item 7). | E2 store in the tenant runtime | none (record class is MCP-only) | none |
| **Intents** (`/intents`) | Effect-intent acceptance queue: proposed/accepted/rejected/applied, who proposed (run id, principal), diff summary, the exact `accept` command. | H1-1 store | **none** (read-only by TS-16; #253 rejected a browser write path) | accept/reject on the protected horizon (credctl / `vuoro admin intent accept`) |
| **Approvals** (`/approvals`) | Unifies what exists piecemeal: bootstrap sessions (`/activate`), membership invitations, connector enrollments, OAuth consents, invite requests. | existing routes | Bootstrap approve, membership accept/PATCH, connector PATCH (all user-plane) | Invite-request "invited" and invitations: admin plane |
| **Releases** (`/releases`) | Per generation: signed tag, digest, report card (`release.py build_report_card`), compatibility manifest, rollout status, which workspaces are on it, changelog (links to docs §3). "Promotion awaiting signature" card shows the exact `promote-release.sh` line and the precondition (clean main at sha) — the fix for the poc.36/37 early-run incident. | release metadata (new read route), `bootstrap/manifest`, `rollout/status` | none | signing on operator terminal (unchanged) |
| **Tokens & grants** (`/workspaces/{id}/access`) | API tokens (create/rotate/revoke), OAuth grants (list/revoke), sessions (list/revoke/logout-all), connectors. Closes GETTING-STARTED's "no dashboard view yet" and the three-day revocation backlog. | existing routes | all (user-plane, owner/admin) | none |
| **Audit** (`/workspaces/{id}/audit`) | `audit-events` with filters; later the hash-chained admin audit (admin design D7) as a read-only mirror. | existing route | none | none |
| **Status** (`/status`, public subset) | Health of control, gateway, MCP edge, canary, last backup observation; operator subset shows rollout state. Replaces the "is it up" kubectl checks. | `/health/*`, `rollout/status`, backup observations | none | none |
| **Docs** (`/docs`) | §3. | built artifact | none | none |

Cross-cutting UI behaviour: 401 anywhere → in-place "session expired, sign in again" with return path (fixes rank 9); `Idempotency-Key` on every write (already used for workspace create); every list is agent-readable as JSON at the same route with `Accept: application/json`, so the agent can quote what the operator sees instead of asking.

### 2.3 Division of labour between surfaces

| Concern | MCP / Claude (cloud callers and local harness) | Web (vuoro.cloud) | CLI (`vuoro-cli`, admin design D4) | Protected horizon (`vuoro-shared` / self-hosted) |
|---|---|---|---|---|
| Read work, describe, evidence | `list_ready_work`, `describe_work`, docs tool (§3.6) | Runs, fleet, intents, releases pages | `vuoro work ls`, `vuoro run show` | — |
| Record | `register_run`, `append_evidence`, `write_session_note` | read-only mirror | `vuoro run register` (trusted side, cred-broker-minted token) | — |
| Propose effects | `propose_effect`, `get_effect` (E3) | queue view | `vuoro intent ls` | **accept / reject** (operator via credctl or `vuoro admin intent accept`, WebAuthn) |
| User-plane management | — | buttons: roll, revoke, approve, bind repo | `vuoro workspace roll --wait`, `vuoro token revoke` | — |
| Admin-plane management | — | show + link | `vuoro admin …` | principal lifecycle, epoch bump, drain/migration, backups, service controls |
| Release promotion | — | awaiting-signature card, post-promotion verification | `vuoro release status` | `promote-release.sh` with YubiKey (unchanged) |
| Secrets | never | never | never in the browser; CLI holds PKCE tokens only | cred-broker |

### 2.4 Where step-up or the protected horizon is required

- **Always protected horizon:** intent acceptance, principal create/retire, epoch bump, drain/migration start, service-controls PATCH, backup CRs, SOPS/secret writes, release signing. These are exactly the admin-plane mutations of the admin design; the web only renders their state.
- **Step-up on vuoro.cloud (Assumption, to be decided with the split-horizon memo):** owner-level user-plane writes that are destructive (`desired_state: DELETED`, `logout-all`, revoking the last owner's token) should require a re-authentication within N minutes. GitHub OAuth re-prompt is the only factor available on the user plane today; WebAuthn is reserved for the admin plane. Recommendation: fresh-session check (re-auth within 10 minutes) now, WebAuthn for users later if external tenants need it.
- **Never on vuoro.cloud:** any control that would let a cloud caller cause an effect, including a "run this intent" button, a token minting UI for agent principals, or a proxy that forwards MCP calls with the browser session's authority.

---

## 3. Documentation and knowledge library on vuoro.cloud

### 3.1 Audiences

1. **The operator** (today's only user): runbooks that match what actually runs, per-generation changelogs, the exact command for every action card.
2. **Agents via MCP**: a tool reference generated from the live tool list and scope map, concept pages in agent-readable form, runbook steps retrievable as a tool result so a cloud session does not have to be handed a pasted snippet.
3. **Future external tenants**: getting started, connect-a-client, mental model, service reference, security posture, what Vuoro will never do (the TS-16 statement is a product commitment worth publishing).

### 3.2 Content types and their sources of truth

| Type | Source of truth | Generated? |
|---|---|---|
| CLI reference | `vuoro-cli` command tree (admin design D4) | yes, `vuoro --help-json` → pages |
| MCP tool reference | `oauth_scopes.py` `MCP_TOOL_SCOPES` + `GRANTABLE_SCOPES` (scope, tool, class read/coordinate/record/propose) joined with the tenant runtime's `tools/list` output (schemas, descriptions) | yes; CI fails on drift between the two |
| Scope and role reference | `oauth_scopes.py` role→authority map | yes |
| Service/API reference | FastAPI `openapi.json` from control (currently blocked at the edge as internal; the build step reads it in-cluster or from the image, not from the public edge) | yes |
| Runbooks | `docs/runbooks/*.md` in vuoro-cloud, `docs/runbooks/*.md` in agentops for the substrate side | no; command blocks carry a `verify:` annotation executed in CI where safe (§4 item 11) |
| Concepts | existing `apps/web/site/*.html` content, TS-16, the mental-model pages | migrated to Markdown source, rendered |
| Changelog per generation | release report card + signed tag + PR list between tags (Forgejo API) | yes |
| Evidence index | `docs/evidence/**` pointers (links, not copies) | yes (index only) |

### 3.3 Pipeline (docs-as-code)

- Source lives in the repos (`vuoro-cloud/docs`, `agentops/docs/runbooks`), no separate docs repo.
- Build: a `scripts/build-docs.py` step in vuoro-cloud CI: collects Markdown, runs generators (tool/scope/openapi/CLI/changelog), renders with a small static generator (recommendation: MkDocs Material or Zola, both single-binary-friendly and support versioned output; decision not needed before the pipeline shape is accepted), emits `site/` plus `llms.txt`, `llms-full.txt`, and a JSON index for search.
- Ship as an OCI image `vuoro-docs` (Chainguard nginx + `site/`), digest-pinned in `apps/docs/` like the other apps; the current ConfigMap approach cannot hold a real site (1 MiB limit).
- Route: cloudflared `vuoro.cloud/docs/*` → `vuoro-docs:8080` (path-based route in `platform/cloudflared/deployment.yaml`), or `vuoro-web` nginx `proxy_pass` to `vuoro-docs`; the former keeps CSP simple.
- Promotion: docs image rides the same generation promotion as control/gateway, so `/docs/` always matches what is live.

### 3.4 Versioning per generation

- URL scheme `/docs/` (= latest promoted generation) and `/docs/g<N>/` for each promoted generation; a version switcher reads `compatibility.json`'s `runtime.generation`.
- Runbooks are versioned with the code they operate; the changelog page links "what changed for operators" between generations.
- Retention: keep the last five generations plus any generation a workspace is still on (fleet read model tells the build which).

### 3.5 Search

- Client-side index (Lunr/Pagefind) built into the image: no server, no third-party, works under the existing CSP (`script-src 'self'`).
- The same index file is served as JSON so the docs MCP tool (§3.6) can answer `search_docs` without a second indexing path.

### 3.6 Agent-readable forms

- `llms.txt` (curated map) and `llms-full.txt` at the docs root; per-page `.md` alongside `.html`.
- MCP: a read-class `search_docs(query, generation?)` tool and `docs://<generation>/<path>` resources on the public `/mcp` surface, under `vuoro:work.read` (or a new `vuoro:docs.read` if we want it grantable to any client, Assumption: `work.read` is enough for now). Both are read-only, served from the built index, and contain no secrets by construction (docs build fails if a `sops`/token pattern is found).
- Action cards on the web link to the runbook anchor; the agent's `describe_work` output carries the same anchor, so both sides read one text.

### 3.7 Hosting in the cluster

`vuoro-system` namespace, `vuoro-docs` Deployment (nginx, read-only root FS, same security log format as `vuoro-web`), fronted by cloudflared path route; image built in CI and pinned in `apps/docs/kustomization.yaml`; no runtime dependency on control or the DB (a docs outage never blocks the operator from reading how to fix an outage).

---

## 4. Proposed backlog items

Sizes: S ≤ 1 day, M ≤ 3 days, L ≤ 1 week. Dispatch fit: **cloud** = cloud session / Routine can do it end to end (code + PR, no credentials); **local** = needs cluster or secrets; **operator** = needs signing or admin plane.

Not proposed here because they are already covered: fleet drift report (H1-7), pending intents in `next-work` (H2-3), onboarding gaps 1-5 (H2-6), settlement pane (H3-5), provenance resolver (H3-2), `vuoro-cli` and the admin plane (admin design slices 0-7), second IdP (H2-8), multi-repo MCP (#2518), status doc reconciliation (H1-8).

| # | Title | Problem (evidence) | Outcome | Repos | Depends on | Size | Security notes | Dispatch fit |
|---|---|---|---|---|---|---|---|---|
| 1 | **Dashboard access panel: tokens, grants, sessions with revoke** | Revocations pending three days because they need a devtools `fetch()` (`OPERATOR-ACTIONS.md`:33-39); GETTING-STARTED L150 says "no dashboard view yet" | Owner/admin can list and revoke tokens, grants, sessions from `/dashboard`; every card shows CLI + HTTP equivalents | vuoro-cloud (`apps/web`) | none (routes exist) | M | User-plane only; CSRF header from cookie as today; confirm dialog; no operator bearer | cloud |
| 2 | **Roll action and roll status in the dashboard** | Rolls are console pastes plus kubectl verification (§1.2) | `Roll now` button (existing `PATCH`) with generation diff and confirm; workspace page shows generation, pinned vs running image, migrate Job state, readiness | vuoro-cloud (`controller.py` read model + route + `apps/web`) | controller exposes observations (new read route); H1-7 shares the data | L | Read route is browser-session, workspace-scoped; no cluster credentials leave the controller | cloud for UI; local for the controller route verification |
| 3 | **Session-expiry handling in the app shell** | Expired cookie → silent 401, operator detours via `/dashboard` (§1.2 step 2) | Any 401 renders an in-place sign-in with return path; `/auth/session` probed on load | vuoro-cloud (`apps/web`) | none | S | Return path allowlisted to known routes | cloud |
| 4 | **Operator inbox on vuoro.cloud** | To-dos live in scratchpad markdown; agent asks for relays (§1.7 rank 1) | Signed-in home lists required actions with action cards; JSON at the same route for the agent | vuoro-cloud | items 1-2; H2-3 for intents; admin design slice 1 for admin cards | L | Inbox is derived, never stores secrets; admin cards are links only | cloud |
| 5 | **Releases page with "awaiting signature" card** | poc.36/37 botched by an early preview; promotion command handed over in chat (09-23 v6:27) | `/releases` shows generations, report card, rollout status, precondition (clean main at sha) and the exact `promote-release.sh` line; post-promotion verification without kubectl | vuoro-cloud (`release.py`, new read route, `apps/web`) | `rollout/status` moved to a session-authenticated read | M | Signing stays on the operator terminal; page is read-only | cloud |
| 6 | **Approvals page unifying bootstrap, membership, connector, consent** | Approvals scattered over `/activate`, terminal, claude.ai (§1.5) | One list; user-plane approvals are buttons; admin-plane ones link out | vuoro-cloud (`apps/web`) | none for user-plane | M | Same auth as today per route | cloud |
| 7 | **Cloud dispatch ledger: every `claude --cloud` dispatch registers a run** | 14 dispatches tracked by hand in `CLOUD-RUNS.md`; wrong billing bucket found late | The agentops dispatch wrapper calls `register_run` (E2) with session id, brief digest, target repo; `/runs` lists them | agentops (`scripts/`), sprintctl | E2 tools live (already on main), H1-3 | S | Token is the trusted-side agent token; cloud session never receives it | local |
| 8 | **Docs site pipeline and `vuoro-docs` image** | No docs site, runbook drift (§1.7 rank 11) | `scripts/build-docs.py`, static site with search, `llms.txt`, image pinned in `apps/docs/`, cloudflared path route, `/docs/` and `/docs/g<N>/` | vuoro-cloud | none | L | Build fails on secret-pattern hits; image read-only; no runtime deps | cloud for build; local for route + promotion |
| 9 | **Generated MCP tool, scope and role reference** | Tool surface documented nowhere; scopes only in code comments | Generator joins `oauth_scopes.py` with `tools/list`; CI drift check; page + `llms.txt` section | vuoro-cloud | item 8 (or emits Markdown into `docs/` before the site exists) | S | Reads code and the runtime image, not the live edge | cloud |
| 10 | **Docs MCP tool and resources (`search_docs`, `docs://`)** | Cloud sessions are handed pasted runbook snippets | Read-class tool under `vuoro:work.read` returns page excerpts and anchors from the built index | vuoro-service (tenant runtime), vuoro-cloud (`MCP_TOOL_SCOPES`) | items 8-9; H1-5 conformance suite must include it | M | Read-only; index built from vetted docs; rate-limited like other read tools | cloud |
| 11 | **Runbook command verification in CI** | `fj actions dispatch` runbook line wrong for a week; promote printout fixed in #95 | Command blocks annotated `verify: dry-run|help|skip`; CI executes the safe ones against the image | vuoro-cloud, agentops | none | S | Only `--help`/`--dry-run` classes run; no credentials in CI | cloud |
| 12 | **Per-generation changelog generation** | Operators reconstruct "what changed" from PR lists and handoffs (H1-8 is a one-off fix) | Build step lists merged PRs between signed tags plus report-card deltas into `/docs/g<N>/changelog` | vuoro-cloud | item 8 | S | Forgejo read token in CI only | cloud |
| 13 | **Status page** | "Is it up" needs WireGuard (§1.6) | `/status` public subset (health, canary) and signed-in operator subset (rollout, last backup observation) | vuoro-cloud | Phase 4 synthetic canary for the canary tile | M | Public subset exposes no hostnames beyond the two already public | cloud |
| 14 | **Retire the pasted operator bearer in `/admin`** | Shared static secret in `sessionStorage` (§0) is the pattern items 1-6 must not extend | `/admin` becomes read-only and moves its reads to session-authenticated operator-role routes; writes wait for admin design slice 1 | vuoro-cloud | admin design slice 1 for the replacement | S | Removes a browser-held long-lived secret | cloud |

Suggested order: 3 → 1 → 9 → 11 → 2 → 8 → 5 → 4 → 7 → 10 → 6 → 12 → 13 → 14 (14 moves earlier if the admin design lands first). Items 3, 1, 9, 11 are a single cloud wave with no cluster dependency.

---

## 5. Rejected ideas

| Idea | Why not |
|---|---|
| Accept/reject effect intents from vuoro.cloud | Acceptance is the trusted-side act that makes TS-16 hold; #253 already rejected a browser write path for effects, and the admin design places admin mutations behind WireGuard + WebAuthn. The web shows the queue and the command. |
| Promote a release from the browser (WebAuthn-signed tag) | Git tag signing with the card is the property being protected; browser WebAuthn produces an assertion, not an OpenPGP/SSH signature over the tag. Keep `promote-release.sh`; give it a better "awaiting signature" card instead (item 5). |
| Embedded terminal / kubectl or psql proxy in the web | Puts cluster credentials behind a browser session on the public horizon; the correct fix is exposing observed state as read routes (item 2) and doing the rest over WireGuard. |
| Extend the pasted operator-bearer `/admin` console with more actions | A shared static secret in `sessionStorage` with no per-person attribution; the admin design replaces it. Item 14 shrinks it instead. |
| Web proxy for MCP calls with the browser session's authority | Would make the web a path by which a browser (and anything driving it) reaches tools with elevated scope; violates §2.1 rule 1. |
| Embedding a chat agent in the dashboard | The primary agent surface is claude.ai / Claude Code with the connector; a second agent surface with its own credentials doubles the attack surface for no workflow gain today. |
| A separate docs repository or docs SaaS | Source of truth must stay next to the code so generation and versioning follow the release; SaaS breaks CSP, privacy stance and the "docs never depend on a third party during an incident" property. |
| Hand-written MCP tool reference | Drifts immediately; generate from `oauth_scopes.py` + `tools/list` (item 9). |
| Live WebSocket/SSE fleet updates in v1 | The 10 s poll already in `app.js` is adequate for a one-tenant fleet; add push when the fleet view has more than a screen of rows. |
| "Override classifier" button in the web | The auto-mode classifier belongs to the harness, not the substrate; a web override would be a new effect path. The durable fix is scoped approvals recorded trusted-side (out of scope here, noted for the telemetry/audit companion). |
| Storing operator to-dos as a table the agent writes to | The inbox must be *derived* from state (rolls due, revocations pending) so it cannot drift from reality and no cloud caller can plant an item. |
| Separate `docs.vuoro.cloud` hostname | Adds a cloudflared route and CSP origin; `/docs/` under the same host keeps one origin and one session. |

---

## Verification notes

Read-only pass. Claims about routes, scopes and the web shell were checked against `origin/main` of vuoro-cloud on 2026-09-27 (`git show origin/main:<path>`); workflow claims cite the handoff, audit or scratchpad line they come from. Frequencies are counts over 2026-09-23..27 and should be re-derived once operator actions are recorded as structured events (telemetry/audit companion).
