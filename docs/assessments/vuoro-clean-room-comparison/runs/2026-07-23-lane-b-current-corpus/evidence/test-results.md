# Lane B Current — Locked Sprintctl Corpus

The ten node IDs in
[`sprintctl-real-corpus-v1.yaml`](../../../fixtures/sprintctl-real-corpus-v1.yaml)
were run from the disposable clone at revision
`f22132c21ca17ad79d347ca1f43df8b3fe636c66`.

Command result: **10 passed in 0.08s**.

The passed obligations cover blocked activation, threaded exclusive-claim race,
proof-gated mutation, rotating handoff, lost-proof recovery, dependency-aware
resume, one next action under conflict, decision-event persistence, stale
command rejection, and served handoff token rotation. This is component-corpus
evidence only; see the manifest limits before treating any requirement as a
full lane verdict.
