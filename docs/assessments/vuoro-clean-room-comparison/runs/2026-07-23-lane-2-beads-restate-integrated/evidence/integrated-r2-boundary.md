# Lane 2 — Integrated Beads-to-Restate Mutation Boundary

## Result

The bridge successfully required a current Restate proof before invoking a
real Beads status/assignee mutation. It also completed concurrent acquisition,
proofless delegated mutation rejection, transfer rotation, stale-transfer
rejection, controlled recovery, and stale-post-recovery rejection.

The composition nevertheless **fails** the authority-exclusivity condition:
a native Beads update accepted an execution-state mutation without an adapter
receipt. The tested bridge repair restored the Beads projection from the
current recovered proof, but it cannot remove the native bypass. This is a
recoverable disagreement path, not a reduction in reconciliation.

## Locked local execution

- Beads revision: `d7b9f4fc52deebc86cb25c214107e96cdd512b67`
- Restate image: `docker.restate.dev/restatedev/restate@sha256:53b245bcd64318233128c49ce56577737c888fcfacd5dbe8e7c88deb12753681`
- Adapter image: `vuoro-clean-room-lane2-adapter@sha256:13816d72ba84dc2df76bb624a4c27de283c505aad4c2b44f0a23466cbbfcdb9d`
- Isolation: disposable planner workspace and data, a Docker network, and
  only loopback-published Restate ports. No production credentials, mounts,
  endpoints, or state were used.

The recovery key and all bearer proofs were generated per run, passed only to
their authority channels, and neither printed nor stored. The following output
contains SHA-256 digest prefixes only:

```json
{"adapter_gated_mutations":"passed","authoritative_owner":"operator-recovered","concurrent_acquire":{"accepted":1,"rejected":1},"native_beads_bypass":"accepted","planner_item":"cr-689","proof_digest_prefixes":["621dc834c751","3f75b4300c69","e8268555c3cc"],"proofless_delegated_mutation":"rejected","reconciliation_repair":"passed-but-bypass-remains","recovery_stale_proof":"rejected","stale_handoff_proof":"rejected"}
```

## Consequence

Do not promote Beads to an authoritative execution-state owner through this
wrapper. A future composition would need to remove or deny the native mutation
path, or treat Beads as an explicitly non-authoritative planner projection.
