---
doc_id: agentops-capture-integrity-and-export-2026-10-30
status: operator-requested-implementation-plan
effective: 2026-10-30
work_binding: unknown
supersedes: []
---

# Capture integrity and deliberate export

This refines **AE-01** in the [evidence-guided workflow plan](2026-10-25-evidence-guided-agent-workflows.md)
and **PW-01/PW-05** in [portable workflows](2026-10-24-portable-agent-workflows.md).
It is an implementation profile and falsifying replay specification, not a new
work queue, evidence home, transcript format or enabled capture service. The
operator requested that useful concepts from the Hanzo/Spool discussion be
incorporated into the existing substrate on 30 October 2026. No vendor product,
model, scanner or hosted session-sharing service is selected by this record.

## Source baseline and version decision

Inspected AgentOps source: `09498925c72986122a936274a3be7d68684a7f1f`.

- `session-mechanization/session-capsule.schema.json` defines the historical
  `session-capsule/v1`: a UUID identity and one finalized mechanical session
  artifact. It has no incremental capture range or coverage contract. Preserve
  its shape and its readers; a clean session end does not establish capture
  completeness.
- `scripts/session_binding.py` produces session identity observations, explicitly
  **not** a session capsule. `scripts/session_notes.py` produces the separate
  semantic `session-note/v1`. Neither is an implicit raw-log collector.
- `scripts/harness_evidence/store.py` provides opt-in private artifact storage,
  digest verification and retention. It does not discover native transcripts,
  export them, or establish that a whole session was observed.
