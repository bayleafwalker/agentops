# Autonomous investigation workflow

**Status:** Candidate source implementation. This delivery was built from the
six-stage summary and Cloud launch prompt in the task conversation. The named
roadmap attachment was not present in the Cloud workspace. Tracked plan/document
searches and GitHub code, issue and pull-request searches across the canonical
repos found adjacent owner guidance but not that named roadmap, so its exact
schemas and 14 named adversarial cases could not be reconciled. The tests listed
below are the candidate interpretation of the visible acceptance summary, not
a claim that they match an unseen file.

## Source reconciliation

Candidate source pins at startup:

| Repository | Commit |
|---|---|
| agentops | 67a450f60c6d3eebb363188d741d4c2d85da37b8 |
| vuoro | 1eae8ace228af39bd224565bac5be0a1fb7c4f25 |
| vuoro-cloud | 1aabd3aad9dbfd5ad2f72bfe9a8923c9b00f8622 |
| sprintctl | b76bd692060ca9b5f53f78d07ee187918a5d265d |
| actionq | 0fc77e8ec879228f576a83156a24a9758ca773c8 |
| actionq-dispatch | 42649f136fdc97430bc2bfb562bdea22927148a0 |
| auditctl | a3fe8de10fbfbfc4eacc842a9e26bcfc126820f6 |
| appservice | b560caa3db231cb3d2737db22d05a056d4f43e8d |

Existing capabilities and boundaries:

- scripts/harness_evidence/ captures bounded telemetry and optional raw
  artifacts under the accepted redaction and retention policy. Telemetry is
  non-authoritative and is not an investigation record.
- scripts/kaos_trace.py checks and reconciles a requirements map. It is
  read-only and is not a runtime probe planner or work ledger.
- jev/eval/agentops-2026-10-20/ reconstructs and scores a frozen dispatch
  classification experiment. It is not a system-incident investigation corpus.
- The existing Vuoro Cloud register_run, append_evidence and
  write_session_note tools provide run identity and evidence lineage. This
  CLI emits payloads for the existing append_evidence path; it adds no Vuoro
  object and cannot accept work or change authoritative status.
- Native harnesses retain model choice, external tool execution and session
  continuation. The CLI starts no worker, scheduler, model router, service or
  protected effect.

Repository plans and contracts reviewed after locating source material:

- `docs/plans/agentops/2026-10-18-kaos-2028-roadmap.md` assigns comparable
  outcomes, uncertainty, denominator and acceptance ownership to existing
  owners. Its learning requirements say that insufficient sample/capture is
  inconclusive and that experiment results do not automatically change policy.
- `docs/plans/agentops/2026-10-24-portable-agent-workflows.md` keeps execution,
  model choice and session continuation in the native harness, with durable work
  and evidence references crossing existing owner boundaries. It adds no
  general queue or second acceptance authority.
- `docs/dispatch/long-running-worker.md` requires persistent native continuation
  to be verified, forbids model substitution and production promotion, and
  excludes private workstation material from Cloud work.
- `docs/plans/agentops/2026-10-22-opportunistic-follow-through/outcome-measurement.md`
  and Vuoro's `accepted-outcome-learning.md` establish that the existing
  `ExperimentRecord` is for supplied owner acceptance, bounded case populations
  and measured burden. This diagnostic replay dataset does not claim owner
  acceptance or create a second measurement record. Its immutable artifacts can
  be referenced through an existing Vuoro run's `append_evidence` chain.
- `appservice/docs/training/README.md` describes the checked-in investigation
  reports as sanitized training materials. Three reports support a small
  source-pinned retrospective replay, but contain no frozen prediction tables
  or pre-registered diagnostic experiment. Only generic summaries and source
  references are included in the candidate fixture; raw commands, log output,
  hostnames and operational values are not copied.

The recently merged portable-agent-workflows plan is adjacent and informs the
native-runtime and authority boundaries; it is not the autonomous-investigation
roadmap and does not supply its schemas or acceptance cases.

These sources refine implementation boundaries; none is the missing named
autonomous-investigation roadmap. In particular, no repository source confirms
the unseen detailed schemas or exact 14 adversarial test names.

The read-only Vuoro work-list call returned an internal tool error, not an
empty result. No work item was inferred. A Vuoro run was not registered because
this Cloud surface did not expose an exact model ID or a digestable versioned
recipe/profile for the session. Persistent native Goal control was not
available in the exposed tool set, so unattended continuation is unqualified.

## Candidate workflow

An investigation is a directory artifact with an append-only events.jsonl
and a content-addressed objects/ store. Events use canonical JSON and a
SHA-256 predecessor chain. Local evidence records bounded outcomes and source
digests; raw source contents are not copied into the evidence object.

The local chain detects in-place edits during replay. It does not authenticate
the author or prevent someone from rewriting and re-hashing the whole chain.
Anchor the final report digest through the existing Vuoro evidence chain and
the candidate Git commit when durable provenance is required.

The investigator registers competing hypotheses with priors and a complete
prediction table for each probe before selecting it. The planner computes
expected entropy reduction, subtracts declared cost and risk, then selects the
highest-utility probe deterministically. The default risk ceiling is low;
raising it is an explicit run setting. Local execution has no shell, process
spawn, network access or write operation. Supported probes read a bounded
regular file beneath a caller-selected root and report only a predicate and
digest. Other probes run through the native runtime and are recorded as
external references with an outcome, collector and digest.

The CLI does not copy probe input contents, but it does persist probe
statements, configured literals, expected JSON values and evidence references.
Only use task-authorized, non-sensitive inputs. Do not record credentials,
private captures, raw prompts, raw outputs or workstation-only paths.

