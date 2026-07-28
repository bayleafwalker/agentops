# OpenCode Go semantic-routing assessment

Status: proposed next assessment; no production authority.

## Decision being tested

DeepSeek V4 Flash is admitted only for low-ambiguity mechanical implementation
behind coordinator-owned, discriminating gates. The next useful question is
whether Kimi K2.7 Code reduces total operational cost on bounded semantic work.
GLM 5.2 has no escalation assignment and Kimi K3 is benchmark-only.

This assessment cannot widen the existing `mechanical_bulk` pilot by itself.
Human admission requires frozen results and an independent review.

## Corpus

Run six to eight paired packets with identical packet bytes, tool rights,
repository commits, fixtures, registered commands, host/runtime versions, and
cache policy:

- two multi-file but mechanically specified implementations;
- two repairs starting from failing behavioural tests;
- two cross-layer semantic changes with frozen interfaces;
- optionally two adversarial fixture or verification tasks.

The final category is coordinator-only in production. It is included only to
measure whether either model detects an inadequate oracle; its output cannot
become production authority.

Each model gets one initial attempt and at most one repair attempt after a
materially revised coordinator packet. Reviewers are blind to model identity.
Packet contradiction or a missing oracle is recorded as `task_defect` and is
not dispatched.

## Measures

Primary:

- total operational cost: coordinator preparation, worker latency, review,
  correction, verification latency, and model cost;
- first-pass acceptance and elapsed time to an accepted candidate;
- coordinator correction minutes;
- blocking and non-blocking independent-review findings;
- semantic mutation or falsifiability score.

Secondary:

- focused- and full-gate results;
- semantically pointless reads and revisions;
- tokens, cache use, and provider-reported cost.

A model may cost materially more and still win if it reliably removes a
coordinator repair cycle.

## Reproducibility contract

Every corpus entry captures:

```yaml
runtime:
  host:
  opencode_version:
  provider:
  model_id:
  model_revision:
  context_window:
  temperature:
  tool_permissions:
  registered_commands:
  cache_policy:
inputs:
  packet_hash:
  repository_commit:
  fixture_hash:
  gate_set_hash:
outcome:
  candidate_commit:
  worker_declared_status:
  focused_gate_result:
  reviewer_verdict:
  coordinator_corrections:
  final_verdict:
```

Candidate bundle, transcript, receipts, focused/full gate results, and reviewer
outcome share one durable execution identity. Workstation observations do not
qualify devbox runs, and model/provider revisions form new assessment strata.

## Backlog

1. Migrate opted-in consumer manifests in their owning repositories:
   `vuoro` currently names `bulk` and `escalation`; `sprintctl` and `actionq`
   name `bulk`. Remove `escalation`, rename eligible mechanical admission to
   `mechanical_bulk`, and do not enable it until each repository can express
   the external oracle and discriminating acceptance properties.
2. Update actionq/actionq-dispatcher `hybrid-bulk-*` action naming or add an
   explicitly time-bounded compatibility mapping in those owning repositories.
   AgentOps does not own their runtime behavior.
3. Update the pinned `/etc/agentops` devbox policy only through its owning
   deployment repository, then re-run containment, credential, no-override,
   and cold packet gates before dispatch.
4. Extend run receipts with the complete reproducibility contract and stable
   execution-resource identity.
5. Add focused-gate versus full-gate stages and require `blocked` when the
   worker cannot execute its focused gate.
6. Add semantic-mutation/falsifiability scoring to independent review records.
7. Freeze the paired corpus and reviewer blinding procedure.
8. Run DeepSeek versus K2.7; publish an admission decision without assigning
   GLM or K3 production authority.
