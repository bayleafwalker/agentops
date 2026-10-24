# Autonomous investigation synthetic demo

This committed artifact exercises one read-only probe against a synthetic
configuration fixture. It contains no historical incident data and makes no
claim about a deployed system.

## Result

- Source implementation: agentops commit
  a34737f8f5508d3967bb45b7c78148b0224368f1
- Final event head after report creation:
  sha256:da02b7dad6d6cbcffd303060d304042be18b45a6d5e58c68e89e1fdabe1d84ad
- Observation object:
  sha256:d9599ff3b70a4237f8b35125a7bef862ee261be37390850ed2b2353d561274d0
- Report object:
  sha256:5d5349cf0aa16c2d9cfde67f067fe09832256110021181ab6042ad3fe0239025
- Evaluation dataset:
  sha256:6f62402e6eac8c69f8334b183900fc3af94af75cc2e44a80f29bffb57bc3ebf1
- Offline synthetic result: one case, correct top hypothesis, correct first probe,
  Brier score 0.0002040608, no abstention.

The evidence object records the predicate outcome and SHA-256 of the input file.
It does not contain the source file bytes. The report keeps the probability
model, chosen probe, observation reference and stop reason together.

## Replay

From the agentops repository:

    bin/agentops investigation-workflow replay \
      docs/evidence/2026-10-24-autonomous-investigation-demo

The command verifies the event chain and evidence-object digest, then
reconstructs the same posterior without reading the source fixture again.

## Rebuild

Use a fresh directory, then run:

    bin/agentops investigation-workflow init /tmp/agentops-investigation-demo \
      --title "Synthetic configuration diagnosis" \
      --hypotheses scripts/tests/fixtures/investigation/hypotheses.v1.json \
      --repository bayleafwalker/agentops \
      --source-commit a34737f8f5508d3967bb45b7c78148b0224368f1 \
      --artifact-ref docs/evidence/2026-10-24-autonomous-investigation-demo
    bin/agentops investigation-workflow add-probe /tmp/agentops-investigation-demo \
      --file scripts/tests/fixtures/investigation/probe.v1.json
    bin/agentops investigation-workflow select /tmp/agentops-investigation-demo
    bin/agentops investigation-workflow run /tmp/agentops-investigation-demo \
      --root scripts/tests/fixtures/investigation/source
    bin/agentops investigation-workflow report /tmp/agentops-investigation-demo --write
    bin/agentops investigation-workflow replay /tmp/agentops-investigation-demo

The demonstration is intentionally synthetic. The historical-incident corpus
from the unprovided roadmap remains a qualification gate.