Replay verifies the event chain, validates probe transitions, checks stored
evidence digests and recomputes posterior updates without re-running probes.
An observation with zero pre-registered likelihood is retained as unexpected
evidence and does not move the posterior. A report returns insufficient_evidence
unless at least one observation exists, the posterior passes the configured
threshold and margin, and no unexplained outcome remains. Reports expressly do
not constitute owner acceptance.

Cold-session continuation uses the artifact directory itself: a fresh native
session can call plan, select, run or replay against the same artifact.
No background process or hidden conversation state is required.

## Stage mapping

| Stage | Candidate result | Remaining qualification |
|---|---|---|
| I0 | Source inventory, acceptance summary and 14 candidate adversarial cases | Compare against the missing roadmap and freeze its actual schema and test names |
| I1 | Strict hypothesis/probe inputs; hash-chained event artifact | Confirm required fields and versioning against the roadmap |
| I2 | Discriminating planner, risk ceiling, shell-free local probes, external observation references and content-addressed evidence | Qualify any domain-specific native probes and evidence retention rules |
| I3 | Event-sourced posterior updates, adaptive probe addition, deterministic replay and cold-session CLI resume | Persistent native Goal and cross-session platform continuation were unavailable |
| I4 | CLI, JSON reports and append_evidence payload generation for existing Vuoro runs | Actual Vuoro registration/append could not be exercised in this session |
| I5 | Deterministic dataset evaluator, synthetic demonstration, and a source-pinned replay of three sanitized Appservice incidents | Retrospective probe tables and labels are unblinded reconstructions; the set is not independent or prospective qualification |

## Candidate adversarial cases

The candidate suite contains 14 adversarial cases:

1. Duplicate JSON keys are rejected.
2. Priors that do not sum to one are rejected.
3. Duplicate hypothesis identifiers are rejected.
4. Parent traversal in probe paths is rejected.
5. Symlink probe targets are refused.
6. Shell and unknown probe implementations are refused.
7. Missing predictions for a hypothesis or outcome are rejected.
8. A partial trailing event line is preserved and rejected.
9. Event-content tampering breaks digest validation.
10. A lower-risk discriminating probe is selected over an equally informative high-risk probe.
11. Replay uses recorded evidence without re-running the probe.
12. Registered predictions cannot be replaced after use.
13. An unpredicted external result preserves uncertainty.
14. An interrupted probe cannot be automatically retried.

These cases exercise the candidate implementation. They do not qualify live
systems, protected operations, external probe adapters or a historical corpus.

## Reproducible offline demonstration

Run from the agentops repository:

    python3 scripts/investigation_workflow.py init /tmp/agentops-investigation-demo \
      --title "Synthetic configuration diagnosis" \
      --hypotheses scripts/tests/fixtures/investigation/hypotheses.v1.json \
      --repository bayleafwalker/agentops \
      --source-commit "$(git rev-parse HEAD)" \
      --artifact-ref _artifacts/investigations/synthetic-config-demo

    python3 scripts/investigation_workflow.py add-probe /tmp/agentops-investigation-demo \
      --file scripts/tests/fixtures/investigation/probe.v1.json
    python3 scripts/investigation_workflow.py plan /tmp/agentops-investigation-demo
    python3 scripts/investigation_workflow.py select /tmp/agentops-investigation-demo
    python3 scripts/investigation_workflow.py run /tmp/agentops-investigation-demo \
      --root scripts/tests/fixtures/investigation/source
    python3 scripts/investigation_workflow.py report /tmp/agentops-investigation-demo
    python3 scripts/investigation_workflow.py replay /tmp/agentops-investigation-demo
    python3 scripts/investigation_workflow.py evaluate \
      --dataset scripts/tests/fixtures/investigation/synthetic-known-cases.v1.json

The synthetic dataset is a deterministic mechanics demonstration. The
retrospective Appservice incident replay has a separate frozen digest and source
references:

    python3 scripts/investigation_workflow.py evaluate \
      --dataset scripts/tests/fixtures/investigation/retrospective-known-incidents.v1.json \
      --expected-digest sha256:e745c889020d5f3dfa8aea68c92b1c540ba0a4bc1e92b3c9c28a62a14c310a3c

The replay reports 3/3 reconstructed labels and 3/3 reviewer-selected probes,
with mean Brier score 0.06843. Because hypotheses, likelihoods and expected
probes were reconstructed after the incidents, this is an offline smoke
qualification of the deterministic planner and posterior implementation. It
does not measure an LLM investigator, establish prospective accuracy, or
qualify an independent historical benchmark. An independent reviewer and a
pre-registered or otherwise independently adjudicated case set remain I5 gates.

For an existing registered Vuoro run, initialize with --vuoro-run-id and
then run vuoro-evidence to render payloads for the existing evidence API.
The call that appends those payloads must use the actual run identity; this
repository CLI never creates a second work or acceptance authority.

## Verification and rollback

Focused source verification:

    python3 -m unittest scripts.tests.test_investigation_workflow -v

Historical replay evidence and dataset digest:

    docs/evidence/2026-10-24-autonomous-investigation-history-replay/README.md
    docs/evidence/2026-10-24-autonomous-investigation-history-replay/evaluation.json

Rollback is limited to reverting the candidate commit(s) or deleting the
candidate branch. The implementation does not write outside the selected
artifact directory and probe root, and its local probe operations are read-only.
Vuoro appends, when explicitly performed with an existing run ID, are immutable
evidence references; they do not alter work acceptance.