- The [AE-01 coverage replay proposal, PR #429](https://github.com/bayleafwalker/agentops/pull/429),
  linked to [GitHub issue #426](https://github.com/bayleafwalker/agentops/issues/426),
  is a separate pending source change at this review. Its synthetic count-only
  replay is not the two-real-harness capture, exact-byte or restart/outbox proof
  required here. Reconcile it before implementation; do not duplicate it or
  describe it as merged or qualified.

**Version choice:** extend the active native observation/evidence path first.
Do not emit `session-capsule/v2`, replace a v1 UUID with a hash, or restart the
retired capsule/scribe machinery merely to carry these requirements. AE-01/C1
below selects the exact owner schema after identifying a producer and consumer.
A breaking wire change gets its own version and migration; existing records are
never rewritten to claim the new guarantees. The EC-00 owner-contract/toolchain
rules apply to a new public interface. This profile is not a second schema source.

## 1. Preserve native bytes; make the capture boundary exact

The adapter names its native format and version, source/stream identity and
collector revision. It freezes each captured file/chunk before assigning its
digest. It does not hash a path to an actively growing log and call that an
immutable artifact. Rotation creates a new source identity with an explicit
continuation relation; a pathname reused after rotation is not the same source.
For a mutable source, pin the readable frontier and source generation before a
bounded read. Appends beyond that frontier belong to a later capture. A concurrent
rewrite/truncation or unqualified snapshot mechanism leaves source consistency
unknown; hashing the resulting copy cannot establish a coherent original range.

The first implementation uses **zero-based byte offsets with an exclusive end**
against the identified native source. A record-number coordinate is optional
adapter metadata and must name its decoder revision; it never silently substitutes
for byte offsets. Record the captured artifact digest and byte length, source
range, and the source frontier actually observed. Offsets belong to the source;
offsets in a transformed/redacted artifact are a different coordinate space.
A partial final native record is retained as such, not normalized into valid text.

Raw logs remain optional and private. A metadata-only source must declare that
it cannot provide native bytes/ranges, rather than generate an empty transcript
and report complete coverage. Cross-host continuation carries authorized,
immutable Git/artifact bytes or retrievable owner references. A local path, dirty
flag or hash of unavailable bytes is not a portable checkpoint.

## 2. Integrity, completeness and process status are separate

Keep three independent observations:

| Axis | Required meaning |
| --- | --- |
| Artifact integrity | These captured bytes match this digest. Verification requires retrieval of the artifact, or a separately identified verifier receipt. |
| Capture coverage | The collector observed a declared source interval/frontier; known gaps and unobserved intervals remain explicit. |
| Process/session end | Clean exit, failure, cancellation, timeout or inferred end under the execution owner's existing vocabulary. |

`complete` is permitted only **within a declared observation boundary** supported
by start/frontier/close evidence and an inventory of expected source streams. It
does not mean all provider reasoning, tools or internal state were observable.
An empty gap list means no gaps were detected, not that none exist. A crash can
leave an intact captured interval; a clean process exit can leave an unknown tail.

Every gap records its basis: observed omission, collector-detected discontinuity,
or inferred/unknown loss. Use an exact byte range only when known; do not invent
an offset or lost record count after a crash. Provider context compaction is a
context event. It is capture loss only when there is separate evidence that
bytes/events were omitted; an intact native log can coexist with compacted model
context. Missing tool output, truncated output and unavailable provider internals
must remain distinguishable.

Coverage includes the expected-session/source denominator, collector availability
and observed window. Sources absent because a hook never ran count as unobserved,
not as zero-event successes. The observer cannot enumerate sessions it never
knew about; such inventory limitations remain in the report.

### Hash and predecessor rules

Use the existing evidence owner's canonicalization and digest convention when
appending observations. A separately content-addressed capture envelope must
declare its canonicalization revision and ship byte-level test vectors: duplicate
JSON keys, non-finite numbers and ambiguous numeric encodings are refused. Hash
the canonical payload **without its derived digest/address and signature fields**;
include any existing v1 UUID as ordinary payload, without changing its meaning.
Signatures, if used, bind the resulting digest and contract context separately.

Predecessor references bind stream identity, sequence and prior digest. Missing,
reordered or conflicting positions are visible. A valid chain does not prove that
the producer captured all activity or that a tail was not withheld. Detecting a
rewritten whole chain requires an independently retained checkpoint/owner anchor;
without one, report only internal integrity. A signature identifies an attesting
producer, not the truth or completeness of its observations.

## 3. Raw retention and export are different artifacts

Preserve the [harness evidence policy](../../architecture/harness-evidence-policy.md):
raw material is opt-in, private and retention-scoped. Use the existing private
store where suitable. An export is a **derived artifact** with its own digest,
source-digest lineage and transformation/scanner revision. Never overwrite raw
bytes in place or export a raw locator under a redacted label.

Construct the complete candidate export locally: notes, attachments, filenames,
metadata and effect/usage summaries are part of its review surface. A scanner
record describes the exact scanned artifact digest, ruleset version, completion
status, finding counts and actions. It contains no secret values or excerpts.
Failed/partial scanning cannot become a successful scan, and zero findings does
not establish that the artifact is safe for every reader.

Freeze export bytes first. Then the existing Sovite/resource-owner output release
path decides whether those exact bytes may reach the named destination and reader
for the stated purpose under current policy. Store that decision/receipt as a
separate owner record referencing the bundle digest, avoiding a circular digest
between a bundle and its own authorization. Recheck current reader authority at
delivery; a retained historical allow is not a reusable live grant. Changes to
bytes, destination, purpose or relevant policy require a fresh evaluation.

`private|lan|public` labels and `scanned_before_egress: true` are descriptive, not
authorization. Normal commissioned policy can decide automatically; this adds no
universal human approval step. Export failure leaves permitted local work running
while release fails closed. Provider session-linking, telemetry and hosted model
context are egress destinations too, not implicit exceptions.

Retention expiration removes authorized private content without rewriting its
historical evidence or manufacturing a replacement digest. Readers distinguish
expired/deleted, access-denied, missing and digest-mismatched artifacts. Append an
availability/retention observation where the owner supports it; do not mutate old
capsules or evidence-chain records to erase their reference. Retained metadata
itself remains subject to its owner access/retention policy.

## 4. Link effects, usage and semantic handoffs to their owners

Capture artifacts carry immutable refs to execution attempts, admitted binding,
effect intent and target receipts, verification, usage and outcome records. They
do not copy those state machines into a transcript envelope. Distinguish an agent's
claim that a push succeeded from the destination's receipt. An intent with no
reconciled receipt remains unresolved; it is neither successful nor safe to repeat.

Provider/harness changes are explicit attempt/segment observations: requested and
observed supplier, native session handle, boundary decision, reason and usage
source. A missing usage source is unknown. Billed API amounts, estimates,
subscription consumption and local compute are distinct. Preserve cumulative vs
incremental counter semantics so failover/replay cannot double-count costs.
No inferred subscription headroom or zero-cost claim follows from no model call.

`session-note/v1` remains the semantic handoff: objective, attempted work, candidate
and verification refs, unresolved effects/questions and a useful next step. The
mechanical capture profile supplies evidence and coverage limitations. Test a
successor against **note + permitted owner records + coverage**, without opening
private raw logs. If the available evidence is insufficient, the correct result is
an explicit missing requirement and safe stopping point. Native resume is a
separately qualified harness capability; the capture artifact promises no
cross-harness restoration of private process or conversation state.

## 5. Delivery within existing packets

These are AE-01 substeps, not new work-item IDs or independent product objects.
Reconcile them to served work before runtime implementation; the binding was not
queried in this repository-edit session and remains `unknown`.

| Substep | Existing owner seam | Exit evidence |
| --- | --- | --- |
| AE-01/C1 | AE-01 source inventory; PW-01 contract qualification | Pin two actual native sources/versions, expected-source inventory, owner append schema, collector capability limits and permitted storage. Reconcile PR #429. |
| AE-01/C2 | Native adapters and private `harness_evidence/store.py` | Freeze bytes and verify exact range/digest/rotation behavior; no raw opt-in means no raw capture; retry does not invent another observation. |
| AE-01/C3 | Existing evidence owner append; offline coverage replay | Preserve unknown tails and partial records; verify ordering, duplicate/conflict behavior, restart/outbox acknowledgement and available anchors. |
| AE-01/C4 | Sovite output release and authorized artifact transport | Local derived export; exact manifest scan; current destination/reader decision; changed bytes or stale permission refused. |
| AE-01/C5 | PW-05 successor and existing ExperimentRecord methods | Two native harnesses and a clean successor host reconstruct permitted state from notes/owner refs/coverage; record all failed and absent cases. |

Run C1/C2/C3 with disposable synthetic artifacts first, then explicitly authorized
real sources; C4 requires the existing output-release path rather than an ad hoc
upload. C5 does not wait for universal transcript capture: a metadata-only source
can qualify a narrower continuation outcome when its limitations are explicit.

## 6. Falsifying replay cases

Freeze source bytes, expected observations and successor answers before running
the candidate. Distinguish synthetic, retrospectively reconstructed and real
native cases. The discussion's reported handoff-loss count is not a frozen test
corpus; locate and deduplicate the actual records before claiming that denominator.

1. Non-ASCII bytes, rotation and an incomplete trailing native record: exact
   half-open ranges and digests match; no normalization repairs the source.
   An append beyond the pinned frontier stays outside the range, while a
   concurrent rewrite/truncation prevents a complete/coherent-source claim.
2. Clean exit with a failed final collector flush: process ended, tail unknown.
3. Crash after a fully committed chunk: chunk integrity survives, later coverage
   is unknown, and no exact lost-event count is invented.
4. Context compaction with intact native log: record a context event, no fabricated
   byte-loss assertion. Separately truncate a tool result and retain that gap.
5. Missing hook/source: expected-source denominator retains the missing case.
6. Duplicate append, lost acknowledgement and restarted producer: same observation
   identity/digest; conflicting bytes at a stream position are refused/quarantined.
7. Removed middle chunk versus withheld final chunk: detect the first from the
   chain; detect the second only when a retained frontier/anchor establishes it.
8. Rewritten whole chain: independent owner anchor detects it, otherwise assurance
   remains internal-integrity-only.
9. Secret fixture in note/filename/attachment metadata: the full export is checked
   locally; no raw artifact or secret finding text escapes through diagnostics.
10. Scan passes but release is denied, expired or for another destination: no
    export. Mutating the bundle after scanning invalidates the scan/release basis.
11. Retention expiry: historical refs remain, retrieval reports unavailable with
    reason, and the successor does not infer artifact corruption or permission.
12. Provider failover with cumulative usage and one absent stop hook: no duplicate
    costs, explicit unknowns, no private-to-public fallback without admission.
13. Worker-reported success with missing target receipt: successor identifies the
    unresolved effect and requests reconciliation instead of retrying it.
14. Different-harness successor without predecessor chat/raw-log access: semantic
    note and owner records identify the exact candidate and next safe action,
    or explicitly name the missing prerequisite. No native-resume claim is made.

## Rollout, rollback and non-results

First publish read-only observations behind the native adapter's existing opt-in
or feature control. Compare against the unchanged v1/session-note readers and
source coverage baseline. Enable export only after current owner release and
destination tests pass. No captured data broadens a grant or blocks already-valid
owner completion merely because an optional recorder is unavailable.

Rollback disables new capture/export adapters and restores prior reader selection;
retain committed evidence, unavailable-artifact observations and source digests.
Reconcile any export with an uncertain delivery outcome before retrying. Never
backfill old records as complete, rewrite v1 UUIDs or delete an owner's evidence
history to make a rollback look clean.

This commit defines implementation and qualification requirements only. It adds no
v2 schema, collector, exporter, scanner, runtime service or claim of deployed
coverage. Those outputs belong to the named existing packets and their owner
evidence, not to the presence of this document.
