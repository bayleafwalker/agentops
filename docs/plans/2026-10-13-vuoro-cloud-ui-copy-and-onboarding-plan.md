---
doc_id: vuoro-cloud-ui-copy-and-onboarding-plan-2026-10-13
subjects: [vuoro-public-ui, vuoro-cloud-onboarding]
purpose: proposal
lifecycle: proposed
created: 2026-10-13
---

# Vuoro Cloud UI, copy and onboarding plan — 2026-10-13

**Status: planning proposal, implementation-ready slices; not deployment approval.**

Requested by the operator as a dispatched UI/copy planning pass. This document
changes no website, service, grants, rollout hold or release gate. It does not
establish current authenticated service readiness. Implement in the owning
`vuoro-cloud` repository after reconciling its canonical source with the observed
public assets. Preserve the ongoing Q4 and Cloud qualification work.

Companion: [Guide and knowledge entry site](2026-10-13-vuoro-guide-and-knowledge-entry-site.md).
This plan owns marketing/application navigation, interaction states, UI text and
accessibility. The companion owns guide information architecture, content,
search, hosting and maintenance. Neither adopts the older
[2026-09-27 UX/workflow proposal](2026-09-27-vuoro-cloud-ux-workflow-and-docs.md)
in full.

## Evidence and limits

Read the workstation and Cloud AGENTS/CLAUDE guidance and Cloud release gates;
`00-EXECUTIVE-DECISION.md`, `19-PRODUCT-POSITIONING-AND-PROOF.md`,
`IMPLEMENTATION-STATUS.md`, `docs/GETTING-STARTED.md`, and the historical
`docs/plans/2026-09-24-onboarding-ux-gaps.md`. These are tracked in the inspected
Cloud checkout, HEAD `3116a561c34453bdac2094282f95e2ca665882c4`.

