# W41-R1 advisory routing comparison — 2026-10-20

**Keep production routing unchanged.** On 33 held-out attempts from 16 work
groups, the cheap native arm had 60.6% non-abstaining coverage, below the
preregistered 90% requirement. Joint lane/tier agreement with recorded choices
was 15.2%, versus 18.2% for the deterministic comparator. Group-weighted
agreement was 20.8% versus 27.1%. These results establish no benefit that
justifies adopting a new classifier.

Recorded choices are an **imitation target**, not independent safety labels.
Both methods disagree substantially with them. Neither experimental arm is
qualified as a safe router here, and the comparator is not a proposed
production replacement. No permissions, model policy or Vuoro authority change
follows from this experiment.

## Method and source

`protocol.json` was committed before predictions. Fifty real dispatch attempts
cover 24 work items forming 23 connected groups. Shared-item attempts stay
together: 17 calibration cases and 33 held-out cases. All 50 historical
input revisions were reconstructed and hash-verified from served edit events;
nine later edits were rewound. Current edited text was never substituted.
None overlap the September 28 benchmark.

`corpus.json` binds source Git revision, input bytes and split. Inputs were
deidentified before transmission. Public Git contains hashes, labels, code
and results, with no case prose. The ignored private `cases.jsonl` working
copy is session-local; existing `_artifacts` source snapshots are
host-persistent, not durable-authoritative. The original route shards are
Git-replicated and edit history is served-authoritative.

`reconstruct.py` rebuilds the exact frozen bytes from those existing sources,
verifies the published SHA256, and defaults to writing nothing. Rebuilding
from the captured source history matched all 50 cases exactly. A cross-host
replay needs the pinned Git history and ordinary authorized served reads;
it must not trust an unverified copy of the private working file.

Historical labels retain lane, tier and source. Original escalation prose
was not recorded, so that label is explicitly missing. Predictors emit an
enumerated rubric reason; they do not reconstruct the original rationale.

## Arms and limits

The deterministic comparator freezes the earlier keyword heuristic and adds
explicit-tier/build, open-design/refine and missing-check/oracle rules. The
native arm uses the existing permitted Claude subscription and exact
`claude-haiku-4-5-20251001` model, with tools/MCP/hooks disabled, no session
persistence and a 30-second case limit. The user explicitly approved exporting
the deidentified cases to Haiku after automatic review initially denied it.
No paid API key or Decisions API call was used. The Decisions arm is unmeasured;
no other model substitutes for it.

All 50 predictions remain, including failures. Malformed, uncertain, timeout
or unqualified-model output abstains and keeps the comparator answer. That
fallback does not count as native coverage. Synthetic negative tests force
malformed output, uncertainty, another model and timeout and verify that
fallback cannot grant tools/MCP authority.

Held-out native invocation latency was 25.6 seconds median and 30.0 seconds
p95, including CLI startup and structured-output handling. Rules took about
0.00011 seconds median and 0.00065 seconds p95. These are invocation times,
not isolated model/API latency.

`results.json` includes lane/tier confusion matrices, case/group agreement,
false-escalation and under-escalation proxies, coverage and latency. The
native arm had 8 false-escalation proxies and 10 under-escalation proxies;
rules had 9 and 14. These are disagreements with historical choices, **not
measured unsafe outcomes**. Actual billed subscription cost and human
correction time remain null. Provider list-price observations in prediction
records are not billing receipts. These missing observations also prevent
satisfying the preregistered adoption conditions.

The independent sample is 23 groups overall and 16 held-out, not 50 independent
jobs. One tracker, imperfect labels, absent original rationale and text-only
replay limit this conclusion. Do not tune on these held-out results and call
the same cases unseen again.

## Reproduce

```bash
# Verify reconstruction without making another private copy:
python3 jev/eval/agentops-2026-10-20/reconstruct.py
# Explicitly restore the ignored replay file only when needed:
python3 jev/eval/agentops-2026-10-20/reconstruct.py --restore-ignored-input
# Re-score the frozen predictions without inference:
python3 jev/eval/agentops-2026-10-20/evaluate.py
python3 -m unittest discover -s jev/eval/agentops-2026-10-20 -p test_evaluate.py -v
```

`--run-native` is an explicit experiment entrypoint and refuses existing
predictions. It never retries or selects held-out answers. A new inference
experiment needs a new dated protocol and untouched held-out population.
