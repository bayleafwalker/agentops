# Clean-Room Comparison — Strategic Buy/Adapt/Fork Assessment

## Revised conclusion

**Do not migrate now. The drop-in candidates failed or remain unassessed. The
strategic build-versus-buy question remains open.**

The completed work is a credible migration-safety gate. It establishes that no
tested, mostly off-the-shelf configuration may take Vuoro authority today:
Beads-native mutation and the tested Beads-to-Restate bridge fail authority
exclusivity, and the tested Windmill configuration fails its execution/trust
gate. The isolated Restate result and the separate completion-boundary harness
are useful component evidence, not integrated replacements.

This is not a substantive answer to whether an external substrate can replace
most of Vuoro after adaptation. The completed probes did not inspect Beads'
mutation paths or extension points, compare an adapter with a fork, run a
representative workflow through an integrated composition, or measure the
residual bespoke and operational burden. Treating missing semantics as a
product failure before evaluating the supported ways to add those semantics
would answer a different question: which product already behaves exactly like
Vuoro?

The unfinished buy/adapt hypothesis is **Beads plus Restate**. The goal is not
to make Beads an R2 authority; it is to determine whether Beads can provide a
useful planner/data-model surface while one narrow authority kernel owns claim
and completion decisions with exactly one mutation path.

Stage 1 is now complete for the pinned Beads revision. The source analysis
rejects a thin adapter under the tested embedded deployment: current hooks run
after mutation, and native execution-state writes have several direct paths.
It advances only a measured fork or projection-only deployment slice; see the
[source analysis](beads-restate-source-analysis.md) and
[implementation map](beads-restate-adaptation-fork-map.yaml).

## What the gate does and does not establish

| Question | Result |
| --- | --- |
| Can the tested configurations replace Vuoro immediately? | No. No migration is authorized. |
| Does Restate have a usable basis for proof, rotation, delegation, and recovery? | Yes, in an isolated R2 litmus. |
| Can the tested Beads bridge make Restate the sole authority? | No. Direct Beads mutation bypassed the bridge. |
| Can an adapter, maintained fork, or upstreamable extension remove that bypass at acceptable cost? | Unknown. No source-level or maintenance analysis ran. |
| Would a qualified composition remove more bespoke surface than it introduces? | Unknown. No residual-ownership or carrying-cost measurement ran. |

## Stage 1 — map the distance to fit

Before building another wrapper, produce a version-locked implementation map
using [the mapping template](../templates/schema/adaptation-fork-map.yaml).
Map every relevant Vuoro requirement to one of `native`, `configuration`,
`adapter`, `upstreamable-modification`, `permanent-fork`, or `still-bespoke`.
For each mutation-bearing Beads path, record the call site, whether it can be
intercepted through a stable supported hook, how direct mutation is denied or
made non-authoritative, migration implications, and upstream-sync risk.

The map must compare at least these variants:

| Variant | Specific question |
| --- | --- |
| Thin adapter | Can all authoritative writes be forced through a stable supported boundary? |
| Maintained Beads fork | Is a narrow native write-path patch cleaner than interception and reconciliation? |
| Upstreamable extension | Is the necessary hook/API plausible for upstream acceptance and stable maintenance? |
| Restate-backed replacement module | Does replacing the planner mutation module produce a cleaner sole authority despite more custom code? |
| Beads as projection/UI only | Does treating Beads as non-authoritative avoid duplication while preserving enough value? |

An adapter with a bypass is not a partial pass. A fork is not automatically a
failure: a small stable patch that makes a receipt mandatory may be preferable
to a large interceptor that silently recreates a second state machine.

The first actual map is [Beads + Restate](beads-restate-adaptation-fork-map.yaml).

## Stage 2 — build one genuine vertical slice

Use the real locked sprintctl corpus and a new, fully locked run directory. The
selected variant must demonstrate this sequence end to end:

1. Create or import work into Beads.
2. Request a claim through Restate.
3. Reject a competing or stale claimant.
4. Dispatch actual execution.
5. Reject a stale completion receipt and accept one current, verified receipt.
6. Crash the coordinating process and resume unambiguously.
7. Demonstrate that direct Beads mutation cannot bypass the authority kernel.
8. Produce the same audit and operator-visible result required by Vuoro.

The existing R2 bridge run is not this slice: it proves only the adapter's own
path and records the native bypass. The completion harness remains a contract
for the execution leg; it does not turn Windmill or another executor into an
authority candidate.

## Stage 3 — compare the adapter and fork variants

Run the thin-adapter variant first to reveal the minimum contract and to avoid
committing to a fork prematurely. Evaluate a narrow fork next only if supported
hooks cannot structurally deny bypasses. Reject the Beads composition if either
variant duplicates broad parts of Beads' state machine or requires a wide,
fragile upstream patch set.

The selected vertical slice must still pass the frozen R2/R6 gates and then run
the comparable S-BATCH, S-SOLO, S-RESUME, and S-SIMPLIFY protocols. Seed
S-DORMANT at setup and report it only after fourteen days. These safety and
comparison requirements are unchanged; this assessment adds the missing
adaptation economics rather than relaxing them.

## Stage 4 — measure residual ownership

For every viable variant, measure the following rather than treating a product
name as an architectural result:

- Vuoro modules/lines and operational procedures removed;
- custom adapter/fork/replacement code added and its test surface;
- authoritative databases and reconciliation loops;
- independently upgraded services and upstream patch burden;
- state migration, rollback, and recovery procedure complexity;
- operator friction for normal S-SOLO work and supervision for batch/resume;
- scenario-segmented setup, maintenance, and idle carrying cost.

The decision rule is deliberately harsh: the external composition must remove
substantially more bespoke surface than it introduces while retaining exactly
one authoritative mutation path. Removing a large Vuoro subsystem for a small,
stable adapter could justify hybridization. Replacing a small amount of Vuoro
with nearly as much custom code plus Beads, Restate, reconciliation, and a
broad fork probably does not.

## Possible outcomes

1. **Retain Vuoro:** adaptation saves little or adds more operational surface
   than it removes.
2. **Hybridize:** an external planner/UI or durable substrate replaces a
   substantial non-authoritative surface while a small Vuoro or Restate
   authority kernel remains.
3. **Fork or adapt:** a bounded Beads change or extension makes the external
   composition the cleanest owner with an acceptable upstream burden.

The record has ruled out only a fourth outcome: **drop-in migration with
negligible adaptation**. It must not be cited as a conclusion about the first
three.

## Relationship to the frozen comparison

This is a strategic assessment layer, not a change to R1–R8, the hard gates,
or the frozen H8 weights. Source mapping and variant comparison do not confer
production authority. Any candidate that moves authority must use a fresh
locked run and meet the frozen contract in addition to the residual-ownership
criteria above.

## Evidence

- [Gate-stage decision readout](decision-readout.md)
- [Final-criteria study](final-criteria-study.md)
- [Integrated Beads-to-Restate boundary](../runs/2026-07-23-lane-2-beads-restate-integrated/evidence/integrated-r2-boundary.md)
- [Execution-boundary study](execution-boundary-study.md)
- [Reduced-profile sufficiency study](reduced-profile-sufficiency-study.md)
