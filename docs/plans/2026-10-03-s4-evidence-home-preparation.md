---
doc_id: agentops-s4-evidence-home-preparation
purpose: proposal
lifecycle: proposed
effective: 2026-10-03
applies_to:
  components: [auditctl, sprintctl, vuoro-core, kctl]
subjects: [evidence-home, knowledge-resolution]
---

# S4 evidence home: design preparation and cutover gates

Status: **proposed preparation**, 2026-10-03, for served `agentops#2485`.
This note does not approve a migration, stop a live authority, start a soak,
change hooks or grant database privileges. The full item remains pending.

## Authority and scope

[TS-6](2026-09-17-target-state.md) and served `agentops#2480` Decision 199
(2026-10-03) settle the direction: new hosted captures are authoritative in the
substrate's authenticated append-only chain; repository exports are projections.
Existing committed auditctl records remain historical source authority until
verified import. Authored payloads, original digests and provenance survive
import; a new envelope or chain digest cannot replace them. This direction
does not prove hosted reachability or authorize effects, credentials or signing.
TS-13 remains a proposed follow-on for kctl/claim/lesson migration (`#2489`),
not a retirement performed by this note.

The item's historical `agentops/DOSSIER-far-future-architecture.md` reference
is not a file in canonical Git. A host-retained planning artifact was read for
context; it is neither a new public authority nor exported here. The binding
requirements are the current Git target state, Decision 199, served #2485's
recorded scope and the source-owner contracts below.

## Measured owner contracts and gaps

These are source observations, not production migration receipts:

