---
doc_id: agentops-2062-ratification-dossier-2026-08-02
status: draft-for-coordinator-and-human-ratification
date: 2026-08-02
scope: analysis only; no implementation authority
---

# AgentOps #2062 — draft ratification dossier

## Scope and evidentiary limit

This is the Wave 4 coordinator/human decision record for AgentOps #2062. It
does not create implementation work or alter domain authority. The
[waved-dispatch program](post-cockpit-waved-dispatch-program.md) is a planning
projection, not a replacement for Sprintctl's live backlog.

The exact propositions are authored only in the untracked canonical-Vuoro
working-tree document
`/projects/dev/vuoro/docs/plans/vuoro-market-absorption-handoff.md`. That file
is correctly absent from this immutable project instance: untracked files have
no member commit and cannot be carried by project materialization, Git history,
or a pinned GitHub blob URL. The coordinator independently read the assessed
draft outside devbox and supplied its contents below. This is
coordinator-supplied untracked-source evidence, **not** a Git citation or an
independent devbox observation: SHA-256
`31dd5d0fe249f72281868f810d4c1c6976d8f26d265d566a41b2aad47735a3fa`, 9,169
bytes, mtime `2026-07-29T16:27:46.096393948+03:00`, status `assessed-draft`.
The assessed draft explicitly says D1--D7 are not ratified.

## Authoritative record inventory

“Canonical durable form” carries the record's meaning; a cache or rendering is
not made authoritative by being useful. “Not evidenced” does not mean absent.

| Record class | One owner | Canonical durable form | Export / rebuild | Retention and security | Loss consequence |
|---|---|---|---|---|---|
| Sprint/work-item state, claims, authority commands, and decisions | Sprintctl | Authority ledger plus authoritative storage projection; producer outbox is transport, not a second authority | `export`, `import`, and remote backfill exist, but exports only backfill labelled snapshots/known events: they cannot recreate authoritative causal history | Tier 0 authority; integrity/access controlled; claim proofs and capability refs are confidential operational data; duration not evidenced | Current state, fencing, and decision proof cannot safely be reconstructed |
| ActionQ Actions, immutable enqueue bindings, attempts/claims, lifecycle and settlement | ActionQ | PostgreSQL Action/lifecycle records plus byte-exact normalized request snapshots/digests | No authority export/rebuild procedure found; migrations are not recovery export | Tier 0 execution authority; snapshots and claim receipts are confidential. No automatic pruning: Action data remains for the Action lifetime | Idempotency, lease fencing, and settlement provenance are lost |
| Runner spool/capability/claim-receipt transport | ActionQ | None: spool is explicitly non-canonical; ActionQ authority records remain canonical | Reconciled `incoming -> quarantine -> sealed`; no spool-as-rebuild path | Ephemeral/private; capabilities and claim receipts must not enter journals/logs | Recoverable only by reconciliation while authority history survives |
| Candidate bundle, verification/publication artifacts, terminal `publication-receipt/v1` | ActionQ | Owner-only artifact root, exact `artifact:sha256` bytes, and receipt bound as terminal `result_ref` | Recovery journal can recover a completed receipt and settle; no general export/rebuild evidenced | Tier 0 provenance. Redacted logs: 1 MiB cap/30-day policy; bundles and receipts documented pinned indefinitely | Same-result provenance cannot later be manufactured |
| Repo-local audit observation and index | Auditctl | Canonical line in daily NDJSON shards; SQLite is a query index | Operator-driven fail-closed `rebuild --from-ndjson`; only exact canonical duplicate IDs skip | Tier 1 durable evidence/outbox; operationally sensitive, access controlled; duration not ratified | Recoverable if shards survive; loss must not alter domain authority |
| Central audit observation, ingest receipt, and cursor | Auditctl | Auditctl central observation ledger, receipt index, durable cursor | Atomic ingest/receipt/cursor documented; no central export/full rebuild evidenced | Tier 1 integrity evidence; owner-authorized; duration not evidenced | Receipt/dedup/continuity evidence is lost; source may be resent only from surviving origin stream |
| Knowledge candidate and review lifecycle | Kctl | Kctl candidate/review store and Kctl review transition | `export-proposal` is a read-only approved-candidate NDJSON snapshot, not lifecycle rebuild | Tier 1 reviewed knowledge/provenance; content-sensitive; duration not evidenced | Review state/provenance lost; proposal cannot assert a review decision |
| Vuoro owner-adapter composition and release pins | Vuoro | Versioned source composition/config and immutable owner release pins/evidence | Exact wheel/source verification specified; no separate state export/rebuild found. Deployment truth is Appservice's separate record | Tier 1 integration/provenance; trusted publisher identity is security-critical | Replacement composition cannot prove same release/catalog/authorization boundary |
| Cockpit views, review queue, metrics, gateway projection | AgentOps | Derived API/UI projection only; authoritative inputs remain owner-local | Re-query/re-render from owner reads; no cockpit DB is authority | Tier 2 operator projection; browser/API credentials are secrets; source sensitivity flows through | Visibility degrades, but owners retain records; projection cannot become recovery authority |

