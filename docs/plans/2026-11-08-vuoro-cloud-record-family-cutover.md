# Vuoro.cloud record-family cutover plan

Status: Proposed plan for agentops#2536; no actions authorized.

<!-- operator-self-use-open-rows:v1
["kctl estate and source scope","legacy knowledge row inventory","Workspace knowledge scope","TS-13 mapping decision","metanarrative authoritative stores","target ledger inventory interfaces","protected acceptance and receipt scope","local sprintctl SQLite inventory and count interface"]
-->

This plan documents readiness-stage S2. It authorizes no profile change, data
read, migration, write, or cutover.

## Evidence labels and scope

- **[fact]** means stated by a repository source cited in this plan.
- **[inference]** means a proposed interpretation or sequencing derived from
  those facts.
- **[unknown]** means repository evidence does not establish the answer.

**[fact]** The governing transition says each record family has one
authoritative store, no dual-write, and `vuoro-shared` remains authoritative
for work items until cutover. Local work/evidence and hosted run/evidence/notes
are separate families. See
[`2026-09-27-agentic-ecosystem-and-split-horizon.md`](../architecture/2026-09-27-agentic-ecosystem-and-split-horizon.md)
§3.3 and §3.4, especially the pre-cutover rule at lines 470–480; session-cost
capture and shards at §1.4:182 and §5:541; OTel's non-authoritative status at
§1.2:93 and §1.4:183; and the intent row/receipt split at §1.4:189 and §3.2.
Readiness §2 and §6 supplies the readiness gates.

**[fact]** The architecture sentence at lines 470–471 says, “Today local
sprintctl, kctl and auditctl writes go to `vuoro-shared` (and auditctl
shards)”. This conflicts with kctl's documented local SQLite ownership and
independence from sprintctl's database (kctl README:38,452; kctl AGENTS.md:16).
The proposed correction at architecture line 470 is to distinguish local
sprintctl writes (served `vuoro-shared` or explicitly selected local SQLite),
kctl's local SQLite candidates/publications and Git-rendered projection, and
the separate served legacy candidate/review adapter. Deployed Workspace
`knowledge` has no kctl bridge. This correction is proposed only; this plan
does not edit the architecture document.

**[fact]** The target-state record TS-6 places hosted evidence in the substrate
hash chain, preserves existing auditctl shards as authoritative historical
source records until verified target-state S4 import, and makes repository exports
projections. TS-13 proposes absorbing metanarrative claims/observations and
kctl knowledge as Evidence kinds `claim` and `lesson` plus Decisions at
target-state S4 (proposed only; TS-13 is not accepted). In particular,
kctl records remain in local SQLite and are not moved at Q1(b); their possible
TS-13 absorption is a later target-state S4 proposal. Readiness S4 is a
different stage: runtime/version qualification and test-workspace migration.
See [`2026-09-17-target-state.md`](2026-09-17-target-state.md).

**[fact]** Readiness §2 reports version skew and an unqualified restore path;
those are gates before any cutover. **[inference]** The plan therefore keeps
all steps below as future gated actions, and performs no dual-write or live
inventory as part of S2.

