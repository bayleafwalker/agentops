# The coherent-but-wrong context pair, measured

**Date:** 2026-08-29 · **Publisher:** auditctl 0.1.5 (the released wheel, installed) ·
**Scope:** two disposable repositories under a scratch directory, `alpha` and `beta`, each
holding a bare `.git` marker and nothing else. Nothing in `/projects/dev` was written to.

The contract's finding 2 asserts that `AUDITCTL_DB` alone, pointing elsewhere, "routes both
halves there consistently". This is that assertion measured rather than reasoned, because
the same page carries a retracted finding that was reasoned and wrong.

## The detection boundary

Every row publishes one event from `alpha/sub`. The only thing that varies is what the
environment says.

| # | `AUDITCTL_DB` | `AUDITCTL_ARTIFACTS_ROOT` | Outcome |
|---|---|---|---|
| 1 | unset | unset | correct — `repo_id` `alpha`, shard under `alpha` |
| 2 | `beta` | unset | **accepted.** Index, `repo_id` and shard all `beta` |
| 3 | `beta` | `beta` | **accepted.** Same as 2 |
| 4 | `beta` | `alpha` | refused: "the root must be the repository itself or an ancestor" |
| 5 | unset | `beta` | refused, same message |
| 6 | unset | the parent of both | accepted — `repo_id` stays `alpha`, shard moves to the pooled root |

So the boundary is exact, and it is not where the fix left it. 0.1.4 removed
`AUDITCTL_ARTIFACTS_ROOT`'s power to redirect: rows 4 and 5 are the fix working, and the
message is a good one. **`AUDITCTL_DB` retains that power in full.** It is a single
environment variable, writable by anything sharing the scope, that relocates identity,
index and shard together — and because it moves all three, there is no contradiction left
for the fail-closed check to find. Rows 2 and 3 are indistinguishable from row 1 by any
check the tool has: `rebuild --from-ndjson` over either scope afterwards reports both
stores clean, because each one *is* clean.

## The part that is worse than "undetected"

The 2026-08-29 misrouting was recoverable. Thirteen events were merged back verbatim with
set and digest equality verified, and the reason that was possible is that the defect was
*incoherent*: the index said one repository and the shard sat under another, so the
mismatch was itself the evidence of what had happened and of where each event belonged.

A coherent redirect leaves no such evidence. Here is the full record written by row 2 —
an event published from `alpha`, filed under `beta`:

```
"actor": "ctxprobe",  "source": "ctxprobe",  "event_type": "workflow.friction",
"origin_stream_id": "ed8497cf-…",  "origin_seq": 1,  "runtime_session_id": null,
"created_at": …, "occurred_at": …, "payload_sha256": …
```

There is no field naming the working directory, the repository, the host, or the session it
was published from. `runtime_session_id` — the one field that could have carried it — is
`null`, which is the Session-fragment gap the contract names, met head-on. So the event is
not merely filed in the wrong place: **nothing in it, or in the store around it, records
that it came from anywhere else.** An incoherent misroute is self-documenting; a coherent
one destroys the trail on the way in. That ordering matters for what gets built next: a
receipt written *after* the fact cannot reconstruct what the write itself never recorded.

## Row 6 is not a bug, and that is the difficulty

A pooled ancestor root is a deliberate live convention, and 0.1.4 accepts it by design
(ancestor-or-equal). But row 6 puts `alpha`'s events under `<parent>/_artifacts/alpha/`
while row 1 put them under `alpha/_artifacts/alpha/` — one repository, one `repo_id`, two
shard trees, both legitimate, selected by an environment variable. That is the
`homelab-analytics` "split and irreducible" store from the contract's finding 3, reproduced
deliberately in under a minute.

So the shard's location is not a function of the repository. It is a function of the
repository *and* an ambient value, which means "where do this repo's events live" has no
answer that can be derived from the repo alone — by a reader, a checker, or an applier.

## What this pins down for the applier

The channel is the finding, not the tool. Any consumer that receives its context through an
ambient value it cannot attribute has the same exposure, and an applier is the worst case
of it: it writes. Two properties fall out of the rows above and should hold for whatever
carries context next.

1. **A context must be attributable, not merely coherent.** Coherence is what rows 2 and 3
   already have. The missing question is not "do these values agree" but "who set them, and
   was that party entitled to". Rows 2 and 3 pass every check that exists because nobody
   asks the second question.
2. **The write must record the context it resolved,** not just act on it. Had row 2's event
   carried the directory it was published from, the misfiling would be a query rather than
   an archaeology problem — and the 13-event repair would not have needed a person.

Neither property needs a new resolver. Both need the context to arrive as something with an
author.

## Reproducing

Two `.git`-marked directories, the installed `auditctl`, and `env -u` to control the pair.
The full sequence is six `auditctl add` invocations differing only in environment; no
fixture, no network, nothing persistent. Total runtime under a minute.
