# Autonomous investigation retrospective incident replay

This artifact replays three generic case summaries derived from sanitized,
committed Appservice training reports at source revision
`b560caa3db231cb3d2737db22d05a056d4f43e8d`:

- shared node pressure behind cross-workload health-probe timeouts;
- a parked-service monitoring target mismatch;
- application maintenance after an incomplete upgrade despite healthy routing.

The source references are embedded in
[`retrospective-known-incidents.v1.json`](../../../scripts/tests/fixtures/investigation/retrospective-known-incidents.v1.json).
The fixture contains abstracted symptoms and labels, not copied commands, raw
logs, hostnames, URLs, credentials or private captures.

## Reproduce

From the agentops repository root:

```bash
python3 scripts/investigation_workflow.py evaluate \
  --dataset scripts/tests/fixtures/investigation/retrospective-known-incidents.v1.json \
  --expected-digest sha256:e745c889020d5f3dfa8aea68c92b1c540ba0a4bc1e92b3c9c28a62a14c310a3c
```

The frozen result is [`evaluation.json`](evaluation.json).

## Qualification limits

This is a retrospective, unblinded smoke qualification. The hypotheses,
likelihood tables and expected first probes were reconstructed from completed
reports; the source incidents did not preserve those pre-registered predictions.
The score therefore checks deterministic ranking and posterior replay against
this curated table. It does not establish prospective accuracy, LLM investigator
quality, causal attribution or independent validation. No owner acceptance or
policy decision is inferred. I5 remains open until an independent reviewer
qualifies a representative case set with independently adjudicated labels and
denominators.