On 2026-10-13, passive public HTTPS GETs returned 200 for
[the homepage](https://vuoro.cloud/), `/join`, `/dashboard`, `/activate`, `/admin`,
the four concept pages, `/showcase.html`, and their inspected scripts. `/docs/`,
`/bootstrap`, `/self-host`, `/faq` and `/contact` returned 404. FAQ/contact exist
as homepage sections, not those standalone routes. Python HTTP reads returned
403; curl succeeded, so the Python results are not a site-outage finding.
The web browsing tool could not open the site. No available browser rendered the
pages; no sign-in, form submission, commissioning, operator action or private
API call was performed. Authentication and live mutation outcomes remain
unverified. Dynamic findings below are source-derived and need browser fixtures.

The public homepage and `app.js` are newer than the local checkout: the live
homepage includes explicit effect-read consent; live application code includes
friendly status names, provenance/freshness facts, blockers and Claude/ChatGPT
connection instructions. Do not overwrite these improvements from the older
checkout. Public response-byte hashes, for reproducibility rather than deployed
image attestation:

| Public asset | SHA-256 |
| --- | --- |
| Homepage HTML | `afa4e91dd47852f3f7d50b9c20c673c13321b0f5ceab842811a262e6d334711f` |
| `/app.js` | `727c0b1da7f346f4a684b40f26699c8c4d7414aacd589836e1a69d0e8f6488e9` |
| `/landing.js` | `7d8dc6267014d99dfe0f34bdf38f198b9dcac0de28b31f339132772c63af2d89` |

Transient audit copies in `/tmp/vuoro-cloud-ui-public-20261013/` are session-local
references, not durable evidence. This tracked planning document contains public
UI observations and source references, not private fleet proofs or customer
records. Unrelated workspace changes are outside scope.

## Product contract for all replacement copy

Cloud operates a shared coordination boundary; customers retain their runners,
repositories, external credentials and artifact storage. The useful public
journey remains evaluate → inspect the bounded local proof → design an invited
pilot. An invitation is not a production-readiness claim. The complete takeover,
verification and dependent-work demonstration must not be described as a
recorded hosted proof until its owning qualification has passed.

Keep these distinctions explicit:

- A local Sprintctl reservation is advisory. It does not prevent another worker
  from acting or revoke external credentials. Hosted MCP `claim_work` uses a
  separate durable work-lease API where available; do not replace its genuine
  lease semantics with reservation semantics merely because an older product
  document discusses advisory reservations.
- Accepted under a named verification profile means that profile's requirements
  were satisfied. It does not mean general correctness or prevention of external
  effects. Profile definitions and their currently supported subset are distinct.
- Control-record readiness, client installation, current grant, reachability and
  permission to mutate are separate facts. A newer response timestamp is not a
  controller observation timestamp or an atomic fleet snapshot.
- A public acceptance preview is advisory. It grants no protected acceptance or
  execution authority. Q4 source publication must not appear as an activated
  browser approval feature.
- Bindings record repository identity and metadata; they do not clone a
  repository. Work descriptions and evidence can contain content a user chooses
  to submit, so avoid the absolute promise that Cloud can never see code.

Use maturity labels from the product contract: Preview, Internal operational
proof, Experimental, Design only or Blocked for external adoption, as applicable.
A release-date/source link must accompany demonstrated claims. Do not expose
private rollout, backup, database or operator proof details as public evidence.

## Page and flow inventory

| Surface | Observed/source behavior | Intended job | Plan |
| --- | --- | --- | --- |
| `/` | Public overview, capabilities, MCP tools, replay teaser, local transcript, modes, invitation form, FAQ | Help an evaluator choose a useful starting point | Shorten navigation; lead with purpose and bounded proof; distinguish capabilities from current availability |
| `/mental-model.html` | Settlement explanation, target takeover scenario, verification table | Explain what a reported result and accepted outcome mean | Separate reservations/work leases; show support/maturity for each profile row |
| `/architecture.html` | Authority and execution boundaries | Answer where state, execution and credentials belong | Retain diagram; link terms to the guide; avoid globally atomic/current claims |
| `/ecosystem.html` | Component/tool catalog | Explain owners after the user understands the task | Keep as reference; do not make all tools primary product choices |
| `/alternatives.html` | Routes people to narrower categories | Help evaluators avoid unnecessary complexity | Retain honest routing; date specific comparison claims and link primary sources when revised |
| `/showcase.html` | Historical PR/commit/tag replay plus illustrated lease takeover | Explain an operational history without claiming it was recorded by Vuoro | Keep recording/illustration labels next to controls; make text steps usable without animation |
| `/join` | GitHub entry; invitation form selected using a tab-local flow marker | Admit an invited person and route returning members | Resolve current session/admission separately; make code request, redemption and sign-in distinct |
| `/dashboard` | Workspace cards, refresh/progress, bindings, client instructions | Show availability and the next safe action | Preserve freshness improvements; add held states, keyed updates and reliable form feedback |
| `/activate?session_id=…` | Terminal commissioning form | Confirm a terminal-initiated repository credential request | Explain trust checks, eligibility, expiry and ambiguous outcome; show no effect-acceptance UI |
| `/admin` | Public shell asks for an operator bearer; implementation stores it in `sessionStorage` | Legacy operator console | Replace with safe private-operator instructions after native administrative parity is established; do not extend this credential pattern |
| `/docs/` | 404 on this pass | Task-oriented guide | Companion owns implementation; add navigation only when the route exists |

Do not add links to `/bootstrap`, `/self-host`, `/faq` or `/contact` as if these
routes exist. Use valid homepage anchors until separately implemented routes
have been qualified.

## Findings and prioritized implementation slices

### P0 — correct the actual first-use and held-state behavior

| Finding | Evidence | Concrete change | Acceptance |
| --- | --- | --- | --- |
| Maintenance does not gate connection guidance | Live `addConnection` checks READY, generation, repository count and configured clients, but not `maintenance_mode` | Put an availability decision before connection instructions. Maintenance blocks access guidance; read-only mode retains read guidance and hides mutation promises | READY/current-generation/maintenance fixture offers no connect/commission/write CTA; read-only fixture explains read access separately |
| DEGRADED is always named “Needs a repository” | Live `STATE_NAMES` maps every DEGRADED value to that text, despite other blockers | Use “Needs attention”; specialize to “Repository needed” only for `repository-required` | Migration/schema/unknown blockers never ask the user to bind a repository as their repair |
| `/join` confuses session state and invitation eligibility | Tab-local `vuoro_join_signin_started`; 401 and 403 both lead to “Signed in with GitHub” | Check the native session/admission responses on entry. Marker may track navigation only. 401 → sign in; confirmed unadmitted session → invitation; admitted member → dashboard; network error → explicit unknown | Fresh tab, returning member, expired cookie, denied admission and failed request fixtures each show one correct action; no marker authenticates a user |
| Polling rebuilds forms | `renderWorkspaces` clears the entire container every refresh | Key cards by workspace ID; patch status/repository facts, preserve forms/focus/open help. Serialize polling and ignore superseded responses | User enters a remote and keeps typing through refresh; values/focus remain. Older response cannot overwrite a newer view |
| Mutating forms can submit twice | Create and bind have no in-flight guard; create generates a fresh idempotency key for each submit | Disable only the submitted form while pending. Retain one create key for one intentional submission; do not automatically resend ambiguous POSTs | Double-click creates one client request; timeout retains inputs and instructs a status check; explicit new action gets a new key |
| Shared API errors lose useful meaning | `call` assumes JSON and keeps status/message but drops machine error code | Parse optional JSON safely; preserve bounded known code/status/request-reference metadata for UI mapping. Non-JSON/network failures get fixed useful text, not parse errors | HTML 502, offline, 401, 403, 409 and 429 fixtures render correct action; no raw body/token/stack is shown |
| Activation offers insufficient recovery/eligibility guidance | READY-only workspace filtering, free repository field, no eligible-workspace explanation | Filter on supported current availability/membership/binding facts. Disable approval until a valid choice exists. Explain missing/expired link, wrong code, no eligible workspace and uncertain result | Missing ID and no eligible workspace never display an actionable approval button; expired/wrong-code tests retain useful input; uncertain POST never auto-retries |
| Guide describes fixed historical bugs as current | GETTING-STARTED says no polling, no bound-repository list, quiet success and signed-out dead form; live script now implements them | Update the owner guide from current UI contracts alongside the UI slice; preserve dated historical evidence | Guide steps match a fixture/browser walkthrough; historical 2026-09-24 record remains marked historical |

The live app already implements several fixes from September: signed-out forms
are withheld, workspaces poll, repositories are listed, binding success is named,
and READY cards include client instructions and source timestamps. Preserve those
features; do not open duplicate implementation slices for them.

Generation equality should be exact when the protocol requires it. The live UI
currently accepts `observed_generation >= generation`; a greater value should be
an inconsistent/unknown record unless the owner explicitly documents that case.
Keep “control record says Ready” distinct from a successful client test.

### P1 — make public copy and the shell agree

1. Add **Sign in** as a stable navigation action for existing members. Suggested
   compact navigation: **How it works**, **Guide**, **Capabilities**, **Sign in**.
   Until Guide exists, its CTA points to the existing mental-model/local-proof
   section rather than a nonexistent route. Put Architecture, Ecosystem,
   Alternatives and Showcase in a secondary “Explore” grouping and the footer.
2. Rename **What's live** to **Capabilities in the invited alpha** unless the
   section has current service-owned availability evidence. A static feature list
   must not claim that every capability is functioning during a held rollout.
3. Rename **Run the local proof** to **Explore the local proof** while it points
   only to a recorded transcript. Provide a run instruction only after its exact
   installation/version path has been qualified in the guide.
4. Replace the application shell's duplicate old landing narrative with a small
   route-specific loading shell, one h1 and a useful no-JavaScript explanation.
   Page title follows the route: “Your workspaces — Vuoro”, “Redeem an invitation —
   Vuoro”, “Confirm terminal commissioning — Vuoro”. Keep a Home and Guide link.
5. Explain both Claude and ChatGPT through configured client metadata. Distinguish
   a configured provider from a person's current consent/grant. Avoid claiming
   that a named client is available just because the marketing page mentions it.
6. Label the verification-profile table with **currently supported** versus
   **definition / future qualification**. Keep the target scenario and historical
   replay honest; retain their dates and source limits.
7. Link a concise privacy notice beside the invitation form and from application
   pages. Preserve the existing consent and GPC/DNT behavior; expand no analytics
   payload with form text, repository URLs, invitation codes or credentials.

### P2 — useful account controls, with native owners and explicit dependencies

- Add grant/session management only against the existing native authorized read
  and revoke routes. Show workspace, client, actual scopes, last use and expired/
  revoked status; a supportable revocation action must name exactly what it
  revokes. Do not revoke broadly when reconnect instructions are sufficient.
- Retire public bearer entry at `/admin` after reviewing which invitation and
  analytics workflows have private-native parity. The immediate copy can direct
  operators to the private administration guide. Removal/migration is an owner
  change, not a cosmetic redirect that silently breaks invitation delivery.
- A commissioning request-summary read would let the browser display terminal
  repository/expiry details before approval. No such read endpoint was identified
  in the inspected source. Design the authenticated, minimal native read contract
  separately; never expose device codes, credentials or arbitrary bootstrap JSON.
- A public status view needs an explicitly sanitized native freshness contract.
  Do not infer operational health from a static release tag, web 200 or an image
  publication. Keep operator fleet/readout and protected approval out of the public
  horizon.

## Replacement copy

Use these strings as the initial implementation copy; preserve native error
codes in developer diagnostics without making users learn them.

| Location | Proposed text |
| --- | --- |
| Hero h1 | **Keep long-running agent work resumable.** |
| Hero body | “Track ready work, visible reservations, evidence and accepted outcomes across sessions. Your agents run in environments you control. Start with the bounded local proof; consider Cloud when several machines or hosted sessions need shared access.” |
| Hero primary / secondary | **Explore the local proof** / **Request a pilot invitation** |
| Returning member link | **Sign in to your workspace** |
| Capability section introduction | “These are the alpha's supported capability boundaries. Access also depends on your workspace, current grant and service availability. Each item states its maturity and qualification limits.” |
| Reservation/lease distinction | “Reservations show who intends to work on an item; overlaps remain visible. Hosted work leases are a separate API that checks the current lease generation when a report arrives. Neither revokes credentials to your external systems.” |
| Acceptance-preview explanation | “Inspect an advisory snapshot for one exact artifact. A preview does not approve or execute it. Protected approval happens through its separately authorized workflow.” |
| Repository/data boundary | “Binding records your repository ID and URL; it does not clone your repository. Descriptions and evidence you submit are stored with the workspace. Keep credentials out of those records.” |
| Empty workspace list | “No workspaces yet. Create a workspace for your pilot, then bind one repository before connecting an assistant.” |
| Slug help | “Use 3–49 lowercase letters, digits or hyphens, starting with a letter. Example: `agent-pilot`.” |
| Binding helper | “Choose a short repository ID used by your tools. Binding records the remote; it does not upload your repository.” |
| Binding success | “Repository `{repo_id}` is bound. The workspace will check the change before it becomes available to clients.” |
| Ready card | “The control record says this workspace is ready. Your client connection has not been checked here.” |
| Requested | “Workspace requested. Provisioning has not started yet. This card refreshes while progress is pending.” |
| Repository required | “Bind one repository to start the workspace runtime.” |
| Pending generation | “The latest change has not been observed by the controller. The previous Ready record does not confirm this change.” |
| Maintenance | “Workspace access is paused for maintenance. Your work is retained. An operator must finish the maintenance before clients can reconnect.” |
| Read-only | “This workspace currently allows reads. Changes and work reports requiring write access are paused.” |
| Migration/schema blocker | “An operator must complete or repair the tenant migration. Refresh status to check progress; rebinding the repository will not repair it.” |
| Unknown status | “Current availability is unknown. The owner did not provide a usable status. Refresh or contact the operator.” |
| Refresh failure | “Could not check current status. These cards show the last successful response from `{time}`. Refresh status to check again.” |
| No configured client | “No supported assistant client was included in this response. Ask the operator which client is enabled for your pilot.” |
| Multiple MCP repositories | “This MCP connection currently needs one bound repository. Your workspace has `{count}`. Ask a workspace administrator how to select the intended repository.” |
| Sign-in expired | “Your session has expired. Sign in with GitHub to continue.” |
| Invitation page | “Redeem an invitation. Sign in with GitHub first, then enter the single-use code you received. Already a member? Open your workspaces.” |
| Invitation failure | “This invitation cannot be redeemed. Check the code and ask the issuer whether it has expired or already been used.” |
| Creation/binding held | “This change is currently paused by the service. Your existing workspace records are retained. Check status or contact the operator.” |
| Create response uncertain | “We could not confirm whether the workspace was created. Refresh your workspace list before submitting another request.” |
| Activation introduction | “Only approve a commissioning request you just started in your terminal. Check the code there, then choose the intended workspace and repository. This issues access for that repository; it does not approve external effects.” |
| No eligible activation workspace | “No workspace is available for this request. It must be current, usable and allow your membership to commission access. Return to your workspace list or ask its administrator.” |
| Activation confirmed | “Commissioning approved. Return to the terminal to finish setup. No credential is displayed here.” |
| Activation uncertain | “Approval status is unknown. Return to the terminal to check whether commissioning finished. Do not approve again until that check completes.” |
| Non-JSON / transport error | “The service did not return a usable response. Check status and try the read again. A submitted change may need confirmation before another attempt.” |
| Invite-request success | “Request received. If the pilot is a fit and capacity is available, we will email an invitation. This is not an account or an access approval.” |

Held-state text must come from a native flag or a recognized refusal for that
operation. Do not label the whole fleet “paused” from one workspace's state or a
private operational note. Unknown stays unknown; no fabricated retry estimate.

## Onboarding and instruction sequence

1. **Choose the path.** Existing member → Sign in. Invitation in hand → Redeem.
   Evaluator without one → local proof/guide or pilot request. Do not make an
   existing member request another invitation.
2. **Create intentionally.** Show slug constraints before entry. Keep a pending
   submit visible; retain data on failure. A receipt that creation was requested
   is not a guarantee provisioning will finish in 70 seconds.
3. **Bind deliberately.** Keep the repository form available at the legitimate
   repository-required state. Confirm the bound repository ID and pending change.
   Never instruct rebinding as repair for an unrelated migration failure.
4. **Check availability.** Current generation, maintenance, read-only mode,
   membership and repository eligibility are distinct. Show the next useful step
   beside the state, with source/time details in a compact expandable region.
5. **Connect a configured assistant.** Show the copied endpoint and the provider's
   guide. Identify supported scopes versus the person's grant. Old grants do not
   widen on refresh; reconnect for fresh consent when required. Never paste client
   secrets or tokens into a chat, ticket, analytics event or generated command.
6. **Test through the real client.** For an installed CLI, show the already
   supported `vuoro-cli --version` and `vuoro-cli workspace list` as installation/
   login checks. A served `sprintctl doctor` success is a later explicit check using
   the qualified generated profile; do not invent an installation command or
   silently use a local database when served configuration fails.
7. **Recover using the owner.** Sign-in problems → GitHub/session guidance; missing
   scope → fresh provider consent; inactive workspace → status/operator guidance;
   ambiguous writes → read current state or return to the commissioning terminal.
   A generic Retry button must not resend a write blindly.

The companion guide must version runnable commands against their native owner
and actual supported package set. In-product hints should link to the relevant
step, not reproduce a second, drifting command reference.

## Visual and interaction direction

Apply the frontend-design skill's emphasis on intentional hierarchy, plain action
names and useful failure/empty states. Preserve the site's existing cool paper,
blue ink, yellow current-work highlight and restrained handover ledger. This is
an interaction/copy repair, not a brand redesign or a new product claim.

| Token/role | Existing starting point |
| --- | --- |
| Paper / surface | `#eef1f5` / `#f9fafc` |
| Text / secondary text | `#16213a` / `#46516b` |
| Current highlight | `#f5d547` |
| Refusal / accepted marker | `#a3242b` / `#1b6a47`, always paired with text |
| Type | Existing system serif headings, system sans body and mono only for commands/data |
| Layout | Left-aligned narrative and task panels; body measures about 60–75 characters; status details subordinate to the next action |

Bring the app shell into the same token system as landing/concept pages instead
of preserving its separate cream/green treatment. Keep the hero ledger as the one
memorable visual; badge rows do not replace explanations. Tables remain tables,
forms remain task-oriented and diagrams have equivalent text steps.

```text
Public header: Vuoro | How it works | Guide | Capabilities | Sign in
Hero: purpose + maturity + local proof / pilot request
Bounded proof: recorded behavior | target illustration | explicit gaps
Cloud: prerequisites + what it hosts + invitation request
Footer: concept references | guide | contact | privacy

Workspace card: name + availability + next action
               last successful source/time (expandable)
               bound repository + connect/read-only guidance
               preserved form and contextual feedback
```

Use user-triggered motion. Disable automatic replay by default, or retain only a
single clearly controlled reveal with pause/off-screen behavior and a complete
static alternative. Current showcase already respects reduced motion and quiets
live regions while playing; preserve those safeguards. Do not announce every
polling timestamp or every animation frame to a screen reader.

## Accessibility and browser validation

Acceptance criteria for each slice:

- One useful h1 and route title; skip link; primary and secondary navigation named
  correctly. Progressive no-JavaScript states direct users to the guide and explain
  which signed-in interactions need JavaScript.
- Keyboard access to every control, visible focus and logical focus after a route
  change, error or successful action. Polling never steals focus, clears input or
  closes an expanded instruction panel.
- Error summary is attached to the relevant form. Invalid fields use
  `aria-invalid` and `aria-describedby`; messages distinguish errors from progress.
  Button states use pending/disabled semantics without trapping focus.
- Minimum WCAG AA contrast: 4.5:1 normal text, 3:1 large text and essential controls;
  no color-only status. Validate both current light/dark palettes rather than
  assuming the token names guarantee contrast.
- Test at 320, 375, 768 and 1280 CSS pixels; 200% zoom; keyboard-only; reduced motion;
  missing/slow JavaScript; and one screen reader. Commands/tables may scroll in
  labelled regions, but core forms/navigation must remain usable without clipping.
- Replay offers text steps and keyboard controls, never requires precise scrubbing,
  and communicates historical replay versus illustration without color alone.
- Client calls use mocks for authenticated/write scenarios. A read-only public
  smoke test checks routes and links; actual pilot mutation/commissioning tests
  require a separately authorized disposable environment, never a production user.

Meaningful automated fixtures: signed out, unadmitted, expired session, no
workspaces, repository-required versus other DEGRADED blockers, active
provisioning, READY/stale/inconsistent generation, maintenance, read-only, one/
multiple/unknown repositories, missing client metadata, no commissioning
workspace, invalid/expired code, HTML 502, offline, 429, delayed out-of-order
responses, double submit, and response loss after a write. Force failure cases
before claiming their guards work.

Preserve and extend `tests/test_public_site.py` checks tying displayed MCP tools,
scopes and client restrictions to the actual gateway registry. Add assertions
that unsupported verification profiles carry their status and that no guide
link is introduced before its route exists. Do not weaken scope checks to make
copy tests pass. Test native payload contracts rather than inventing grants in
frontend fixtures.

## Ownership, sequencing and stop conditions

| Slice | Owner files | Dependencies | Stop condition |
| --- | --- | --- | --- |
| 1. Current-state/copy repairs | Cloud `apps/web/deployment.yaml` embedded app; state/browser tests; owner getting-started guide | Reconcile current canonical app with inspected newer public script | Held, stale, auth and error fixtures pass; existing freshness/client features preserved |
| 2. Form/poll behavior | Cloud app script and focused browser fixtures | Native error/idempotency contracts audited | No duplicated POST, input/focus loss or stale-response overwrite; uncertain writes remain uncertain |
| 3. Public hierarchy and maturity copy | Cloud `apps/web/site/landing.html`, concept pages, landing/showcase scripts/styles; public-site tests | Product intentions review; companion guide route only when ready | Clear path for evaluator/returning member; no stronger authority/durability/profile claim |
| 4. Commissioning UX | Cloud app + native bootstrap tests; minimal read contract only if separately accepted | Actual membership/availability contract, terminal flow | User can distinguish eligible, expired, confirmed and uncertain outcomes without browser secrets |
| 5. Guide linking and shell consistency | Cloud routes/assets + companion guide implementation | Guide source/hosting/CSP qualification | No dead routes, duplicated stale instructions or app-wide CSP weakening |
| 6. Legacy admin disposition | Cloud owner admin routes, private CLI parity and guide | Explicit parity/security review | Required invitation workflow still works; no new public privileged-action or bearer-storage surface |

A source review and qualified CI do not prove deployment. Cloud promotion still
uses its own release/hardware gates; neither this plan nor an ordinary source
merge resumes a held rollout. Finish implementation with product-intention review,
then qualify the actual published/static behavior and any authorized pilot flow.
Report remaining unknowns plainly. No commit, push, website change or deployment
was performed during this planning pass.
