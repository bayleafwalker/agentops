---
description: Bounded MI-1 Track A comparison; install only for the approved experiment.
on:
  workflow_dispatch:
    inputs:
      case:
        description: Frozen comparison case
        required: true
        type: choice
        options: [receipt-audit, ci-diagnosis]
permissions:
  contents: read
concurrency:
  job-discriminator: ${{ github.run_id }}
checkout:
  fetch-depth: 0
engine: claude
network: defaults
timeout-minutes: 15
max-turns: 12
max-ai-credits: 100
tools:
  bash: ["git show:*", "git status:*", "python3:*"]
  edit:
safe-outputs:
  report-failure-as-issue: false
  create-pull-request:
    title-prefix: "[MI-1 Track A] "
    draft: true
    max: 1
    base-branch: main
    fallback-as-issue: false
    auto-close-issue: false
    allowed-files: ["docs/experiments/mi1-tracka/results/*.md"]
    max-patch-files: 1
    max-patch-size: 32
---

Read docs/experiments/mi1-tracka/README.md and cases.json. Execute only the
selected case: ${{ inputs.case }}. Use the frozen revisions and exact input
bytes named in the case ledger, rather than the latest receipt or historical
workflow. The native comparator receives this same task and ledger.

Inspect the relevant source and public records. Run deterministic read-only
checks when useful. Write one concise Markdown report under
docs/experiments/mi1-tracka/results/ with citations to files, revisions and
checks actually examined, findings and remaining unknowns. Do not fabricate
commands, observations, usage, cost, operator time or acceptance. The report
is an agent proposal; a separate reviewer applies the predeclared rubric.

Open exactly one draft pull request with the report through create_pull_request,
including when no defects are found. Keep effect credentials and owner APIs
outside this runtime. Stop if the frozen inputs are inaccessible or differ.
Do not start other agents or modify any file outside the report directory.
