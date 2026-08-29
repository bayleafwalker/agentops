# `resume-and-settle` — recorded runs

`events.db` is the authority here; the Markdown files are projections of it and can be
rebuilt (`acceptlab report --db events.db --run-id <id>`). It is committed rather than the
reports alone because acceptance-lab's own rule is that the event log is authoritative and
projections are disposable, and keeping only the projection inverts that.

| Run | Scenario | Status | Score | What it says |
|---|---|---|---|---|
| `762d7235` | 1.0.0 | FAIL | 0.694 | The first run. Failed `served-surfaces-only` on the probe's own arrange-phase writes — the gate was mis-stated, not the platform. Kept rather than rescored. |
| `15f82e69` | 1.0.1 | FAIL | 0.722 | The corrected gate passes. Three hard gates still fail, all on one thing: the checkpoint and its exact revision do not survive an interruption. |

Five hard gates pass, including the two that matter for authority: nothing local was used
as a source, and every change carried a receipt. Session identity and work authority were
both recovered *and* matched what the interrupted session actually held.

The fix is `sprintctl` branch `fix/handoff-checkpoint-survives-interruption`, two commits:
the served handoff crashed outright whenever a sprint had an active reservation, and the
handoff record discarded the checkpoint it was given. Neither is deployed. Re-run the probe
and re-evaluate after the deployment carries them, and the expected result is a `PASS` —
that prediction is the point of recording this failure with a date on it.
