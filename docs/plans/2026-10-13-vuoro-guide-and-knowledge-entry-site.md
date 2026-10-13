---
doc_id: vuoro-guide-and-knowledge-entry-site-2026-10-13
subjects: [vuoro-public-guides, vuoro-knowledge-entry]
purpose: proposal
lifecycle: proposed
created: 2026-10-13
---

# Companion guide and knowledge entry site for Vuoro

Status: **planning proposal; no implementation, publication or deployment**.
This responds to the operator's request to dispatch consideration of a guide /
knowledge entry site alongside the current vuoro.cloud. It complements the
[parallel UI/copy review](2026-10-13-vuoro-cloud-ui-copy-and-onboarding-plan.md). It does not change Q4 activation, held Cloud claims,
public authority boundaries or existing release gates.

Recommend a public **Vuoro Guide** at `https://vuoro.cloud/docs/`: a searchable,
version-aware starting point that explains what to try, how to perform common
tasks, what observed results mean, and where the authoritative contract lives.
Keep general product content in `vuoro`; keep Cloud onboarding and operational
content in `vuoro-cloud`; publish an allowlisted, pinned projection of both.
Do not turn the public guide into a new knowledge database or editable copy of
owner contracts.

## 1. Evidence and current gaps

Read-only source audit used local `vuoro-cloud` HEAD
`3116a561c34453bdac2094282f95e2ca665882c4` and local `vuoro` HEAD
`977d417368ecca2a35ec3572eec87e972a14e5de`. These are observed checkout revisions,
not assertions of current canonical branches or deployed images.

Sources read: shared and repository AGENTS; `vuoro-cloud/CLAUDE.md` guidance;
`19-PRODUCT-POSITIONING-AND-PROOF.md`, `00-EXECUTIVE-DECISION.md`,
`13-REPO-OWNERSHIP-AND-CHANGE-MATRIX.md`, `IMPLEMENTATION-STATUS.md`,
`docs/GETTING-STARTED.md`, `apps/web/{deployment.yaml,kustomization.yaml,site/}`;
`vuoro/README.md`, `site/index.html`, `.github/workflows/pages.yml`,
`packages/vuoro-knowledge/README.md`, `docs/architecture/knowledge-resolution.md`
and the September 29 settlement scenario evidence. Also read the historical
[September 27 UX/workflow/docs proposal](2026-09-27-vuoro-cloud-ux-workflow-and-docs.md)
and the binding [target-state direction](2026-09-17-target-state.md).

| Observation | Implication for the guide |
| --- | --- |
| Local Cloud nginx explicitly serves landing, five concept/showcase pages and app routes; no `/docs/` route or docs generator was found. `docs.css` styles concept pages, not a documentation library. | Add a distinct reading/search surface; do not claim an existing guide site. |
| Marketing HTML/CSS/JS lives in `apps/web/site`; app shell and app.js remain embedded in `apps/web/deployment.yaml`. | Guide links touch both source locations; avoid replacing app state with documentation controls. |
| General Vuoro has a separate raw static GitHub Pages overview in `site/index.html`. | Establish one canonical guide destination and cross-link the overview; do not start a third independent content fork. |
| Existing Cloud getting-started prose says there is no automatic refresh or bound-repository list. Companion planner's unauthenticated public GET of current app.js shows polling, bound-list and richer connector states. | Reconcile onboarding against current observed UI before publication; the old instructions are not an acceptable first guide. |
| Product positioning records, later scripted lease proof and current website copy are not fully aligned. | Distinguish dated evidence, current supported contracts and target scenarios. A docs launch cannot silently upgrade a public claim. |
| `vuoro-knowledge` already resolves Git content by identity, purpose, lifecycle, applicability and revision. Its source explicitly does not own publication/work state. | Reuse identities/provenance and owner references; add no parallel ratification or work state. |

