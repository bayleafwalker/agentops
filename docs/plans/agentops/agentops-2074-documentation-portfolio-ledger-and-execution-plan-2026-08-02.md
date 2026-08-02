---
doc_id: agentops-2074-documentation-portfolio-ledger-and-execution-plan-2026-08-02
status: active-plan-packet-freeze
date: 2026-08-02
owner: agentops
tracker_item: agentops#2074
scope: planning and packet freeze only; owner-local rewriting not authorized here
---

# AgentOps #2074 documentation portfolio ledger and execution plan

## Decision and scope

This pass freezes the documentation-refactoring portfolio; it does not perform
the owner-local rewrites. Sprintctl remains authoritative for live work state.
This ledger creates no child items, claims, acceptance decision, publication,
deployment, archive deletion, or migration authority. Historical evidence is
preserved even where a forward pointer or status label is needed.

The following were deliberately read-only and remain reserved:

- the separate `agentops-2062-ratification-dossier-2026-08-02.md` and its
  active #2062 source set;
- every existing architecture file, including
  [`docs/architecture/vuoro-system-shape.md`](../../architecture/vuoro-system-shape.md);
- the canonical Agentops clone's pre-existing untracked session handovers;
- all six sibling repository worktrees.

The three requested Luna reports and their logs were reviewed from the derived
project folder's `.session/`. Their inventories are discovery evidence, not
architecture, ownership, status, or acceptance authority. No additional worker
was launched because source inspection closed the concrete evidence gaps.

## Critical review of worker evidence

1. The Agentops inventory correctly found a high-risk ownership drift:
   current binding and promotion sources make ActionQ the execution owner and
   `actionq-dispatcher` a compatibility launcher, while current-looking
   overviews still assign coordination to `actionq-dispatch`. It also correctly
   treated materialization, claim, packet, Action, and execution-session IDs as
   different lifecycles. The report did not establish the default-beta
   workflow, so that workflow is frozen below as a #2074 program requirement,
   not inferred from overlapping names.
2. The utilizer report's command mismatches were confirmed against source:
   ActionQ claim and settlement require proof on stdin; Sprintctl's non-served
   `claim show` requires a claim token; `maintain check` has no `--fix`; and
   Kctl implements coordination publication. Runtime `--help` was not available
   in the worker environment, so owner packets must verify installed help plus
   tests before changing examples. Source inspection is sufficient to file the
   discrepancy, not to settle compatibility or security wording.
3. The plan-status report counted a wide corpus but made status recommendations
   only for named files and families. This ledger classifies every explicitly
   assessed document or assessed family; raw count membership is not itself a
   status assessment. Its proposed change to
   [`docs/plans/next-session-dispatch.md`](../next-session-dispatch.md) is
   rejected because the file already carries the requested historical warning
   and forward pointer. Its preservation findings for Sprintctl archives and
   clean-room evidence are accepted.
4. Five broken links in Sprintctl's project-integration guide were reproduced
   by resolving their paths. They are mechanical repair candidates, but no
   currently registered hybrid command discriminates those failures. They are
   therefore not cheap-worker dispatch-ready at this freeze.

## Default-beta project workflow

The following vocabulary and operating rule is frozen for every packet. It is
a workflow boundary, not a transfer of domain authority:

| Context | Allowed use | Prohibited inference |
|---|---|---|
| Diagnostic dispatch-ready instance | Read-only portfolio discovery, dependency and dirty-state checks, packet preparation, and recovery diagnosis. | It is not the normal writable workspace and must not become the source of a candidate patch. |
| Unique task instance | Real owner-authorized work. Its task identity, source commit, repository, packet, and allowed paths are fixed at creation and are not reused for another task. The bounded files inside it may be edited only as the packet allows. | A shared folder name or materialization ID does not grant claim, queue, Git, acceptance, publication, or deployment authority. |
| Canonical clone | Clean recovery source and explicit break-glass workspace. | It is not the default location for routine agent edits or concurrent task execution. |

Every implementation packet must start from its repository's frozen commit in
a new task instance. The dirty member worktrees used for this diagnostic pass
must not be promoted into writable task workspaces.

