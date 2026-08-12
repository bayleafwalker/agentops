# Vuoro release-batch Codex program investigation — 2026-08-11

**Status:** point-in-time investigation candidate

**Root Codex session:** `019fef40-40f3-7961-8be3-d5867fb8501d`

**Observation window:** 2026-08-11 05:25:57Z–20:37:38Z

**Repository baseline:** AgentOps `c91797d2a13fe3da9ca743d43609734e8a531848`

This report assesses the long Vuoro release-batch coordination program and its
Codex children. It separates recorded facts from interpretation. It is not a
release receipt, tracker authority, provider qualification, or audit finding.
No raw session body, credential, claim token, command output, or private
provider payload is committed here.

## Executive assessment

The program produced substantial reviewed work across AgentOps, Outctl,
ActionQ, Vuoro, and Vuoro Cloud while respecting several important safety
boundaries: dirty/detached worktrees were preserved, qualification gates were
not weakened, protected-main rejection was not bypassed, and independent
reviews issued real NO-GO verdicts that triggered corrections.

The principal weakness was coordinator economics. One root session remained
active for more than 15 hours and accumulated a 112,366-token live context at
the latest token snapshot despite six compactions. Its cumulative counter reported 216.6M
input tokens, of which 213.5M (98.58%) were cached. That headline is therefore
not fresh-token consumption, but the remaining 3.08M uncached input plus
195,116 output tokens still indicates a very large coordination surface. The
record also contains 198 agent-wait calls, 455 generic wait calls, repeated
operator requests for status, and at least one failed spawn caused by the
thread limit.

The review loops were valuable but not consistently bounded. Reviews caught
authority, compare-and-swap, capability-limit, and evidence-binding defects.
However, some reviewer sessions stayed open for hours around unavailable
external gates, and the root repeatedly polled rather than yielding to durable
completion signaling. The missing ActionQ completion-log API was correctly
left disabled; that decision also explains why the coordinator could not use
the desired durable completion path.

## Evidence boundary and reproduction

The root rollout was still growing when this point-in-time report was made.
The stable evidence boundary is its first 10,656,991 bytes (7,470 complete
JSONL records), SHA-256
`319fe9936789e83c538d12ef3a849c1ce43be31daf7efbc36f842a67f067c5fd`:

```bash
LOG=/home/agent/.codex/sessions/2026/08/11/rollout-2026-08-11T08-16-33-019fef40-40f3-7961-8be3-d5867fb8501d.jsonl
head -c 10656991 "$LOG" | sha256sum
head -c 10656991 "$LOG" | jq -r \
  'select(.type=="event_msg" and .payload.type=="token_count" and .payload.info!=null)
   | [.timestamp,.payload.info.total_token_usage.input_tokens,
      .payload.info.total_token_usage.cached_input_tokens,
      .payload.info.total_token_usage.output_tokens,
      .payload.info.total_token_usage.reasoning_output_tokens,
      .payload.info.total_token_usage.total_tokens,
      .payload.info.last_token_usage.input_tokens,
      .payload.info.model_context_window] | @tsv' | tail -1
head -c 10656991 "$LOG" | jq -r \
  '.type + "\t" + (.payload.type // "")' | sort | uniq -c
head -c 10656991 "$LOG" | jq -r \
  'select(.type=="response_item" and .payload.type=="function_call")
   | .payload.name' | sort | uniq -c | sort -nr
```

Twenty-two local Codex rollout files identified the root or a descendant by
that session ID. Their frozen sorted path manifest is
[`vuoro-release-batch-codex-program-investigation-2026-08-11-child-rollouts.txt`](vuoro-release-batch-codex-program-investigation-2026-08-11-child-rollouts.txt).
The path-list digest at discovery time was
`f0a2c15e5a4ceb0731e8707fc3043332b231e83560baaad808e62b6ffc6caca7`.
The set comprised the root plus 21 named child sessions. This count does not
include provider work launched outside Codex's local rollout store.