**S2 is partially met.** The family map, proposed targets, reconciliation
method and plan-register entry exist, but current authority/count interfaces
remain unresolved for per-repository sprintctl SQLite (sprintctl maintainer),
metanarrative claims and observations (metanarrative owner), possible legacy
`knowledge/v1` rows (vuoro-cloud operator), and whether deployed Workspace
knowledge is in scope (Workspace owner/#2536 owner). Whether the session-cost
JSONL duplicates or extends auditctl shard authority is unknown (agentops/
auditctl owner). The observed kctl estate also remains incomplete (kctl owner).
These are named in open questions below.
The #2536 owner decides whether readiness S2's existing acceptance criterion
is accepted as-is; this plan records the partial state and does not relax that
criterion.

## Family mapping and count checks

“Before” and “after” are immutable cutover snapshots. Counts must be taken
from the named authoritative source using its supported read/export interface,
with a stable ID and payload digest inventory retained in the private
cutover evidence area. Compare both total counts and the sorted `(id,digest)`
sets; count equality alone does not prove identity. Record excluded/deleted
records and any unsupported/unknown categories explicitly. No credentials,
record contents, or private inventory are to be placed in this public plan.

| Record family | Current authoritative store | Target authoritative store | Before/after count and reconciliation check |
|---|---|---|---|
| Work items, sprints, decisions, refs, events and work-item notes | **[fact]** `vuoro-shared` work schema in served mode; local SQLite when explicitly selected in local/recovery mode. **[unknown]** per-repository local sprintctl SQLite stores and the supported complete work-item count interface; see open question 8. Hosted work catalog is read-only before cutover. Readiness §2; architecture §3.3. | **[inference]** vuoro.cloud work catalog/ledger after the named cutover. | Before: count all in-scope work entities and event rows separately from the authoritative backend; capture IDs, revisions and digests. After: count corresponding vuoro.cloud entities/events and compare exact ID/revision/digest inventories; report intentionally excluded terminal/archived rows separately. Require zero unexplained missing, duplicate, or changed records. |
| Local run records and session lifecycle events (`workflow.session`, `dispatch.exit`) | **[fact]** auditctl shards are an authoritative local evidence source (TS-6); local session cost log is `/projects/dev/.claude/session-costs.jsonl` as an additional capture source (architecture §1.4:182, §5:541). **[unknown]** whether the JSONL is a duplicate/projection or contains authoritative records not present in shards. | **[fact]** substrate evidence hash chain is the target for evidence (TS-6). | Before: count run/session/exit records by source and event kind; compare shard and JSONL identities to identify overlap, gaps, and unclassified rows. After: count imported chain evidence by original source ID/digest and event kind; exact source-to-chain mapping, preserving original digests and provenance. Require all source rows classified as imported, duplicate capture, or explicitly excluded with reason. |
| Local harness evidence and cost snapshots | **[fact]** auditctl shards are authoritative historical source records through verified target-state S4 import (TS-6); harness telemetry (OTel) is non-authoritative (architecture §1.2:93, §1.4:183). | **[fact]** vuoro.cloud substrate evidence hash chain for authored evidence (TS-6); OTel remains observation only. | Before: count authored audit events by shard, producer and event kind; do not add Langfuse/Prometheus/Loki observations to authored evidence totals. After: count chain records by original shard/event digest; compare exact identities and preserve authored payload and original digest. Report telemetry separately and never count it as migrated evidence. |
| Hosted/interactive runs, their evidence and session notes | **[fact]** vuoro.cloud (architecture §3.3); run/evidence records use the public horizon (TS-16). | **[inference]** vuoro.cloud remains authoritative; no relocation is proposed. | Before and after: count by workspace, record type and stable ID in read-only snapshots; verify counts and `(id,digest)` sets unchanged across the work-item cutover. Do not recount gateway correlation logs as registered run records. |
| kctl durable candidates | **[fact]** Per-repository local SQLite (`$KCTL_DB`, default `~/.kctl/kctl.db`), table `knowledge_candidate`, `candidate_kind=durable`; kctl/AGENTS.md and README.md. The served adapter targets the legacy candidate/review catalog, not the deployed Workspace catalog. | **[inference]** Proposed target-state S4 TS-13 `lesson` Evidence plus Decisions where applicable, only after scope and conversion contract are approved; no current bridge. kctl records stay in local SQLite at Q1(b). | Before: freeze a standalone SQLite backup and run `python -m kctl.source_preflight --snapshot <file> --sha256 <hash>`. Retain private per-table/per-row digests; additionally count `SELECT candidate_kind,status,count(*) FROM knowledge_candidate GROUP BY 1,2`. Reconcile candidate IDs/statuses and source digests, including excluded/rejected rows. After: count mapped Evidence/Decision records by source identity and compare exact identities/digests. Preflight qualifies only supplied-snapshot coverage, not live-tail or estate completeness. |
| kctl coordination candidates | **[fact]** Same per-repository local SQLite, `knowledge_candidate` with `candidate_kind=coordination`; distinct review stream. | **[inference]** Proposed target-state S4 TS-13 Evidence/Decision only if explicitly included in approved scope; coordination is not automatically a `lesson`. kctl records stay in local SQLite at Q1(b). | Same frozen-snapshot preflight and SQL grouped by `candidate_kind,status`; reconcile coordination IDs/statuses independently from durable candidates. After: compare only explicitly mapped records, preserving separate kind and source identity. |
| kctl published entries | **[fact]** Per-repository local SQLite, table `knowledge_entry`; publication lifecycle is local-owned. | **[inference]** Proposed target-state S4 TS-13 Evidence/Decision if in scope; published status is lifecycle provenance, not a separate target family. kctl records stay in local SQLite at Q1(b). | Before: use frozen snapshot row counts/digests for `knowledge_entry`, plus publication-consistency findings from preflight; reconcile entry IDs to source candidates and supersession links. After: exact source-ID/digest mapping, separately report superseded or excluded entries. |
| kctl rendered knowledge base | **[fact]** Committed Git Markdown in each consuming repo (for example `docs/knowledge/knowledge-base.md`); it is a rendered projection, not a hosted store. | No record-store migration. Rebuild from the chosen authoritative source after any approved cutover; retain Git history. | Before: record repo/commit, target paths, and deterministic rendered file hashes/entry counts. After: rebuild and compare expected output/hash, and verify each rendered entry maps to the reconciled published-entry inventory; do not add projection rows to Evidence counts. |
| kctl extractor state (`extractor_state`, v1, and `extractor_state_v2`) | **[fact]** Per-repository local SQLite tables, extraction bookkeeping rather than knowledge content; frozen-source preflight covers both tables. | Retire with kctl; no TS-13 target record. | Before: count and digest rows in the frozen preflight report; reconcile watermark/state against the corresponding source event stream as an operational retirement check. After: zero active kctl extractor-state rows once kctl is retired; do not migrate them as Evidence. |
| Legacy central `knowledge/v1` candidate/review/publication catalog | **[fact]** Legacy adapter/schema is retained separately; in served mode the kctl client can target legacy candidate intake/review, while publication/render/export remain Git/local-owned. This is distinct from deployed Workspace. **[unknown]** whether rows remain in any tenant DB; report points to vuoro-cloud `scripts/legacy-domain-inventory.py` for read-only inventory. | No automatic target: Workspace has no kctl bridge, and TS-13 migration contract is unresolved. Treat any extant legacy rows as a separately scoped source pending owner decision. | Before: vuoro-cloud operator runs supported read-only legacy-domain inventory per tenant and reports schema/table counts plus stable IDs/digests; distinguish absent schema, empty schema and inaccessible tenant. After: if explicitly migrated, reconcile exact source identities/digests to approved target records; otherwise record retained/unbound disposition and recheck counts. |
| Workspace knowledge on `vuoro-shared` (`vuoro-workspace/v1`) | **[fact]** Deployed `knowledge` owner is Workspace; its `knowledge_workspace` schema and `vuoro-knowledge-objects` PVC are not kctl state and have no kctl bridge. | Remains Workspace-owned; no kctl-to-Workspace migration is implied. **[unknown]** whether Workspace knowledge belongs in #2536’s S2 family inventory. | Before/after: Workspace owner supplies supported read-only inventory/count and stable IDs/digests if #2536 includes it; compare unchanged inventories across this cutover. Do not compare against kctl candidate/entry counts or infer parity from configured profiles. |
| Metanarrative claims and observations | **[unknown]** the current authoritative persistence location is not established by the cited repository sources; TS-13 says these are future absorbed records, not where they live today. | **[fact]** proposed target is Evidence kinds `claim` and `lesson`, plus Decisions (TS-13). **[inference]** map claims to `claim`, observations/lessons to `lesson`, and adopted judgements to Decisions only after owner confirmation. | Before: blocked until metanarrative owner identifies each source and distinguishes claims, observations, lessons and decisions; count by category with stable IDs/digests. After: count each target kind and compare per-category identity/digest inventories, recording rejected/superseded items separately. |
| Intent proposals and protected acceptances / receipts | **[fact]** proposed intent row is in vuoro.cloud; accepted canonical digest and receipt are on protected side (architecture §1.4:189 and §3.2). | **[fact]** split across vuoro.cloud proposal and protected-side acceptance/receipt; no single-store move is specified. | Not in this cutover population unless #2536 explicitly scopes them in. If included later, count proposal, acceptance and receipt records independently on their authoritative sides, by intent ID/digest; verify cross-reference completeness without moving or conflating protected receipts. |
| Project-instance folders and derived views | **[fact]** `_projects/*` are derived work folders, never a store (TS-14); OTel summaries are non-authoritative (architecture §1.2:93 and §1.4:183). | No authoritative-store migration. Rebuild from their source after cutover as needed. | Record source checkpoint/revision and derived output count before and after; parity is validated by successful deterministic rebuild, not importing the derived rows as records. |

**[fact: session observation, read-only investigation on 2026-11-08; not
reproducible from this repository]** The investigation reported these scoped
observed counts (not an estate-wide baseline): aligned-equity has 39 published entries;
homelab-analytics has durable candidates 27 approved / 121 published / 34
rejected and coordination candidates 1 approved / 4 published / 8 rejected;
sprintctl has durable 4 published / 1 rejected and coordination 1 published /
2 rejected; box has 7 published entries; the inspected `~/.kctl` v9 database
is empty. Treat these as session observations only: the full `.kctl` estate and
legacy central row presence remain open questions above. Frozen-source preflight
accepts at most 100,000 rows and rejects unknown tables and newer schema versions;
it covers `schema_version`, `knowledge_candidate`, `knowledge_entry`,
`extractor_state` (v1), `extractor_state_v2`, and `sqlite_sequence`
(kctl `docs/protocols/frozen-source-preflight.md:54–63`). The report's suggested
SQL counts candidates by kind/status; published-entry totals must come from
`knowledge_entry`, not the candidate `status` grouping.

## Proposed cutover order

All order and gates below are **[inference]** unless stated as fact above.
The readiness stages S3–S7 remain prerequisites; this plan does not collapse
them into #2536.

1. **Inventory and freeze scope.** Confirm the record-family owners, supported
   read/export interfaces, identity rules, retention exclusions, and the
   unknowns below. Capture read-only before snapshots and digests. No public
   schema/API change is part of this plan; any required schema or contract
   change must be separately reviewed against vuoro-cloud migration docs and
   migration policy before implementation.
2. **Resolve non-work source families.** Establish metanarrative authoritative
   stores and mappings; resolve the remaining kctl estate, legacy-row and
   scope questions below. Keep affected rows blocked until owners provide
   evidence and count definitions.
3. **Qualify destination and recovery.** Complete readiness S3–S5: reviewed
   workstation profile, compatible runtime/client composition, and fresh
   restore drill. Confirm cutover and rollback can use supported interfaces.
4. **Rehearse one family on a copy.** Start with one bounded local evidence
   family, preserve source payloads/digests, verify target counts and exact
   identity mapping, then exercise rollback on the copy. No dual-write.
5. **Prepare the Q1(b) switch.** Freeze and reconcile the family mapping,
   interfaces and client configuration. Keep every family on its existing
   authoritative store; kctl records stay in local SQLite and do not move at
   Q1(b). No staged move is made in this preparation step.
6. **Perform the single Q1(b) cutover that starts NORMAL.** After the
   Authorization-header fix and E2, switch local harnesses to vuoro.cloud and
   vuoro-shared to protected services plus fallback, as architecture §3.3:481–483
   and §7:684–686 specify. Within this controlled cutover, move the in-scope
   families one at a time, as readiness S6 requires. At every intermediate
   point, each family has exactly one authoritative store: stop writes to its
   old authority before enabling writes to its new authority, reconcile its
   before/after inventory, and leave all not-yet-moved families solely at
   their existing authority. Do not declare NORMAL until the complete switch
   and all family reconciliations succeed. Cut over work items and related
   events, revisions and notes as one dependency-ordered group so references
   do not point across authorities. Stop on any unexplained discrepancy.
7. **Verify settled state.** Recheck all family counts and identities, confirm
   hosted/interactive and protected-side records remained in their existing
   stores, and retain `vuoro-shared` as the documented fallback until the
   outage-epoch/recovery stage is complete (readiness S7; architecture §3.3).
   Do not remove the old source until its retention and rollback period is
   explicitly closed. Any later kctl absorption is a separate proposed
   target-state S4 decision, not part of Q1(b) or readiness S4.

## Open questions

1. **kctl owner (sprintctl/kctl maintainer):** A read-only session investigation
   on 2026-11-08 observed five `.kctl` databases; `bindery-core` and
   `counterfactual-ops` set `KCTL_DB` without an existing directory. This is a
   session observation, not reproducible from this repository. Confirm the
   complete estate and explain the origin/scope of
   the empty `~/.kctl` v9 store. Frozen preflight covers only an explicitly
   supplied snapshot, not live-tail or estate completeness.
2. **Vuoro-cloud operator:** Run the read-only `legacy-domain-inventory.py`
   check per tenant to establish whether legacy `knowledge/v1` rows remain;
   distinguish no schema, empty schema and inaccessible tenants.
3. **#2536 owner:** Decide whether deployed Workspace knowledge on
   `vuoro-shared` is an S2 record family in this plan. If yes, identify the
   Workspace owner’s supported inventory and count/digest interface; do not
   use kctl candidate counts as a proxy.
4. **#2536 coordinator / TS-13 owner:** Confirm whether proposed target-state S4
   lesson/claim
   absorption remains the intended plan for kctl records and define which
   durable and coordination categories map to Evidence or Decisions. Until
   that contract exists, the target mappings above are proposals only.
5. **Metanarrative owner (agentops maintainer):** What are the authoritative
   current stores and stable IDs for claims, observations, lessons and
   decisions? Which categories map to TS-13's `claim`, `lesson` and Decision
   records?
6. **Vuoro-cloud owner:** What supported read/export interfaces and target
   ledger kinds expose complete inventories for work, runs, evidence and
   notes at the version selected for readiness S4? The readiness record notes
   version skew and incomplete live ledger-version proof.
7. **#2536 owner / operator:** Is the work item scope intended to include
   protected acceptances/receipts or only local harness record families, and
   what retention window closes rollback for each family?
8. **#2536 owner / sprintctl maintainer:** Which supported interface provides
   complete counts and stable identities for per-repository local sprintctl
   SQLite databases? This plan cannot establish either the local database
   inventory or the count interface from repository evidence; both remain
   [unknown] until confirmed. See the work-item family row above.

## Sources

- `docs/dispatch/verification/2026-11-07-vuoro-cloud-workspace-readiness.md`
  §§2, 6.
- `docs/architecture/2026-09-27-agentic-ecosystem-and-split-horizon.md`
  §§1.2, 1.4, 3.2, 3.3, 3.4, 5, Q1 and Q3.
- `docs/plans/2026-09-17-target-state.md` TS-6, TS-13, TS-14, TS-16.
- `docs/runbooks/vuoro-workstation-cutover.md` Preconditions, especially 6.
- `docs/plans/trace-background.md` (kctl candidate extraction description;
  not evidence of the knowledge store's authority).
- kctl `AGENTS.md`, `README.md`, and `docs/protocols/frozen-source-preflight.md`
  (local store ownership, served adapter boundary, Workspace distinction, and
  frozen-snapshot coverage/count limits; checked in the local kctl checkout).
- The architecture sentence and proposed correction at line 470 are quoted and
  described in Evidence labels and scope above. The correction is not applied.
