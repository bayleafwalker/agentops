# Verified MI-1 cross-harness case and bounded baseline

Current status checked 2026-10-09: the P1 reconstruction, P2 ingestion,
P3 named conformance, P4 bounded completeness deliverables and Track B are
accepted in the served work owner. The operator retired the unexecuted Track A
comparison on 2026-10-09. MI-1 now covers these proved bounded deliverables and
Track B; retirement establishes no comparative vendor result.
The earlier [protected preparation packet](../2026-10-09-mi1-protected-proof/README.md)
is a historical snapshot of a different, same-harness preparation case.

A hosted Claude assessment became a public source-only handoff. A fresh native
Codex continuation received that Git artifact and source without the predecessor's
private conversation. The native review corrected source claims and ran targeted
Go tests. An independent scratch reproduction confirmed that changing capture
completeness behavior changed a verdict while leaving the advertised implementation
hash unchanged. This documents a hash-scope gap; it changes no runtime behavior.
The verified assessment landed in
[Bindery PR10](https://github.com/bayleafwalker/bindery-core/pull/10), merge
`684dc4be6e34ae4b6924a9e9d429731350e28bca`, after every applicable CI check passed.

The [exact native report](result.md), SHA256
`775b03b33f9c5048ffcc11dc92e865a7e186982f14e9e93190c6c36bc0e4ace7`,
was then copied to this agentops-owned evidence path through the separately
commissioned protected verifier and applier. The owner refused the predecessor
canonical digest, missing required proof and predecessor verification receipt,
all HTTP409 without mutation. A deliberate interruption after signed create-only
branch publication preceded the PR and owner receipt; recovery rediscovered the
same signed branch and completed publication. The exact bytes and dedicated
signing key were independently verified. This effect landed in
[agentops PR325](https://github.com/bayleafwalker/agentops/pull/325), merge
`c50de0492df2c9594bd499e88f23c47df0128051`, after all applicable CI checks passed.

The bounded evidence case is settled by the work owner's Decision. A separate
read-only principal reconstructed all eight authorization links using P1's four
owner reads. Removing the receipt from a copied capture rendered it explicitly
`missing`; changing the artifact rendered `conflict`. The projection still
reports `authorizes_effects: false` and writes no acceptance.

Protected authority and signing remain restricted to agentops evidence publication.
The ordinary Bindery source PR was separately reviewed and landed. No protected
Bindery grant, cloud credential, executor, game/hardware result or ERH-006 completion
is implied. Actual provider outputs were coordinator-captured; direct hosted owner
registration was unavailable. Unknown coordinator build/instruction fields remain
unknown. Provider session references are references, never work identity.

## Explicit completeness sample

The existing `scripts/evidence_completeness.py` query was run twice with identical
inputs/results over the qualifying case and an independently observed historical
ordinary-run sample. Removing the copied effect receipt changes the query's result
to a missing-receipt failure.

| Stratum | Reconstructible | Failure class |
|---|---|---|
| Track B runs, n=3 | 2/3 (66.67%) | one coordinator attribution gap |
| Track B effects, n=1 | 1/1 (100%) | none |
| Historical ordinary runs, n=3 | 0/3 (0%) | three capture failures |
| Historical ordinary effects, n=0 | null | no sampled effects |

Track B is the bounded 2026-10-09 execution and protected follow-through. Ordinary
runs are all top-level native Claude sessions in the agentops project that started
on 2026-09-30 UTC and actually executed there; the bounded shared-owner export
through 2026-10-02 contained zero run rows. This is a precommissioning historical
window. No historical identities were backfilled. Tiny samples and overlapping
failure classes support no whole-estate or current-deployment coverage claim.

Raw provider captures, exact query inputs and reader/falsifier captures remain
host-persistent on the trusted host, with their hashes and proof references recorded
in durable-authoritative served checkpoints. They are excluded from this public
source-only summary. Public source artifacts are cross-host-replicated Git.

## Retired comparison and preserved external gates

[Track A's original protocol](../../experiments/mi1-tracka/README.md) is historical.
The operator explicitly retired its comparison requirement from MI-1 after choosing
local `claude -p` with the existing subscription. No GitHub Agentic Workflows
inference run was dispatched. The unused workflow is removed, and comparative
operator-time/cost/quality/recovery results and the kill-rule decision remain
unestablished. The original native quality failure remains preserved.

The accepted MI-1 scope is P1–P4 plus the real Track B proof above. Hardware
execution, ERH-006, legacy S4 import and unqualified resource-owner horizons remain
separate open gates; no fixture, source-only result or bounded sample closes them.