```bash
sha256sum \
  docs/assessments/vuoro-release-batch-codex-program-investigation-2026-08-11-child-rollouts.txt
```

Repository facts were checked with `git show -s --format='%H %s' <sha>` in each
owning checkout; they are not expected to resolve from this AgentOps worktree
alone. Locally resolvable examples include:

- Outctl W1 `e4e0f0db27fb39986f161c1adb71c94ea9ee699c` and W2
  `958374a6eed81c83f432e7be674de7c661d85a06`;
- AgentOps #2116 `a9fe337655afb0dc24ea71316163dc7b1ccedb7a`, #2118
  `47e6de69f2d3971b4ec4299c514a8d8e0ac0819d`, and #2142
  `0d267773d4653dac3de6610095527c2bfac1127d`;
- Vuoro gateway identity `d5a549ff00ffd7cb51c5c626c62a82d5d6608b0d`
  and later rendered-guidance merge
  `8c63905356893f8cc1b61c14d92c31104f2939ac`;
- ActionQ CI remediation merge
  `11262336b7aa6174ea0f703a66d7d443ba0954ef`.

## Measured facts

Token and live-context fields below are the latest token snapshot inside the
evidence prefix, at 20:37:35Z. Event/tool counts cover the full prefix through
its final complete function-call record at 20:37:38Z.

| Measure | Recorded value | Interpretation limit |
|---|---:|---|
| Root elapsed span | 15 h 11 m 41 s | Includes waits and operator pauses; not active compute time. |
| User messages | 36 | Includes status, correction, authorization, and handoff prompts. |
| Completed root turns | 46 | The root session was still active. |
| Context compactions | 6 | Does not disclose the exact retained-token content per compaction. |
| Child spawn calls | 25 | Twenty-one descendant rollout files were found; retries/failed spawns and externally launched providers prevent one-to-one attribution. |
| Child follow-ups / messages | 30 / 29 | Delivery does not prove the child acted on every message. |
| Agent-list / agent-wait calls | 50 / 198 | Wait duration and useful versus redundant polling are not directly summarized. |
| Generic waits | 455 | Tool semantics vary; this is not 455 failed operations. |
| Shell command executions | 945 | Counts invocations, not command cost or success. |
| Cumulative input tokens | 216,554,298 | Model counter is cumulative across turns and cache-heavy. |
| Cached input tokens | 213,470,208 (98.58%) | Cached tokens are not equivalent to fresh input or billed cost. |
| Uncached input difference | 3,084,090 | Derived as input minus cached input; still not a provider invoice. |
| Output tokens | 195,116 | Root counter only; child/provider attribution is not safely additive. |
| Reasoning-output subset | 38,094 | Reported separately by the runtime and not added again to total. |
| Cumulative total tokens | 216,749,414 | Equals reported input plus output. |
| Live context / model window | 112,366 / 258,400 (43.49%) | Latest token snapshot, not peak context. |

The six recorded compactions occurred at 06:20, 08:55, 14:29, 17:16,
18:21, and 19:24 UTC. The operator later requested automatic handoff/compaction
at 100k context. The point-in-time live context was already above that
threshold, so the desired control had not yet become automatic.

## Outcome record

### Repository-verified or review-recorded outcomes

- The Outctl migration advanced through a merged W1 contract/oracle and W2
  native skeleton. W3 reached an independent NO-GO: advertised 256 MiB capture
  capacity was not enforced by the CLI/API, and symlink defenses retained a
  check-then-use concern. This is evidence that review was independent rather
  than ceremonial; W3 was not published at the cutoff.
- AgentOps #2118 corrected its OpenCode qualification probe to the actual
  top-level `sessionID` shape and added evidence-growth binding. A single paid
  contained-provider lifecycle was operator-reported as successful at
  $0.0007385056, but formal qualification remained blocked on the missing
  executable final corpus.
- AgentOps #2142 produced a bounded qualification corpus. The devbox lacked
  the privileged runner/state needed for the authorized one-shot paid run, so
  execution was handed to the workstation/root boundary instead of weakening
  the gate.