Public web browsing could not fetch vuoro.cloud or the Vuoro GitHub Pages site;
that is **could not check**, not evidence of an outage. The companion UI planner
independently obtained successful unauthenticated public HTTPS GETs, shared the
exact retrieved HTML/app.js, and confirmed live/source drift. The inspected live
homepage advertises invitation-only alpha, an advisory `preview_acceptance`
read surface, the Sprintctl 0.7.3 local transcript, and version-specific hosted
connector leases. The companion public route inventory found `/docs/` returning 404; current
marketing, concept and app-shell routes returned 200. Current public GET is not
a deployment lineage or tenant capability qualification. No authenticated app, live tenant or cluster probe
was performed in this planning pass.

Reservations are advisory coordination records. Versioned hosted `claim_work`
leases are a separate owner contract; an explanation must not erase genuine
lease semantics or imply that advisory reservations are exclusive. Neither
allows a general promise that an old worker cannot affect an external system.

## 2. Audience and first useful outcome

| Audience | Job | Best first route | Success |
| --- | --- | --- | --- |
| Evaluator / individual developer | Decide whether Vuoro addresses continuity and settlement across existing runners. | Start → choose a path → bounded local proof. | Can explain what was proved and what remains unavailable without creating an account. |
| Invited Cloud workspace owner | Get a usable workspace and connect an eligible client. | Cloud → invitation to first successful read. | Understands workspace state, repository binding, membership, consent and next action; secrets remain in the supported setup flow. |
| Agent user returning after interruption | Find the current owner state and decide whether a prior result counts. | Guides → inspect before resuming. | Identifies item/run/revision and owning decision; does not substitute an old transcript or self-report for settlement. |
| Integrator / self-hosting operator | Find exact client/server compatibility, schemas and failure behavior. | Reference / operate. | Uses a supported pinned contract and can find migration/recovery boundaries. |
| Maintainer / support author | Publish a correction and identify stale guidance. | Source link / article metadata. | Makes one owner-repo change and rebuilds the public projection. |

External default journey remains **evaluate → bounded proof → bounded pilot**.
Invitation acceptance is an additional route for eligible users, not the
universal call to action. Private estate procedures remain owner-repo runbooks;
the public guide describes the boundary and routes an authorized operator to
the appropriate procedure.

## 3. Relevant current market patterns

These are information-design references, observed on 2026-10-13. They are not
evidence of Vuoro features or permission to reuse brand assets/text.