> **Program risk — evidence availability.** #2062 discovery found that
> authoritative task context can cite untracked canonical-clone files that are
> absent from immutable task instances. Before a semantic decision, a packet
> must require the cited evidence to be committed at its frozen revision or
> attached as immutable evidence; otherwise it stops or defers the decision.

## Classification rules

- **current-governing**: an intended current contract, operator entry point,
  index, or ratified decision. A stale passage is corrected in place only by
  its owner.
- **active-plan**: an unfinished, explicitly active projection. It never
  overrides Sprintctl.
- **completed-history/evidence**: a completed assessment, handover, run, or
  plan record retained for provenance.
- **superseded**: replaced as current guidance; retain the body and add or
  preserve a forward pointer.
- **draft/proposal**: not accepted as governing truth.

Risk is the collision risk if the document remains current-looking, not a
license to rewrite it. “Owner review” in validation is mandatory for semantic,
authority, compatibility, security, migration, retention, or archival claims.

## Portfolio ledger — Agentops

| Assessed document or family | Class | Owner | Evidence and required action | Risk | Validation |
|---|---|---|---|---|---|
| [`README.md`](../../../README.md) | current-governing | Agentops | Active entry point still assigns bounded coordination to `actionq-dispatch`; reconcile names and link the current owner/launcher records. | High | Owner review; terminology scan; all local links resolve. |
| [`docs/ecosystem.md`](../../ecosystem.md) | superseded | Agentops | Its transitional/current-state framing and one-shot install/cron/config examples predate ActionQ convergence. Preserve useful history, add a prominent successor pointer, and remove it from the normal operator path. | High | Owner review against current ActionQ and launcher CLIs; no historical passage deleted. |
| [`docs/architecture/vuoro-system-shape.md`](../../architecture/vuoro-system-shape.md) | current-governing | Agentops, with cited domain owners | Current system narrative still assigns bounded coordination to `actionq-dispatch`. Architecture truth requires owner review; this pass does not edit it. | High | Agentops plus ActionQ/launcher/Vuoro owner review; architecture link check. |
| [`project.toml`](../../../project.toml) | current-governing | Agentops | Canonical project binding names `actionq-dispatcher` as reference-only and retains ActionQ execution authority. No #2074 rewrite. | Medium | `render_project.py check`; membership compared with registry. |
| [`docs/project/project-binding-spec.md`](../../project/project-binding-spec.md) | draft/proposal | Agentops | Header remains draft and the body contains both superseded and later membership text. Do not promote it by implication; reconcile status only with project-owner acceptance. | Medium | Owner acceptance; render/materialization tests; explicit supersedes pointers remain. |
| [`docs/project/project-folder.md`](../../project/project-folder.md) | active-plan | Agentops | V2 foundation is implemented while operating-model hardening remains. Add the default-beta diagnostic/task/canonical-clone crosswalk only after owner review. | High | Materializer tests plus explicit checks that diagnostics are not writable task instances. |
| [`docs/project/project-render.md`](../../project/project-render.md) | current-governing | Agentops | Deterministic rendering contract; no runtime task identity. Add only a non-overlap pointer if the lifecycle crosswalk needs it. | Low | Render check on fixtures; owner review of terminology. |
| [`docs/runbooks/vuoro-unattended-promotion.md`](../../runbooks/vuoro-unattended-promotion.md) | current-governing | Agentops coordinator; ActionQ, launcher, Vuoro, Appservice for owned steps | Current promotion source distinguishes ActionQ's daemon from the compatibility one-shot. Use as reconciliation evidence; do not infer deployment authorization. | High | Owner CLIs/artifact revisions checked; deployment steps remain separately authorized. |
| [`docs/runbooks/hybrid-dispatch.md`](../../runbooks/hybrid-dispatch.md) | current-governing | Agentops | Operational named-pilot contract already separates packet and worker session concepts. Qualify IDs when adding the project-instance crosswalk. | Medium | Hybrid validator and registered cold gates; owner review. |
| [`docs/plans/agentops/README.md`](README.md) | current-governing | Agentops | Active index mixes current, historical, and future plans and calls the launcher the existing coordinator. Add lifecycle labels/pointers without rewriting plan bodies. | High | Every listed local target resolves; index labels match document headers and this ledger. |
| [`agent-ops-substrate-plan.md`](agent-ops-substrate-plan.md) | superseded | Agentops with domain owners | Foundational plan already marks backend direction partly superseded, while later daemon/coordinator passages remain current-looking. Preserve as history and point to current records. | High | Status/pointer review by affected owners; body preservation diff. |
| [`state-event-command-matrix.md`](state-event-command-matrix.md) | current-governing | Agentops plus named state owners | Ratified ownership matrix; its `actionq-dispatch` compatibility wording needs terminology reconciliation, not a new ownership decision. | Medium | Domain-owner review against current owner contracts. |
| [`vuoro-substrate-simplification-refactoring-assessment-2026-07-26.md`](../../assessments/vuoro-substrate-simplification-refactoring-assessment-2026-07-26.md) | completed-history/evidence | Agentops assessment; named repository decision owners | Executive crosswalk records convergence, while R1 preserves pre-convergence evidence and alternatives. Label detailed R1 as dated evidence; do not rewrite the assessment. | High | Forward pointer to landed convergence; historical body unchanged. |
| [`portable-runtime-challenger-assessment-2026-08-01.md`](../../assessments/portable-runtime-challenger-assessment-2026-08-01.md) | completed-history/evidence | Agentops | Bounded assessment is complete and authorizes no challenger run. Retain unchanged. | Low | Header decision remains explicit; referenced evidence resolves. |
| [`vuoro-pre-clean-room/README.md`](../../assessments/vuoro-pre-clean-room/README.md) | completed-history/evidence | Agentops assessment | Complete retrospective with dated topology and migration evidence. Preserve as evidence, not a current operator map. | Medium | Status visible from parent index; links resolve. |
| [`decision-readout.md`](../../assessments/vuoro-clean-room-comparison/outputs/decision-readout.md) | current-governing | Agentops assessment/human decision owners | Governing no-migration gate result; strategic choice remains open. Keep its deliberately bounded conclusion. | Low | Decision and evidence links resolve; no broader migration inference. |
| Clean-room run corpus under [`docs/assessments/vuoro-clean-room-comparison/`](../../assessments/vuoro-clean-room-comparison/) | completed-history/evidence | Agentops assessment | Runs are already labelled template/partial/complete/closed. Preserve all evidence and incomplete rows. | Low | Corpus status/index consistency; no deletion. |
| [`next-session-handover.md`](../../assessments/vuoro-clean-room-comparison/outputs/next-session-handover.md) | superseded | Agentops assessment | Session handover already forwards to the decision readout and normalized verdict. Retain as dated handover. | Low | Forward targets resolve; no current-queue language introduced. |
| [`handover-2026-07-27-worker-routes.md`](../../dispatch/handover-2026-07-27-worker-routes.md) | superseded | Agentops | Its open containment questions are explicitly superseded by the 2026-07-28 contained run. Add only visible status/forward metadata. | Medium | Successor link resolves; containment evidence unchanged. |
| [`handover-2026-07-28-contained-run.md`](../../dispatch/handover-2026-07-28-contained-run.md) | completed-history/evidence | Agentops | Completed containment evidence; configured route qualification remained blocked. Preserve that limitation. | Medium | Back/forward links resolve; `qualification_eligible: false` remains visible. |
| [`handover-2026-07-28-served-recovery-rollout.md`](../../dispatch/handover-2026-07-28-served-recovery-rollout.md) | completed-history/evidence | Agentops and Sprintctl for owned facts | Recovery handover distinguishes a served-safe local diagnostic from authority mutation. Do not generalize the diagnostic into normal work. | High | Sprintctl owner review; diagnostic remains read-only and recovery-scoped. |
| [`wave1-implementation-findings-2026-07-29.md`](../../dispatch/wave1-implementation-findings-2026-07-29.md) | completed-history/evidence | Agentops with named implementation owners | Ratified workflow vocabulary plus reviewed but unpublished candidates. Reuse vocabulary while preserving release/deployment disclaimers. | High | Owner contracts confirm vocabulary; no candidate represented as shipped. |
| [`post-cockpit-waved-dispatch-program.md`](post-cockpit-waved-dispatch-program.md) | active-plan | Agentops | Active cross-repository projection explicitly subordinate to Sprintctl and owner semantics. It is the current plan pointer, not live status. | Medium | Header remains active; Sprintctl/owner re-read required before execution. |
| [`docs/plans/next-session-dispatch.md`](../next-session-dispatch.md) | completed-history/evidence | Agentops | Already contains a historical warning and current-plan pointer. No action is required despite the worker recommendation. | Low | Existing banner and forward link resolve. |
| [`execution-scope-declaration-pilot.md`](execution-scope-declaration-pilot.md) | draft/proposal | Agentops | Advisory pilot renamed from a non-existent local legacy doc ID. Normalize rename metadata only after the registry convention is decided. | Medium | Owner decision on `supersedes`; advisory/no-gate language retained. |
| Tracked records under [`.agents/sessions/`](../../../.agents/sessions/) | completed-history/evidence | Agentops/session coordinators | Four tracked dated journals/handoffs are operational evidence. An index may improve discovery, but must exclude or separately handle canonical-clone untracked handovers. | Medium | `git ls-files .agents/sessions`; dates/outcomes indexed without body rewrites. |