- Vuoro's gateway identity slice is locally resolvable at `d5a549f…`; a later
  locally resolvable merge `8c63905…` contains rendered guidance. The Cloud
  follow-up passed an independent cross-repository review, but direct push to
  protected `main` was rejected and left for PR/maintainer merge.
- ActionQ correction work recorded focused and full test evidence while
  preserving unrelated frozen artifacts. Later workstation information says
  the CI evidence refresh merged at `1126233…`, which is locally resolvable.
- Completion alerts were deliberately not activated after the expected
  served `/session-completions` surface returned HTTP 404. Packaged consumer
  code remained available for a later release rather than presenting a false
  degraded success.

### Operator-reported but not locally reproduced in this investigation

- A workstation release package was reported verified and retention-pinned
  with SHA-256
  `2669cc79085105119790019e3afdaf5731fc94ca862f3a7431daaa9b36c5c1ed`.
  Its `.session/project-release-20260811T2033Z` files were not present in the
  inspected devbox paths, so this report does not independently attest them.
- Pull-request merges #34/#35 (AgentOps), #20 (ActionQ), #29 (Vuoro), and #1
  (dispatcher) were reported by the operator. The relevant AgentOps/Vuoro/
  ActionQ commits above are locally resolvable, but this investigation did not
  query GitHub or recompute the complete package.

## Delegation and correction-loop assessment

### What worked

- **Reviews changed outcomes.** #2116/#2118 and #2124 used re-review sessions;
  Outctl W1 received a long corrective review; Vuoro #2126 used review, fix,
  workflow review, final review, and clean gate; W3 was stopped by a concrete
  capability-limit defect.
- **Authority remained separated.** Reviewers did not merge their own
  candidates, protected-branch rejection was honored, external qualification
  stayed fail-closed, and deployment was left to the workstation when the
  devbox lacked authority.
- **Delegated tasks were usually bounded by worktree and issue.** Named child
  paths make the review graph reconstructable, and later corrections cite
  exact commits and targeted gates.
- **The root corrected routing after feedback.** The operator clarified that
  Luna should run through Codex rather than OpenCode Go; later work used Codex
  children and Terra-class review roles.

### What was inefficient

- **The root became the durable scheduler.** Frequent `list_agents` and wait
  calls, repeated “Done?”/“Check up” prompts, and the failed attempt to move a
  live SSH-bound session into tmux show that continuity depended too heavily
  on one terminal and one context.
- **Slots stayed occupied by waiting or superseded work.** At the meta-review
  dispatch, the thread limit caused a spawn failure; an existing nested W3
  oracle had to be stopped/reused to free capacity. Reviewer sessions for
  #2142 and #2126 spanned roughly three and two-and-a-half hours respectively,
  much of which cannot be distinguished from waiting.
- **Correction packets were sometimes underspecified.** #2124 required
  separate initial, CAS, and authority reviews. W3 needed an oracle analysis
  after implementation had already begun, and the first independent review
  found a straightforward advertised-limit mismatch. Both suggest that
  falsifying invariants should have been frozen before build dispatch.
- **Status communication lagged work state.** The operator asked for status
  repeatedly. The root did create compact handoffs, but only after prompts and
  after large context growth.
- **Cross-host truth arrived asynchronously.** Workstation CI/package updates
  superseded the root's earlier handoff. Without a signed/shared completion
  feed, the coordinator could only reconcile operator messages against local
  Git state after the fact.

## Tool and session failures recorded

1. Provider inference initially returned HTTP 403 `RegionError`; workspace
   opt-in for Chinese providers resolved it. The record supports configuration
   failure, not credential or network failure.
2. The #2118 probe assumed a fabricated response envelope; OpenCode 1.18.4
   actually emitted top-level `sessionID`. Two commits corrected the oracle.
