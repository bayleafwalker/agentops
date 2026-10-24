# Native 2.1.309 synthetic acceptance projection

This record projects the appservice collector receipt into metadata for AgentOps.
It contains the pinned collector digest, source commit, config and receipt hashes,
case counts and mutation outcomes. It contains no OTLP records, fixture values,
credentials or response bodies.

The appservice candidate was `7fabc910445292eb7dd5acbac636f5fd572ebf43` on
`cloud/20261024/programme-06-telemetry`. Its pinned Alloy gate passed 62 cases
(54 exported records, 8 refused inputs) and all seven fresh-control mutation
pairs. The captured receipt SHA-256 is recorded in
[`2026-10-24-native309-synthetic-acceptance.json`](2026-10-24-native309-synthetic-acceptance.json).

To regenerate after checking out the cited appservice candidate, first produce
the bounded receipt, then project it from this repository:

```sh
python3 docs/scripts/run_native309_alloy_acceptance.py \
  --receipt /tmp/native309-alloy-20261024.json
python3 scripts/project_native309_acceptance.py \
  /tmp/native309-alloy-20261024.json \
  --source-commit 7fabc910445292eb7dd5acbac636f5fd572ebf43 \
  --output docs/evidence/2026-10-24-native309-synthetic-acceptance.json
```

The projector refuses another Alloy digest, incomplete matrix, failed or
unexpected mutation, non-synthetic receipt, extra receipt fields, and receipts
over 32 KiB. The result is source and synthetic qualification only; it does not
claim production sink, live model, activation or user acceptance.