Evidence basis: Sprintctl [outbox ADR](https://github.com/bayleafwalker/sprintctl/blob/cf6761cddb3b32f51e022fc988d03992d108819e/docs/plans/adr-outbox-sync-model.md),
the ratified [state/event/command matrix](state-event-command-matrix.md),
ActionQ [portable-runner contract](https://github.com/bayleafwalker/actionq/blob/1b92f7ce5f8be3050cd8c5725d53e015dae4302f/docs/protocols/portable-runner.md),
Auditctl [write/rebuild](https://github.com/bayleafwalker/auditctl/blob/df73a4e5ad96873cfa6768d1af573b1e0d98608e/docs/protocols/audit-write-and-rebuild.md)
and [central-ingest](https://github.com/bayleafwalker/auditctl/blob/df73a4e5ad96873cfa6768d1af573b1e0d98608e/docs/contracts/central-observation-ingest.md)
contracts, Kctl [proposal example](https://github.com/bayleafwalker/kctl/blob/3b355de41358da74542170a80b8b5fa15d692ff1/docs/examples/knowledge-proposal-consumer.md),
and Vuoro [adapter promotion](https://github.com/bayleafwalker/vuoro/blob/08f83013b1b9f9042598b5468e8655aa7ba72d09/docs/architecture/adapter-promotion.md).

## Proposed ActionQ boundary — owner ratification required

Propose that ActionQ retain Action enqueue roots, immutable request snapshots,
claim/attempt fencing, queue/dispatcher leases, execution-session lifecycle,
trusted runner supervision, candidate publication receipts, settlement, and
recovery journals. The runner is an implementation boundary inside ActionQ,
not an additional authority.

Propose that ActionQ not own Sprintctl item/sprint transitions or claims,
Auditctl durable evidence/ingest, Kctl review decisions, AgentOps
projection/cockpit policy, Vuoro catalog/composition, or Appservice deployment
truth. It may emit observations and submit bounded owner commands, but cannot
project another domain's effect as ActionQ state. ActionQ-owner approval is
still required for artifact-root retention/deletion and recovery/export policy.

## Proposed cockpit disposition — owner/human ratification required

Keep cockpit as AgentOps-owned derived operator UX: source-labelled reads,
review queue, metrics, and mediated intent submission. It must not become a
durable authority or raw cross-domain database writer. The documented
sprint-activation JavaScript SQL transaction is a temporary boundary exception;
the existing proposal is to remove it in favour of an owning-domain command.
Its removal schedule and final allowed cockpit writes remain human/owner calls.

## Roadmap-surface classification

| Surface | Class | Reason |
|---|---|---|
| Authority ownership, fenced claims, immutable Action requests, durable evidence, review decisions, trusted release provenance | Strategic | Correctness, accountability, or security changes if ambiguous/lost |
| Outbox, SQLite indexes, ingest cursors, runner recovery journal, adapter catalog, source-labelled cockpit projections, session capsules/proposals | Mechanism | Serves strategic records but is not an independent authority |
| Worktrees, runner spool, disposable PostgreSQL fixtures, temporary candidate environments, dashboard caches, wave ordering | Disposable | Recreate/discard without creating authority |

Candidate bundles and publication receipts are not disposable: although their
worktrees/test environments are, the bundles/receipts are strategic provenance.

## D1--D7: source, human status, and recommended disposition

No human ratification, rejection, or deferral was observed in the immutable
instance evidence. The table's first status column reports that fact; it does
not assert a human decision. The recommended disposition is this dossier's
evidence-based recommendation only.

| Decision | Coordinator-supplied assessed-draft proposition summary | Current human-ratification status | Evidence-based recommendation | Remaining owner decision / basis |
|---|---|---|---|---|
| D1 | Freeze task-packet, execution-event, and evidence data schemas now; defer an Executor behavioural interface until a second backend consumes it | No ratification evidenced | Ratify the data-contract / defer-behaviour boundary | The second-backend consumption trigger remains the guard against premature interface abstraction |
| D2 | Require authoritative semantic records to be dumpable to plain, human-readable, Git-committable files and reconstructable from that dump; operational-exhaust scope remains unresolved | No ratification evidenced | Defer | Exact record/export scope and owner commitments remain unresolved |
| D3 | Represent external work state as an asymmetric mirror with cursor or watermark and explicit conflict rules; reject symmetric ownership and an Executor abstraction | No ratification evidenced | Ratify as an integration constraint | Subject to Sprintctl-owner confirmation of mirror, cursor/watermark, and conflict semantics |
| D4 | Narrow ActionQ to dispatch identity, lifecycle, claim/lease, retry identity, executor references, terminal observations, and reconciliation commands; exclude arbitrary DAGs, general cron, broad event transformation, worker discovery, and generic approvals | No ratification evidenced | Defer | ActionQ owner must approve the exact retained and forbidden capability set |
| D5 | Classify roadmap surfaces only as strategic, mechanism, or disposable by whether loss destroys information or merely needs replacement machinery | No ratification evidenced | Ratify the three-class review method | Do not pre-classify disputed components; their classification remains a review outcome |
| D6 | Use incident-derived conformance scenarios, with roughly eight as a cap; current Auditctl evidence supports one failure family only, and synthetic histories must be labelled | No ratification evidenced | Ratify the incident-derived cap and one-family starting evidence | Subject to Auditctl-owner confirmation; synthetic scenarios retain explicit labels |
| D7 | Keep MCP as an external CLI/API peer boundary and never the internal domain model | No ratification evidenced | Record as an already-settled standing constraint, not a new ratification | Preserve as a boundary condition; no new human decision is claimed |

The ActionQ, Sprintctl, Kctl, Auditctl, cockpit, and other owner decisions
named above remain explicitly unresolved. The coordinator-supplied assessed
draft is evidence for these recommended dispositions, not evidence that a
human has already made them.

## De-duplicated existing records and ratification queue

1. Sprintctl's outbox ADR is the canonical protocol decision; this repository's
   matrix is its classification/ownership projection.
2. Auditctl local NDJSON and central ingest are distinct local/central classes;
   neither replaces Sprintctl or ActionQ authority history.
3. ActionQ's runner contract covers non-canonical spool and canonical receipts;
   do not split runner artifacts into a new owner.
4. Vuoro composition evidence is distinct from Appservice deployment truth.
5. The cockpit program and write-surface policy describe one AgentOps projection
   boundary; neither authorizes a second Sprintctl implementation.

Human/owner decisions still needed: D2 record/export and operational-exhaust
scope; D3 Sprintctl mirror semantics; D4 ActionQ retained/forbidden capability
set; D6 Auditctl confirmation; ActionQ retention, deletion, and recovery/export
commitment; Sprintctl authority-history retention/snapshot recovery;
Kctl/Auditctl retention and security durations; and cockpit's final write
disposition including removal of the SQL exception.