3. `tmux new -s codex resume <session>` exited immediately. The successful
   operational lesson was to start a shell/session correctly inside tmux, not
   to assume that command shape preserved the already-running process.
4. A child spawn failed because the agent-thread limit was reached.
5. One W3 reviewer environment lacked `cargo`, so it could run Rust unit tests
   already available in the candidate but not the full cargo-dependent W3
   gate. The coordinator's environment had stronger prior gate evidence.
6. Vuoro Cloud direct-main push was rejected by branch protection; no bypass
   was attempted.
7. Served completion ingestion was absent (HTTP 404), preventing durable
   completion signaling and leaving polling as the fallback.
8. Dirty, detached, ahead, and derived worktrees plus project-context drift
   were present at startup. The root fetched/pruned but did not overwrite
   those states.

## Improvements

### Immediate operating changes

1. **Bound the root session.** Produce a signed/raw-free handoff at 80k live
   context and start a successor by 90k. Treat 100k as a hard stop, not the
   trigger to begin preparing.
2. **Replace polling with durable completion records.** Until ActionQ P3
   exists, use a host-local mode-0600 completion ledger with session ID,
   task path, candidate SHA, terminal status, and receipt digest. Poll that
   bounded ledger, not every agent at 30-second cadence.
3. **Reserve one review slot.** Run at most two implementation children when a
   four-slot tree includes root; keep one slot available for independent
   review/correction. Close completed/superseded children promptly.
4. **Freeze a falsifying packet before build.** Require exact base SHA,
   authority boundary, invariants, negative fixtures, maximum limits, and
   executable gates. Review the packet first for high-risk process, CAS,
   qualification, and cross-repository work.
5. **Time-box external-gate reviewers.** If credentials, root, provider opt-in,
   or a protected merge is unavailable, return a blocked verdict and release
   the slot. Resume with a fresh reviewer when evidence becomes available.
6. **Separate coordinator and provider telemetry.** Record per-child start/end,
   model/provider, uncached/cached input, output, tool calls, retry count,
   outcome, and cost when exposed. Never sum cumulative child counters without
   proving their accounting scope.
7. **Standardize progress intervals.** Emit a concise status on state change or
   every 10–15 minutes during long gates: completed, active agents, blocker,
   and next event. This addresses operator uncertainty without verbose polling.

### Product/process changes

- Implement the planned ActionQ completion log with durable ingestion,
  acknowledgements, replay, retention, scoped credentials, and the served API
  before activating the cockpit consumer.
- Add a session-investigation exporter that emits raw-free per-turn metrics and
  stable prefix digests. Current JSONL is rich but requires ad hoc `jq`, and
  its cumulative token semantics are easy to misread.
- Validate reviewer toolchains before dispatch. A process/Rust review should
  fail preflight when `cargo` or the pinned toolchain is unavailable.
- Store cross-host release receipts in a shared, content-addressed authority
  visible to both workstation and devbox. Chat updates should announce a
  receipt, not be the only copy of it.

## Missing telemetry and confidence

High confidence applies to root event counts, token fields, timestamps,
compaction times, child names, local Git object resolution, and review messages
inside the stable prefix.

The following are missing or ambiguous:

- token counters do not state whether child totals are globally cumulative,
  session-local, or billing-equivalent; child totals are therefore not added;
- no reliable active-versus-idle latency decomposition or per-tool duration
  aggregate exists;
- OpenCode/Luna/Terra provider runs outside Codex are not uniformly present in
  the local rollout store;
- per-agent monetary cost is absent except the single operator-reported paid
  qualification amount;
- peak context before each compaction is not directly summarized;
- failed tool calls lack one normalized error taxonomy;
- tracker notes are referenced in handoffs, but this investigation did not
  mutate or comprehensively export Sprintctl state;
- the root session continued after the cutoff, so W3 correction and later
  release outcomes are intentionally not claimed here;
- workstation package files were not locally available for independent hash
  verification.

These limitations make the report suitable for process improvement and
candidate review, but not for billing reconciliation or release attestation.