| Owner and inspected revision | Existing contract | S4 implication |
| --- | --- | --- |
| [auditctl validation](https://github.com/bayleafwalker/auditctl/blob/085980b95dc327c5ac7887ecff3897e1390184e5/auditctl/validation.py), [central admission](https://github.com/bayleafwalker/auditctl/blob/085980b95dc327c5ac7887ecff3897e1390184e5/auditctl/central.py) | Stable `ad:` event id; optional legacy envelope; closed `observation`/`decision` class; canonical `payload_sha256`; central `record_sha256` includes record class and producer timestamp. | Preserve the producer's identity and both digest domains. Do not infer a Decision from event type or recompute an old digest using a new format. |
| [auditctl write/rebuild protocol](https://github.com/bayleafwalker/auditctl/blob/085980b95dc327c5ac7887ecff3897e1390184e5/docs/protocols/audit-write-and-rebuild.md) | SQLite plus fsynced NDJSON are not one atomic transaction. NDJSON can lead after a crash; stable-id rebuild converges valid records. | Inventory committed shards and recoverable local tails separately. A success count from SQLite alone is insufficient. |
| [Sprintctl evidence owner](https://github.com/bayleafwalker/sprintctl/blob/33b39d422adcf076f401356e963718303b468211/sprintctl/pg.py) | Run-bound evidence; per-run transaction lock; exact idempotency replay precedes tail checks; conflicting key/content or stale/forked tail is refused. | Extend this owner and protocol, not a second hosted chain. Moving its physical schema requires a reviewed owner migration. |
| [Sprintctl authority commands](https://github.com/bayleafwalker/sprintctl/blob/33b39d422adcf076f401356e963718303b468211/docs/guides/authority-commands.md), [ratified outbox ADR](https://github.com/bayleafwalker/sprintctl/blob/33b39d422adcf076f401356e963718303b468211/docs/plans/adr-outbox-sync-model.md) | Unknown transport outcomes remain replayable; terminal receipts authorize no transition; unsupported batch types are reported, not silently synced. Producer/ingestion fingerprints are distinct. | Compare effective state and canonical content, not unrelated hash columns. Offline requests must not become effective locally. |
| [Vuoro chain](https://github.com/bayleafwalker/vuoro/blob/90b45193f04fe8e05a072416acd1d1cba0cb19e2/packages/vuoro-evidence/src/vuoro_evidence/core/chain.py), [current rerun evaluator](https://github.com/bayleafwalker/vuoro/blob/90b45193f04fe8e05a072416acd1d1cba0cb19e2/packages/vuoro-evidence/src/vuoro_evidence/core/decision.py) | Entry linkage hashes item id, content digest, sequence and predecessor. The current evaluator can return REACQUIRE with no evidence and models rerun results as Decision kinds. | These existing functions do not establish the S4 derived-state/dead-harness rule. That rule needs an explicit implementation and adversarial gate before absorption. |

The 0.12.0 release owner identifies commit
`f6936f410f41a7dfaf7e5a1390c552eb90954874` and confirms that release adds
accepted-effect discovery, not new evidence or uncertain-effect semantics.
Inspected source revisions above are separately pinned; they are not asserted
to be the running deployment. The existing public proposer rollout gap
`#2600` likewise remains distinct from this evidence-home design.

Risk surfaces inspected: auditctl `audit-write-and-rebuild` requires depth-2
stateful verification for changes; Sprintctl declares `claim-ownership` and
`document-linked-work`; agentops has no declared `risk_surfaces` array at this
revision. Later schema, import, hook and publication changes require their own
stateful verification. This preparation changes only this note.

## Destination and ownership proposal

Proposed physical destination: `work_evidence` schema in the existing served
work database, owned and migrated by Sprintctl's work/evidence authority.
The name is a design proposal, not an installed schema. Keep the current run,
Release, Decision and work owners; move/extend evidence storage through that
owner rather than retaining a parallel audit ingestion authority. Separate
schema/roles honor the ratified ADR's domain separation without adding a new
service, shipper, daemon, runner or database.

Proposed roles, to be validated against actual deployment roles before DDL:

| Role | Allowed boundary | Excluded authority |
| --- | --- | --- |
| `work_evidence_schema_owner` | reviewed migrations and append-only constraints | application/hosted login; automatic deployment |
| `work_evidence_append` | authenticated, repo/workspace/run-bound append through existing protocol handlers; per-run tail lock | row rewrite/delete, arbitrary schema access, Decision/Release terminal writes |
| `work_evidence_read` | scoped protocol reads and exports with visible watermark | append, terminal decisions, effects |
| `work_evidence_legacy_import` | operator-controlled, manifest-bounded verified import of historical records; revoked after reconciliation | general hosted record scope, manufacturing grant use or new terminal decisions |

No auditctl role inherits these grants. No hosted scope gains legacy-import
power. Runtime roles cannot cascade-delete evidence by deleting a run; the
schema migration must replace that currently possible retention relationship
with explicit append-only protection before cutover. A migration-role bypass
is a separately reviewed operator action, not a runtime repair path.

The canonical `evidence_item` retains its current logical fields: repo/run/item
identity, idempotency key and request digest, kind/ref/content digest, collector,
validity, claims/provenance, chain sequence/predecessor and received timestamp.
Add append-only historical-source bindings to that same owner:

- `source_record`: original complete authored JSON and original line bytes or
  content-addressed bytes; original event id, class, payload digest and available
  central record digest; historical envelope fields; authored occurrence time.
- `source_binding`: source repository identity, committed shard path/blob/commit,
  line position, original producer stream/sequence when present, stream class,
  and `stream_state=committed_shard`. Uncommitted recoverable tails use an
  explicit alternative binding: `stream_state=uncommitted_tail`, capture host
  and original stream identity, absolute source path, whole-file frozen snapshot
  digest, byte offset/line position and reviewing operator identity. Missing
  commit/blob fields remain absent; no committed provenance is fabricated.
  Both variants also carry raw-line SHA256, import-manifest identity, destination
  evidence id/chain entry reference and verified mapping revision.
- `import_receipt`: manifest digest, importer identity/build, source/destination
  watermarks, counts/digest-diff result and reconciliation evidence reference.

These are proposed tables/fields, not new unversioned payload holes. The owner
must specify constraints and protocol schemas in its later implementation PR.
Unattributed legacy rows remain explicitly unattributed; importing them never
fabricates an old run, producer sequence, identity, grant, profile or assertion.
An import run records the importer and mapping without masquerading as the
historical producer. Repository projections preserve these bindings and cite
the authoritative substrate receipt.

## Digest preservation and import stop rules

| Source value | Destination treatment | Comparison |
| --- | --- | --- |
| Existing `payload_sha256` | copy byte-for-byte; validate with the source's canonical payload algorithm | source = imported original payload digest |
| Existing central `record_sha256`, when actually recorded | copy byte-for-byte with its algorithm/version | source = imported original record digest |
| Legacy row with no authored envelope/digest | retain complete original bytes/JSON and absence; compute a separately named import fingerprint | never label the new fingerprint an original authored digest |
| Raw committed NDJSON line | retain source blob/path/line and raw-line SHA256 separately from semantic JSON digests | frozen source manifest = exported imported source bytes |
| Destination item digest / chain entry digest | follow the existing evidence protocol, with original digests retained beside the import reference | independently verify the import content binding and every chain link |

Central audit hashes preserve non-ASCII characters and refuse NaN in canonical JSON;
NDJSON serialization has its own encoding. Sprintctl legacy event payload
hashes are another domain. Identically named `record_sha256` values from
producer and ingestion envelopes need not match. The future digest-diff tool
must identify the algorithm/domain it compares, not normalize all records into
one newly hashed envelope. The new destination content digest must bind the
complete immutable source representation and mapping revision, including the
original digest fields; it excludes destination ids, chain position and received
timestamps, which the append request/chain binding protects separately. Store it as a distinct digest: this additional integrity
binding never overwrites or relabels the original authored digests. Verify it
again when exporting or comparing imported evidence.

Freeze an inventory of committed shards plus explicitly reviewed uncommitted
recoverable tails before import. Never rewrite, truncate or delete historical
shards to make validation pass. Exact duplicate source identities/content replay
as the same import; conflicting event ids, producer tuples or idempotency keys
stop the entire affected manifest. New importer stream numbering cannot hide an
original gap. Tail bytes must still match their whole-file frozen snapshot
before import; a changed tail stops its manifest. Deterministic import keys bind
manifest digest and stable source identity. A source without a validated stable
identity fails admission; any separately reviewed identity-free historical input
must include path/blob or tail-snapshot identity and byte/line position in its
key. Identical content at different source positions cannot silently collapse.
The coverage report distinguishes replay from distinct records with reviewer
sign-off. Exact retries reuse those keys. Source authored order comes from original stream/sequence and line
bindings; destination chain sequence records import order and does not invent
historical causal order. Stop also on missing/corrupt files, invalid class, unmatched digest,
changed source inventory, unauthorized workspace/repo binding, chain break,
unknown lost-response outcome, count/coverage mismatch, or an unreconciled tail.
A verified retry resumes by durable identity/receipt; it does not mint a fresh
record to hide an uncertain write.

Acceptance requires source-to-destination coverage and zero mismatches for
original payloads/digests/provenance, not just matching row totals. Include
Unicode, legacy no-envelope records, observation/decision pairs, duplicates,
origin gaps, conflicts, crash-after-fsync and lost-response retries in disposable
fixtures. Before production import, rehearse the **complete real frozen manifest** in an
isolated destination, with source-access controls appropriate to its data.
Require full coverage and zero mismatches in every original digest domain.
Production must use that exact manifest digest, importer build and mapping
revision. Compare per-record source bindings, original digests, deterministic
import keys, source content-binding digests, coverage and digest-diff results;
any source change or divergence in those fields stops import. Destination ids,
chain sequence/predecessor/entry digest and received timestamps may differ
between destinations, but each destination's entire chain must independently
verify against its recorded tail. Those expected differences are not permission
to ignore source identity, content or effective authority.
Synthetic edge cases supplement this real-inventory gate, never replace it.

Historical audit `record_class=decision` stays historical evidence;
only the current Decision authority may bind a Release or write terminal status.

## Served derived evaluation

Store human/provider assertions and authenticated records. Derive rerun state,
expiry, grant use and EvidenceSet composition from those records at read time,
with explicit `as_of`, evaluated input digests, source watermark and evaluator
revision in the response. REACQUIRE, RECONCILE and `effect_uncertain` are derived
results, not newly persisted terminal Decision kinds. Accept/reject/withdraw/
supersede/revise retain the current Decision authority and Release binding.

The required dead-harness rule is: an accepted attempt, evidence of grant use,
and no terminal effect claim derives `effect_uncertain`, hence RECONCILE before
any consequential retry. No observation or an expired lease is not proof that
nothing happened. Proposed conservative handling of missing use receipts is also required for
owner review: an accepted attempt with no terminal effect claim remains
RECONCILE unless authority-side evidence proves non-invocation. Refusal before
invocation or proven absence of issuance/redemption may establish that proof;
missing use evidence cannot. An independent terminal observation has precedence
over non-invocation proof; unresolved contradictions require reconciliation.
An accepted+apparently-unused history without such proof must assert RECONCILE,
not REACQUIRE. An independent terminal observation may resolve uncertainty;
a self-reported success is not promoted into independent corroboration by an
import wrapper. Explicit refused-before-invocation evidence may justify a safe
reacquire path; missing results cannot substitute for that evidence. Expiry or
input changes invalidate sufficiency at read time while retaining the original
assertion, its digest and every historical Decision.

The exact owner vocabulary and precedence need implementation review and
forced-failure cases, including accepted+used+dead/no-terminal, accepted+unused,
refused-before-invocation, contradictory observations, expired evidence, changed
inputs and stale Release revisions. The source observations above show why
merely copying today's `decide_rerun` is not an absorb gate.

## Isolated absorb pre-merge gate

Run this only in a disposable authority/database/repository with synthetic
records, isolated profile and no production credential or effects. The later
owner implementation must supply an executable harness and pinned build; this
note is a test specification, not a claim the sequence ran.

1. Seed a served item, its exact Release, authenticated producer binding and
   source evidence. Record canonical baseline effective state and all cursors.
2. Stop **only the isolated authority**. Record failed reachability. Keep the
   producer outbox, cached baseline, pending requests and git worktree alive.
3. Attempt reserve against the pinned item/revision. Persist its request/key
   durably. If the owner cannot, the gate is unproven and fails. Label it pending,
   never an effective reservation/lease or right to execute.
4. Commit a harmless fixture change with `Vuoro-Release: <exact release digest>`.
   Save commit identity and the trailer; changing the digest is a failure case.
5. Append fixture evidence through the planned producer path, preserving its
   authored digest and queued identity. Propose a harmless effect intent bound
   to that Release/evidence, using a stable idempotency key; do not apply it.
6. While offline, verify that the only changes are authored local observations,
   commits and pending requests. No accepted proposal, shared reservation,
   terminal status, effective grant or execution may appear.
7. Restart the same isolated authority. Sync the same durable requests through
   its served protocol; harvest the trailer through the existing negotiated
   path. Repeat sync and a lost-response retry without creating duplicates.
8. Compare canonical **effective** state before/after sync against a continuously
   online reference history applying the same recorded requests in their
   recorded causal order: Release/item revision, decisions, reservation
   semantics, evidence identities/digests/tail, proposal binding, uncertainty/
   expiry results, cursors and unresolved requests. Before running, pin any
   ordering-dependent **metadata** timestamp fields that may differ. Ignore
   only those fields, receipt timestamps and random transport ids; never ignore
   state, authority, expiry/validity inputs or differences in their derived
   results. Use a controlled evaluation clock/as-of for semantic comparisons.
   Preserve a field-level diff and replay receipts.
9. Inject source digest mutation, stale CAS, a concurrent append, authority crash
   after commit/before reply, crossing expiry and changed inputs while offline,
   plus accepted+used+dead-harness and accepted+missing-use-receipt histories. Require
   explicit refusal/reconciliation and exact retry equivalence. Any divergent
   effective state or fabricated authority fails the gate: keep auditctl
   separate and stop migration.

**Current executable gaps:** served reservation commands first resolve identity
and invoke the live server; the supported batch/outbox path is not a blanket
queue for reservation, run-evidence and effect-proposal operations. Generic
`authority submit` in enforce mode is retired. An unavailable server cannot be
worked around with SQLite, direct DSN writes, shadow acceptance or a fabricated
receipt. The implementation must demonstrate the exact offline paths above;
unsupported steps are a failing/unproven gate, not silently omitted steps.
No soak can start while this test is unimplemented or fails.

## Hook transition, soak and irreversible follow-up

After the isolated gate, verified import and coordinated live cutover approval,
hook writers move to local **rotated NDJSON only**, outside committed shard paths.
Retain stable event ids, explicit live/fixture stream class, private local modes,
locking/fsync, bounded records, rotation recovery and disk-full visibility.
A local capture is pending until the single served record protocol returns a
verified receipt; no second local authority or new shipper is introduced.
The owner implementation must extend the existing Sprintctl producer outbox/
served sync path to the run-evidence append operation, with authenticated run
binding and exact retry receipts, before any hook repoint. That path is the
submission mechanism; hooks do not gain a separate shipper or direct DSN.
Captures carry a genuinely registered `run_id`. Without it, they stay local,
pending and explicitly unattributed; no synthetic run is substituted. Rotation
never deletes or truncates unreceipted records. A full pending backlog that
blocks rotation surfaces a bounded failure just like disk-full.
Hook failure must leave visible bounded failure evidence, not silently claim a
successful substrate capture. Existing cost/guard hooks remain their owners'
concerns. Do not change them in this preparation.

Coordinate the existing shard commit scheduler/consumer with the hook repoint:
flush and reconcile its final tail, record source cursors and cutover boundary,
then prevent new shard commits. Keep the auditctl adapter/release line and both
append-only CI checks intact. Treat any post-boundary new shard commit as a
cutover failure, preserving the row and investigating its producer. Read-only
source shards, rebuild tools and rollback evidence stay available throughout.

| Cutover/soak field | Value in this preparation |
| --- | --- |
| Actual verified live cutover time and receipt | **not occurred / unset** |
| Read-only soak start `T0` | **unset**; fill from actual approved cutover after final reconciliation |
| Earliest irreversible review `T1` | **unset**; compute `T0 + 90 days` in UTC only after T0 exists |
| Dated retirement work item | **not filed as a dated cutover claim**; create at actual T0, due T1, citing receipts |

At actual cutover, record T0/T1 and file the dated follow-up covering deletion
of the auditctl adapter/release line and removal of
`scripts/check_append_only_shards.py` from CI. The follow-up must require the
elapsed 90-day read-only soak, continued read/restore availability, zero digest
or effective-state divergence, no new shard commits, final operator review and
separate irreversible authority. A cutover rollback records its reason, voids the current T0 and preserves its
boundary. A later verified cutover sets a new T0/T1; previously elapsed time
never counts toward its 90-day soak. It cannot backdate or silently continue a
failed soak. Hook rollback
may resume capture only under an explicitly reviewed writer arrangement that
avoids two authorities and preserves every pending record.

Evidence at cutover must include the absorb field-level diff, import manifest
and zero-mismatch report, final tail/receipt ledger, deployed producer mapping,
the item's requested `git log --since <actual T0> -- '_artifacts/**/audit'`
observation plus the stronger commit-range check
`git log <cutover-boundary-commit>..origin/main -- ':(glob)_artifacts/**/audit/**'`
for every inventoried repository, after verifying that the pathspec matches
its real shard paths. Arbitrary committer dates cannot defeat the range check.
Record each repository's boundary commit and inspected main head. Include CI references showing
the append-only guard still present. Trigger WL-A3 intake (read-time expiry join)
on actual verified import, as #2485 specifies; do not call a design commit an
import. Do not close #2485 until all its operational Acceptance evidence and
actual dates exist. #2489's kctl migration and irreversible retirements remain
separately coordinated follow-ups.

## 2026-10-09 causal intake prerequisite qualification

The [released HTTPS proof](../evidence/2026-10-09-s4-causal-proof/README.md)
executes original offline reservation, trailer ingestion, evidence and bound
proposal intake against disposable owner clones, four real committed-response
loss/CLI-kill recoveries, and independent context/revision/evidence-head refusal
histories. This advances the causal intake prerequisite only. The controlled
read-time effective-state comparison (expiry, changed inputs and authenticated
accepted/use/non-invocation facts), complete real-inventory import, production
writer qualification, cutover and soak gates above remain required and open.