| Reference | Pattern to adapt | Fit and limit |
| --- | --- | --- |
| [Temporal quickstarts](https://docs.temporal.io/quickstarts) and [learning entry](https://learn.temporal.io/getting_started/) | Separate a local first exercise, later developer guides, and deployment choices. Give the exercise a concrete result. | Useful to Vuoro's local-first evaluation. Do not borrow Temporal's durable execution guarantees: Vuoro does not execute customer workflows. |
| [Restate documentation](https://docs.restate.dev/) | Distinct quickstart, concepts, task guides, examples, reference and hosting choice entry points. | Useful for a multi-surface developer product. Do not turn Vuoro's hosted coordination into a durable-execution/runtime claim. |
| [GitHub's Start your journey](https://docs.github.com/en/get-started/start-your-journey) | A short sequenced learning path expressed as user tasks. | Use for a small first-session path, not an encyclopedic feature index. |
| [Linear docs](https://linear.app/docs) and [start guide](https://linear.app/docs/start-guide) | Job-oriented groups and direct return to the app, plus popular tasks. | Suitable for work operators; keep protocol/domain names out of the primary navigation. Do not imitate unsupported issue-tracker features. |
| [Diátaxis](https://diataxis.fr/) | Distinguish tutorials, task guides, reference and explanatory concepts. | Use as the editorial rule; one page should principally serve one need. |

Use their clarity, task sequencing and explicit next steps. Author Vuoro's own
examples, diagrams, screenshots and language. A competitor screenshot is not a
Vuoro product mockup or reusable asset.

## 4. Information architecture and entry points

Top-level `/docs/` navigation: **Start**, **Guides**, **Concepts**, **Reference**,
**Operate**, **What's changed**. Audience, mode and maturity appear as page
metadata/filter choices, not six duplicate documentation trees.

| Section | Contents | Editorial shape |
| --- | --- | --- |
| Start | What Vuoro helps with; choose local/shared/Cloud; current availability; local proof; invited Cloud first session. | Short tutorials: prerequisites, bounded steps, observable finish, next lesson. |
| Guides | Resume after interruption; inspect a result; connect an eligible client; resolve consent/access problems; manage a workspace; revoke access. | Task guides: goal, prerequisites, supported path, check result, recovery/stop condition. |
| Concepts | Readiness/ownership/evidence/settlement; reservations versus leases; verification profiles; where effects and credentials stay; freshness/unknown states. | Explanations with small concrete cases; no installation steps or implied grants. |
| Reference | CLI commands, supported MCP tools/scopes, compatibility, states/errors, response schemas, glossary. | Exact and generated where possible, scoped to a release/profile. |
| Operate | Public self-hosting evaluation; upgrade/migrate; backup/restore boundaries; export and exit; links to authorized operator procedures. | Procedures owned by the component they operate; sanitized public subset only. |
| What's changed | User-visible changes, compatibility notices, retired procedures, proof records. | Dated records clearly separated from current instructions. |

Suggested initial routes include `/docs/start/choose-your-path/`,
`/docs/start/local-proof/`, `/docs/start/cloud-first-session/`,
`/docs/guides/inspect-before-resuming/`, `/docs/guides/connect-a-client/`,
`/docs/concepts/reservations-and-leases/`,
`/docs/concepts/results-and-settlement/`, `/docs/reference/mcp/`,
`/docs/reference/compatibility/`, `/docs/help/`.

Link contract:

- Marketing header: **Guide** → `/docs/`; local proof CTA → the bounded proof
  tutorial; Cloud CTA retains invitation flow and offers “Already invited?”
  onboarding beside it. Existing concept URLs stay valid through redirects or
  concise overview pages linking their detailed guide chapters.
- Dashboard/help: persistent **Help** linking to the relevant guide. Workspace
  state and connector cards deep-link to exact task anchors. Links carry no
  token, principal, workspace or private artifact data.
- Guide header: **Product overview**, **Open app**, **Help**. No sign-in is
  required to read it. App links navigate; guide pages do not call privileged
  APIs or act on behalf of the reader.
- Command errors may name stable public guide anchors alongside the existing
  safe error code. Introduce these in owner packages, not a universal wrapper.

Every article shows its audience, mode, maturity, applies-to contract/version,
last verified date and source revision. “Current guide” means a reviewed content
snapshot, not that every workspace runs the same generation. Unknown runtime or
permission state remains explicit.

## 5. First content backlog

These are implementation candidates, not newly created work items.

| Priority | Entry | Owner/source | Acceptance |
| --- | --- | --- | --- |
| P0 | Choose your path and current availability | Product decision + current disposition sources; `vuoro` | Local proof and invited Cloud paths are distinct; unsupported installation is not presented as working. |
| P0 | Read the bounded local proof | Existing Sprintctl 0.7.3 evidence plus maintained owner CLI recipe | Names exact release/backend and four observed outcomes; no full takeover or cross-harness claim. |
| P0 | Cloud: invitation to first successful read | Cloud UI, GETTING-STARTED, user CLI runbook | Reconciles current polling/binding/sign-in behavior; step outcomes are visible; current eligible clients are verified for the advertised generation. |
| P0 | Reservations, leases and external effects | Sprintctl contract + versioned MCP edge surface | Separate APIs and versions; no claim that either cancels external credentials/effects. |
| P0 | Inspect before resuming | Work/read/evidence owners and current connector catalog | Identifies current item, run, generation/revision and decision without inventing an execution or acceptance action. |
| P0 | Connect/reconnect an eligible client | Cloud OAuth/MCP contract | Explains scope/membership/generation eligibility and that refresh cannot widen a grant; secret values stay outside chat/screenshots. |
| P0 | Access/problem index | UI errors + CLI safe reason codes | Covers signed-out session, invitation, no eligible workspace, repository-required, wrong scope and compatibility failures with truthful next actions. |
| P0 | Generated MCP surface and compatibility | Released catalog/scopes + pinned composition | Every public tool maps to shipped code/fixture and maturity; excludes new Q4 protected routes and consumer execution. |
| P1 | Result reported versus owner-settled | Current owning decision contract | Uses named verification profiles and retained rejected evidence; unknown/missing proof is visibly unknown. |
| P1 | Revoke/rotate access | Cloud user CLI/control contract | Current role/scope prerequisites, confirmation and outcome; no pasted operator bearer pattern. |
| P1 | Public self-hosting evaluation and exit | `vuoro` deploy guides + Cloud compatibility | States evaluated paths, migration/backup constraints and export/uninstall instructions; not a production-support promise. |
| P1 | Glossary and proof library | Owner references + dated evidence | Separates observations/claims/current contracts; each proof names environment, dates and limitations. |
| P2 | Operator incident/restore subset | Cloud operator runbooks | Only reviewed public material, with private commands/identifiers omitted rather than silently copied. |
| P2 | SDK/integrator examples and version history | Owning protocol packages | Exact release-specific fixtures, supported examples, explicit supersession and redirects. |

Before publishing P0, create an inventory of existing article claims and classify
source drift. The later scripted September 29 lease scenario and MI-1 evidence
can be linked as dated proof records once their public projection is reviewed;
neither automatically replaces current public wording or closes held Cloud
or protected Q4 adoption gates.

## 6. Sample guide entry

The following is an original proposed entry. It is a content example, not a
verified command tutorial or a new runtime capability.

### Check the current state before resuming work

**For:** an agent user returning after interruption. **Mode:** use your supported
work-reading client. **Expected result:** know which owner state and evidence to
carry into the next attempt. **Maturity:** must be labelled for the actual
published client/contract profile.

A prior session saying “done” is useful evidence. It does not tell you whether
the work owner accepted the result or whether the next attempt owns the work.
Start with the current item, then read the record associated with that item.

1. **Find the exact item.** Open the same workspace and repository used by the
   previous attempt. Use the supported work-reading entry point; record its
   item identifier and the current revision. If you cannot verify that binding,
   stop and resolve access or compatibility first.
2. **Read the current ownership record.** Determine which contract applies:
   an advisory reservation or a versioned connector lease. A reservation does
   not exclude another worker. A lease generation in an old transcript does
   not establish the current generation.
3. **Check the owning decision.** Separate a reported success, stored evidence,
   completed checks and an accepted settlement. If a verification profile is
   named, read what that profile checked. Missing or unavailable decisions stay
   unknown; do not infer acceptance from an artifact's existence.
4. **Carry forward the references.** Keep the item/revision, run and evidence
   references that the current read returned. Follow the supported resume or
   reassignment guide for that specific contract. This reading step grants no
   repository, deployment or protected acceptance authority.

**Example:** attempt A produced an artifact, then a new lease generation went
to B. A's later report can remain visible as rejected evidence. It does not
settle the item for B. Read the owner decision before treating dependent work
as ready. This illustrates the versioned lease contract, not every reservation
or a universal external-effect guarantee.

**If the service cannot answer:** preserve the prior references and mark the
owner state unavailable. Use the documented recovery path for that mode. An
old local transcript is not a fresh served answer.

**Next:** Results and settlement · Reservations and leases · Access problems.
Production publication adds the exact supported command/tool and field names
from the generated reference plus a tested example for its compatibility set.

## 7. Navigation, search and agent-readable forms

Desktop: compact global navigation, grouped left sidebar, article body and
on-page contents. Mobile: one accessible navigation drawer, persistent search
entry, clear breadcrumbs and previous/next only within a tutorial sequence.
Use the current Vuoro visual identity but optimize article readability. No
nested wall of authority package names on the start page.

Search runs against the static public artifact. Results show title, section,
mode/version, maturity and a short excerpt; current supported instructions rank
before explicitly labelled historical evidence. Exclude private/operator-only
and proposal pages from the public search index. A search miss suggests glossary
synonyms and Help; it does not fabricate an answer. No third-party query
telemetry or privileged “ask an agent” action is required for launch.

Publish HTML plus per-article Markdown, a curated `/docs/llms.txt` and a small
machine-readable page manifest with doc_id, URL, revision, applicability and
source links. Existing `vuoro-knowledge` may consume the same canonical sources
and manifest under its established boundaries. Do not claim `llms.txt` makes
content authoritative. A future public docs MCP/resource surface is a separate
read-only contract decision; no workspace scope upgrade is implied here.

## 8. Build, hosting and maintenance

### Recommended implementation

Use an isolated static **Astro/Starlight** build under `vuoro-cloud/apps/docs/`,
with locked dependencies and an explicit public source manifest. Starlight
provides Markdown authoring/navigation and default Pagefind search; its official
[content guide](https://starlight.astro.build/guides/authoring-content/) and
[search guide](https://starlight.astro.build/guides/site-search/) support that
choice. This is a proposal based on the available tools, not an installed
repository dependency.

Do not assume it works under the existing web CSP unchanged. The current
Cloud web header has `script-src 'self'`. Pagefind's official
[hosting guidance](https://pagefind.app/docs/hosting/) says its WebAssembly
needs `wasm-unsafe-eval` and its default worker may need additional worker
policy. Build a docs-only policy with externalized initialization/theme scripts
or exact build hashes; use Pagefind's no-worker configuration if it avoids a
blob worker. Test the generated site, not only development mode. No general
`unsafe-inline` / `unsafe-eval` relaxation or app-wide CSP change is proposed.

Produce a digest-pinned static nginx docs image rather than putting a search
bundle and every article into Kubernetes ConfigMaps. Cloud already owns static
nginx/GitOps/public routing; a docs image avoids growing the existing projected
ConfigMaps into a documentation packaging system. Add `apps/docs` Deployment /
Service using the existing nonroot/read-only pattern. Route same-origin
`/docs/` to it before the general vuoro-web rule. Copy the generated files under
`/docs/` and build with that base path so no API or app rewrite is needed.
Keep docs serving independent of control, tenant state and authenticated APIs;
publish a downloadable static archive for offline incident reading. No new
hostname, paid docs service or separate editable content repository is needed.

### Source-of-truth and owner matrix

| Material | Canonical authoring owner | Public projection |
| --- | --- | --- |
| Product concepts, general tutorials, protocol/client contract | `vuoro/docs/public/` plus owning package references | Pinned allowlist input, source links and revision manifest. |
| Work transitions, reservation/lease/evidence semantics | Owning domain repository | Generated reference or reviewed short guide with explicit delegation; no copied state machine. |
| Cloud accounts, onboarding, memberships, connectors, deployment/operations | `vuoro-cloud/docs/public/` and reviewed existing runbooks | Cloud-owned chapters at the same site. |
| Current maturity / disposition | Established product/disposition authority | Versioned public subset; authors do not set availability by editing a badge. |
| Cross-repository direction and this proposal | `agentops/docs/` | Governing links, not a second public guide content tree. |
| Knowledge discovery/provenance | Existing `vuoro-knowledge` contract | Rebuildable projection; no new publication or review store. |

Use `doc_id`, `purpose`, `lifecycle`, `applies_to`, dates and supersession from
the existing knowledge contract. Add presentation metadata such as audience,
learning type, mode, maturity and public-publish allowlist in a build sidecar /
extended content schema. Tutorial/task/reference/concept labels are editorial
roles; they do not overwrite the contract's purpose/lifecycle enums.

Build only explicit public paths at pinned Git revisions. Do not crawl all
`docs/` or export session notes, raw evidence blobs, secrets, personal/customer
identifiers or private estate instructions. Generated files are disposable
projections; a correction edits the canonical source. The source manifest
records repository, commit, path, content digest and article mapping. No live
forge, database or customer access is needed to read the built site.

Cloud hosting maintainers own the pipeline/routes; domain owners review their
semantics; a nominated guide maintainer owns navigation, templates, link health
and source drift. Changes to advertised behavior ship with their relevant
article/reference change. Monthly public content review supplements that
change-triggered rule. Superseded pages retain stable redirects and an explicit
historical banner. Version archives are compatibility-set snapshots, not a
promise that all hosted tenants have the latest generation.

## 9. Staged delivery and acceptance

1. **Reconcile and freeze P0 content.** Inventory current public copy, live app
   behavior, owner contracts and held claims. Produce a reviewed public source
   manifest and 6–8 canonical articles. Accept when every procedure has a
   supported mode/version, source owner, tested outcome and truthful limitation.
2. **Build local static prototype.** Add isolated Starlight build, layout,
   article metadata, search and Markdown projection. Accept when browser tests
   under the intended docs CSP pass, no-JS reading works, keyboard/mobile search
   and navigation work, and builds fetch no runtime/customer data.
3. **Wire product/app entry points.** Add Guide/Help and exact contextual links.
   Accept when an evaluator finds the proof, an invited user finds first read,
   and a returning user finds ownership/settlement guidance without being
   directed into an unsupported feature. Preserve existing URLs and app flows.
4. **Publish through Cloud's existing reviewed release process.** Add static
   image/routing and smoke checks only after source qualification. Accept when
   `/docs/`, deep links, assets and public search respond on the actual host,
   app/API routes still pass, security headers are measured, old release rollback
   is tested, and the offline archive matches the published content manifest.
5. **Expand from observed questions.** Add P1/operator/integrator chapters and
   generated release references. Accept when documented commands safely pass
   help/dry-run/disposable-fixture checks and intentional drift/missing-source /
   private-page falsifiers fail the build.

Initial usability exercises: give three independent readers the jobs “what
can I try without an invitation?”, “why is my connected client missing a tool?”
and “which interrupted result counts?”. Each should find the correct page and
state the next supported action within two minutes without unsupported claims.
This is a proposed acceptance test, not a measured usability result.

Technical checks: broken internal/source links fail; duplicate/missing doc IDs
fail; unclassified maturity/applicability fails; changed owner reference without
review fails; secret/private-content fixtures fail public inclusion; reference
tool/scope drift fails; search returns only published pages; build is reproducible
from pinned inputs. Do not run mutating documentation examples against a user's
live workspace in CI.

## 10. Unresolved facts before implementation

- Actual deployed release and tenant compatibility/maturity beyond the public
  GET observations: UNKNOWN in this pass. Do not use a local source commit or
  stale status document as deployment evidence.
- Canonical source revisions for every owner input: freeze them in the content
  manifest when implementation starts; this proposal used local snapshots.
- Exact current release-proof wording across product19, later evidence and live
  site: needs owner reconciliation; this proposal changes none of those claims.
- CSP compatibility of the generated docs bundle and image distribution/promotion
  integration: requires a local prototype and existing Cloud release review.
- Public support contact destination and named guide-maintainer assignment:
  select from the existing product/support workflow; no unsolicited external
  messaging or new service account was created.

Planning artifact is intended for Git review in agentops and becomes durable
only when committed/landed. This pass changed only this new file and performed
no commit, push, external write, production mutation or deployment.