## Portfolio ledger — owner repositories

| Assessed document or family | Class | Owner | Evidence and required action | Risk | Validation |
|---|---|---|---|---|---|
| ActionQ [`README.md`](https://github.com/bayleafwalker/actionq/blob/1b92f7ce5f8be3050cd8c5725d53e015dae4302f/README.md) | current-governing | ActionQ | Quick start uses `claim --worker` and settlement without required proof stdin. Owner must rewrite examples without weakening proof/receipt semantics. | High | Installed `actionctl --help`, source decorators, focused CLI tests, and owner security review agree. |
| ActionQ [`actionq-server-daemon-workstream-c-plan.md`](https://github.com/bayleafwalker/actionq/blob/1b92f7ce5f8be3050cd8c5725d53e015dae4302f/docs/plans/actionq-server-daemon-workstream-c-plan.md) | active-plan | ActionQ | Header says active but the verified checkpoint predates daemon convergence and names `actionq-dispatch`. Reclassify or update only by ActionQ owner decision. | High | Compare current entry points/tests and successor records; preserve checkpoint history. |
| Compatibility launcher [`README.md`](https://github.com/bayleafwalker/actionq-dispatch/blob/9acf07185ca900adf92bd424dadf47d588a625f3/README.md) | current-governing | actionq-dispatcher | Correct current boundary but says “ActionQ daemon runbook” without a direct link. Add a link; do not add coordinator semantics. | Medium | Local link resolves; `dispatcher-once` help/tests; ActionQ owner confirms target. |
| Sprintctl [`docs/guides/start-here.md`](https://github.com/bayleafwalker/sprintctl/blob/73b9ae5cebe510bfedb775424de1e243e06abf81/docs/guides/start-here.md) | current-governing | Sprintctl | Clear start path; retain as the utilizer entry point. | Low | Docs-integrity and install-workflow tests. |
| Sprintctl [`docs/guides/project-integration.md`](https://github.com/bayleafwalker/sprintctl/blob/73b9ae5cebe510bfedb775424de1e243e06abf81/docs/guides/project-integration.md) | current-governing | Sprintctl | Five local paths resolve one directory too shallow. Repair links only; lifecycle prose is a separate semantic review. | Medium | All local links in this file resolve from the file's directory; Sprintctl docs-integrity suite. |
| Sprintctl [`docs/guides/remote-mode.md`](https://github.com/bayleafwalker/sprintctl/blob/73b9ae5cebe510bfedb775424de1e243e06abf81/docs/guides/remote-mode.md) | current-governing | Sprintctl | Explicitly transitional but mixes direct PostgreSQL and served operations; examples omit a required non-served claim token and name nonexistent `maintain check --fix`. | High | Mode-labelled `--help`/tests; owner compatibility, recovery, and secret-handling review. |
| Sprintctl [`docs/reference/knowledge-review-flow.md`](https://github.com/bayleafwalker/sprintctl/blob/73b9ae5cebe510bfedb775424de1e243e06abf81/docs/reference/knowledge-review-flow.md) | current-governing | Sprintctl for events; Kctl for review/publish | Diagram uses stale `sprintctl events` spelling. Correct command after both owners confirm the end-to-end flow. | Medium | Installed command help and focused cross-tool documentation review. |
| Sprintctl [`docs/reference/cutover-dogfood.md`](https://github.com/bayleafwalker/sprintctl/blob/73b9ae5cebe510bfedb775424de1e243e06abf81/docs/reference/cutover-dogfood.md) | completed-history/evidence | Sprintctl | Dated dogfood procedure uses the old `authority-config set` spelling. Preserve the original evidence; add status/current-command annotation rather than silently rewriting history. | High | Sprintctl owner decides annotation form; current authority help/tests; historical command retained as evidence where needed. |
| Sprintctl [`docs/archive/README.md`](https://github.com/bayleafwalker/sprintctl/blob/73b9ae5cebe510bfedb775424de1e243e06abf81/docs/archive/README.md) and listed archive files | completed-history/evidence | Sprintctl | Archive is explicitly historical and points to current sources. No status or deletion action. | Low | Every listed file and current-source link resolves. |
| Sprintctl [`docs/plans/README.md`](https://github.com/bayleafwalker/sprintctl/blob/73b9ae5cebe510bfedb775424de1e243e06abf81/docs/plans/README.md) | current-governing | Sprintctl | Current plan index explicitly demotes sprint snapshots. Keep as lifecycle authority for plan discovery. | Low | Indexed documents exist; headers match index role. |
| Sprintctl [`adr-outbox-sync-model.md`](https://github.com/bayleafwalker/sprintctl/blob/73b9ae5cebe510bfedb775424de1e243e06abf81/docs/plans/adr-outbox-sync-model.md) | current-governing | Sprintctl | Ratified canonical protocol ADR with an explicit external supersedes pointer. Preserve historical analysis and pointer. | High | Sprintctl owner/protocol tests; no backend or migration semantics changed by docs-only work. |
| Sprintctl `docs/sprint-snapshots/` family | completed-history/evidence | Sprintctl | Plans index explicitly marks snapshots archival and non-authoritative. No deletion. | Low | Index pointer remains; files preserved. |
| Vuoro [`README.md`](https://github.com/bayleafwalker/vuoro/blob/08f83013b1b9f9042598b5468e8655aa7ba72d09/README.md) | current-governing | Vuoro | Good boundary summary but lacks a local client/service/Compose start path and owner-facing links; “devbox dispatcher” wording can collide with the launcher boundary. | High | Vuoro owner and domain owners review; local links; package tests for runnable examples. |
| Kctl [`README.md`](https://github.com/bayleafwalker/kctl/blob/3b355de41358da74542170a80b8b5fa15d692ff1/README.md) | current-governing | Kctl | Contradicts its implemented `--coordination` publication/render surface and leaves local/remote/served selection implicit. Owner must settle intended wording; do not infer lifecycle semantics from the flag alone. | High | Installed help, focused tests, Kctl owner lifecycle review, links resolve. |
| Auditctl [`README.md`](https://github.com/bayleafwalker/auditctl/blob/df73a4e5ad96873cfa6768d1af573b1e0d98608e/README.md) | current-governing | Auditctl | Uses the former public substrate label and lacks a first-run read/write plus local/served path. Naming edits must not change durability, rebuild, ingest, or credential claims. | Medium | Auditctl owner review; CLI help/tests; protocol links and examples resolve. |

## Frozen repository-local execution packets

These are planning packets, not claims or dispatch requests. Packet IDs below
are stable portfolio IDs; a later execution must create a unique task-instance
ID and bind it to the listed repository and commit. A dirty or advanced source
requires coordinator re-inspection and an explicit refreeze.

| Packet | Repository and frozen base | Allowed paths | Frozen outcome and exclusions | Mode and discriminating validation |
|---|---|---|---|---|
| AO-TAXONOMY | Agentops `5affbfb6a3fb9ee1900a909887d3b28f797e0bc0` | `README.md`; `docs/ecosystem.md`; `docs/plans/agentops/README.md`; semantic review only for `docs/architecture/vuoro-system-shape.md` | Reconcile public names, ActionQ execution ownership, launcher compatibility wording, and current start/index pointers. No architecture decision or historical rewrite. | Coordinator/Agentops owner. Existing registered hybrid gates do not falsify taxonomy drift, so no cheap worker. Validate exact terminology scan, local links, and ActionQ/launcher owner sign-off. |
| AO-ARCHIVAL-METADATA | Agentops same base | `docs/plans/next-session-dispatch.md` (verification only); `docs/dispatch/handover-2026-07-27-worker-routes.md`; tracked `.agents/sessions/*` only if an owner-approved index is added | Add only missing status/forward metadata. Do not edit bodies, clean-room evidence, the #2062 set, or any untracked handover. The next-session file currently needs no change. | Metadata is mechanical but not cheap-worker eligible until a registered gate fails on missing/incorrect pointers. Validate `git ls-files`, successor existence, body-preservation diff, and all links. |
| SPRINTCTL-UTILIZER-LIFECYCLE | Sprintctl `73b9ae5cebe510bfedb775424de1e243e06abf81` | `docs/guides/project-integration.md`; `docs/guides/remote-mode.md`; `docs/reference/knowledge-review-flow.md`; `docs/reference/cutover-dogfood.md`; `docs/plans/README.md`; `docs/archive/README.md` | Repair five links; separate served/direct examples; annotate stale commands; preserve archive, cutover evidence, ratified ADR, and snapshots. No claim, proof, backend, authority, compatibility, recovery, migration, or security semantics may be decided by the editor. | Link repair is mechanical/path-bounded but not worker-ready: `sprintctl.suite` currently does not assert these five links. Semantic work is Sprintctl owner/coordinator. Validate installed CLI help, `uv run --extra dev --extra served pytest tests/test_docs_integrity.py tests/test_install_workflow_contract.py -q`, full registered suite, and an all-links resolver expanded by the coordinator. |
| ACTIONQ-UTILIZER | ActionQ `1b92f7ce5f8be3050cd8c5725d53e015dae4302f` | `README.md`; `docs/plans/actionq-server-daemon-workstream-c-plan.md` | Make quick start executable under the current proof contract; resolve the active-plan checkpoint/status. Do not alter proof, receipt, claim, lease, settlement, compatibility, retention, or migration meaning. | Coordinator/ActionQ owner only. Validate installed help, source/CLI tests, registered non-Postgres gates, and security/compatibility review. |
| ACTIONQ-LAUNCHER-LINK | actionq-dispatcher `9acf07185ca900adf92bd424dadf47d588a625f3` | `README.md` | Add an explicit ActionQ daemon runbook link and retain transparent one-shot wording. No daemon or coordinator behavior. | Mechanical/path-bounded, but no declared hybrid route or docs discriminator: owner-local edit, not cheap worker. Validate target existence and `uv run --extra dev pytest tests/ -q`. |
| VUORO-UTILIZATION-ARCHITECTURE | Vuoro `08f83013b1b9f9042598b5468e8655aa7ba72d09` | `README.md`; owner-selected existing `docs/` start/architecture pages only after refreeze | Add a local client/service/Compose start path and owner links; reconcile dispatcher vocabulary without changing transport-only, composition, adapter, compatibility, migration, or deployment boundaries. | Vuoro owner/coordinator. Existing registered gates test packages, not documentation semantics, so no cheap worker. Validate local links, runnable fixture-safe examples, `vuoro.boundaries`, and domain-owner review. |
| KCTL-NARROW | Kctl `3b355de41358da74542170a80b8b5fa15d692ff1` | `README.md` only | Resolve the coordination-publication contradiction and label local/direct/served paths. Do not change extraction, review, publication, supersession, or backend semantics. | Kctl owner/coordinator only; hybrid is disabled. Validate installed help, targeted README-linked tests, full pytest, and lifecycle-owner review. |
| AUDITCTL-NARROW | Auditctl `df73a4e5ad96873cfa6768d1af573b1e0d98608e` | `README.md` only | Reconcile public naming and add a first-run mode path without changing SQLite/NDJSON ordering, rebuild, ingest, retention, security, migration, or deployment claims. | Auditctl owner/coordinator only; hybrid is disabled. Validate installed help, full pytest in temporary roots, protocol-link resolution, and durability/security owner review. |

No packet may combine repositories in one writable context. The two ActionQ
rows are one portfolio unit but two repository-local packets. Agentops
architecture wording and Vuoro repository wording likewise integrate only
after both owner-local candidates pass independent review.

## Execution order and collision control

1. Owners first ratify the vocabulary crosswalk and the default-beta workflow;
   this is the semantic prerequisite for taxonomy rewrites.
2. Run AO-ARCHIVAL-METADATA independently because it changes only status and
   pointers. Stop if an untracked handover overlaps a selected path.
3. Run ACTIONQ-UTILIZER and ACTIONQ-LAUNCHER-LINK as separate task instances;
   integrate ActionQ first, then make the launcher link target its accepted
   record.
4. Run SPRINTCTL-UTILIZER-LIFECYCLE under Sprintctl ownership. Link repair may
   be integrated separately from mode/command semantics.
5. Run VUORO-UTILIZATION-ARCHITECTURE only after ActionQ/launcher terminology
   is accepted. Agentops architecture text remains a separate Agentops-owned
   change even when reviewed in the same reasoning unit.
6. KCTL-NARROW and AUDITCTL-NARROW may proceed concurrently in separate task
   instances after their owners answer the lifecycle questions below.
7. Run AO-TAXONOMY last so the portfolio entry points link only to accepted
   owner-local documents. Independent review precedes any Git publication or
   Sprintctl transition.

## Unresolved questions

1. Who is the human/owner approver for the default-beta diagnostic/task/canonical
   clone vocabulary, and is it already recorded outside the assessed corpus?
2. Should `docs/project/project-binding-spec.md` remain a draft despite shipped
   binding behavior, or should an accepted successor own the current contract?
3. Which current ActionQ document is the canonical daemon operator runbook that
   the compatibility launcher should link to?
4. Does the ActionQ workstream-C plan remain active, or is it completed history
   after convergence? Only ActionQ may decide.
5. For Sprintctl cutover evidence, should stale command spellings remain inline
   with an annotation, or move to an explicitly historical command block?
6. Does Kctl intend coordination candidates to be publishable/renderable as a
   separate stream, or is the implemented flag transitional? The flag alone is
   not lifecycle acceptance.
7. Which Auditctl first-run path is supported for ordinary operators, and what
   retention/security wording has actually been ratified?
8. Should tracked `.agents/sessions/` gain a public index, given that the
   canonical clone also contains reserved untracked handovers that must not be
   swept into this program?
9. Which repository will own a reusable documentation-link/command-example
   discriminator? Until registered gates can fail on these errors, no #2074
   documentation slice qualifies for cheap hybrid execution.

## Validation record for this planning pass

- The three worker reports and corresponding logs completed before the ledger
  was drafted.
- **Project-instance resolution:** every remaining relative Agentops link
  resolves from this ledger in the derived project instance.
- **Canonical and GitHub portability:** sibling-repository citations are
  immutable GitHub blob URLs pinned to the frozen member commits, rather than
  `../../../../` paths that only resolve in a derived project topology. Each
  cited blob is checked against its local frozen Git object and GitHub URL.
- The only intended Agentops worktree addition is this ledger. The pre-existing
  `.agents/environment.generated.md` modification is out of scope and must
  remain untouched.
- Sibling worktrees, canonical-clone untracked handovers, #2062 files,
  architecture files, Git history, Sprintctl state, and deployment state must
  show no mutation from this pass.
