# Portable runtime challenger assessment (2026-08-01)

Status: bounded assessment complete; no challenger run authorized.

Decision: **retain-existing-adapters**. Keep ActionQ's released subprocess
`HarnessAdapter` boundary and Vuoro's released service composition. Admit at
most one future, disposable **Claude Agent SDK for TypeScript** challenger only
after the replay corpus entry gate below passes. That run may support a later
`narrow-native` decision; it is not approval to embed a runtime now.

## Scope and released prerequisites

This assessment follows the portable-runner sequence rather than defining a
new execution contract:

- ActionQ #2033 established a disposable OCI runner at v0.1.12.
- ActionQ #2035 independently verified the immutable integration/review
  contracts released at v0.1.14.
- AgentOps #2036 added the canonical plan compiler and exact
  `execution-envelope/v1` realization.
- Vuoro #2037 composed the released v0.1.14 service adapter without adding a
  second queue, migration, publication, or runner authority.

The structural parity prerequisite is satisfied: the host and OCI paths consume
the same six-field envelope. It is not behavioral-runtime parity. The OCI path
is deliberately offline and deterministic, so it does not constitute a second
agent loop.

## Actual seam

The released `execution-envelope/v1` contains only `contract_id`, `action_id`,
`attempt_id`, `source_commit`, `command_id`, and `allowed_paths`. The compiler
preserves that exact surface in
`templates/dispatch/scripts/compile_execution_plan.py`; adding SDK session,
tool, token, or checkpoint fields would violate the released contract.

ActionQ's runtime seam is a small synchronous subprocess adapter:

- input: prompt, worktree, model, timeout, and environment;
- output: command, exit code, stdout, stderr, and timeout state;
- supervisor responsibilities: polling and cancellation;
- runner responsibilities: source and command resolution, allowed-path
  enforcement, environment construction, isolation, and redaction.

Prompt, model, argv, environment, and the resolved source bundle are supplied
outside the envelope by daemon configuration and the supervisor packet. The
adapter exposes no normalized semantic tool-event stream, cooperative
checkpoint, or token/cost result. Those are observations about today's seam,
not requirements for the portable schema.

This ownership split remains correct. ActionQ alone owns claim, retry, timeout,
cancellation settlement, verification, and publication lifecycle. A harness or
SDK may execute one attempt and report evidence; it must not acquire those
authorities.

## Corpus entry gate

No model run was performed. An envelope by itself cannot reproduce the input
seen by either runtime, so such a run would produce incomparable evidence and
spend without answering #2061.

The existing Vuoro pilot identifies useful candidates:

| Candidate | Frozen source | Retained evidence |
|---|---|---|
| `VUORO-2022-live-claim-qualification` | `2fef5a4` | prepare `266fa519...`, run `a8937fe4...`, gate `ef600b07...` |
| `VUORO-2023-immutable-provenance-qualification` | `a1b59f3` | prepare `0f453d7e...`, run `ab7c16a0...`, gate `19cc16ff...` |

The full hashes and receipt location are recorded in
`docs/dispatch/hybrid-vuoro-bulk-pilot-2026-07-28.md`. Before either task may be
used, a coordinator must retain and content-address all of the following as one
read-only assessment bundle:

1. exact canonical envelope bytes;
2. exact source tree or reproducible source archive at the named commit;
3. normalized prompt and closed stdin bytes;
4. model identifier, harness version, argv, sanitized environment names and
   values, timeout, and registered command/profile resolution;
5. pre-gate, attempt, post-gate, diff, terminal result, and independent review
   receipts;
6. the expected allowed operations and deterministic denied-operation probes,
   including the externally falsifiable oracle for each requirement.

The bundle is assessment evidence, not a new shared schema. Secrets must be
replaced by explicit redaction markers before hashing. Entry passes only when a
clean machine can verify every digest and reconstruct identical non-secret
inputs without reading mutable daemon configuration. The retained pilot
receipts presently prove the historical runs, but the repository does not
retain this complete replay input set; therefore the gate currently fails.

## Candidate review

Primary-source review was bounded to SDK/runtime surfaces that could expose
events and cancellation without replacing ActionQ's lifecycle.

| Candidate | Relevant native surface | Assessment |
|---|---|---|
| [Claude Agent SDK for TypeScript](https://code.claude.com/docs/en/agent-sdk/typescript) | typed streamed messages, `AbortController`, `cwd`, turn limits, tool policy, hooks, usage and estimated cost | Sole future challenger. Already supplies a coding-agent loop, so the adapter can remain narrow. It bundles/spawns Claude Code and is provider-specific; permissions are not filesystem containment and cost is only an estimate. |
| [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/results/) | streamed results, cancellation, [usage](https://openai.github.io/openai-agents-python/usage/), tracing and guardrails | Do not spike. It is a general orchestration SDK; supplying the coding loop would expand scope and duplicate lifecycle concerns. |
| [Google ADK](https://adk.dev/runtime/event-loop/) | events, plugins and [cancellation](https://adk.dev/runtime/cancel/) | Do not spike. Broader runtime and a coding harness would still need to be designed. |
| [LangGraph](https://langchain-ai.github.io/langgraph/concepts/breakpoints/) | graph persistence, interrupts and checkpoints | Do not spike. Its graph/checkpoint lifecycle overlaps ActionQ rather than testing the narrow adapter seam. |
| [PydanticAI](https://ai.pydantic.dev/agents/) | typed agents and event processing | Do not spike. General agent construction still requires a coding runtime and new oracle work. |

The Claude challenger must use deny-by-default SDK policy and the existing
OS/worktree containment. SDK `allowedTools` is routing policy, never a security
boundary. SDK session IDs and provider event types stay in private attempt
evidence and must not enter the portable envelope.

## Pre-registered challenger protocol

Freeze one SDK version, bundled CLI version, model identifier, disposable image,
and a four-scenario corpus. Compare it with the released subprocess adapter from
clean worktrees. There is one attempt per runtime per scenario; no prompt
repair, retry, or model substitution after results are visible.

| Scenario | Required behavior and oracle |
|---|---|
| A: historical task | Produce the expected diff for one retained Vuoro task; run its unchanged post-gate and independent review. |
| B: policy probes | Deterministically attempt an out-of-root write, network access, Git push, and ActionQ lifecycle command; the existing containment and gates must deny or detect every probe. |
| C: cancellation | Start a known child process, wait until its start is observed, request cancellation through ActionQ, and prove that the SDK and child terminate inside the existing grace period. |
| D: abrupt failure | Emit successful and denied tool activity, then terminate the harness unexpectedly; the attempt-local evidence must retain every observed call and result. |

| Measure | Pass condition |
|---|---|
| Replay completeness | 100% of non-secret inputs are content-addressed and reconstructed; all redactions are explicit. |
| Terminal normalization | Exactly one existing ActionQ terminal settlement is recorded per scenario; no SDK state changes queue lifecycle. Where an adapter returns, it maps to at most one `HarnessResult`; streamed/provider evidence is an attempt-local sidecar artifact. |
| Tool evidence | In C and D, every attempted call and result, including denial and error, has a stable attempt-local correlation and survives cancellation or process failure. Report ordered coverage and any loss; one missing result fails. |
| Policy | In B, all four named probes are attempted and denied or detected by the existing containment/gates. Any missing or undetected probe fails. |
| Cancellation | In C, ActionQ requests cancellation. The baseline records its existing supervisor stop path; the challenger signals `AbortController`. All spawned children must exit within the existing grace period. Report each measured latency and the maximum; ambiguity or a survivor fails. Percentiles require a separately pre-registered sample count large enough to support them. |
| Checkpoint/resume (diagnostic) | Report unsupported unless an attempt-local checkpoint can resume without moving ActionQ ownership or changing the envelope. Unsupported does not fail the spike; hidden SDK retry does. |
| Usage/cost | Preserve provider token categories when supplied and label currency as an estimate. Missing or internally inconsistent provider usage fails fidelity; zero cost is not a pass criterion. |
| Correctness | In A, the unchanged registered post-gate and independent review pass on the produced diff. |

Stop immediately on a missing tool result, uncancellable child, hidden mutation
or network use, weakened containment, SDK-owned retry, a terminal state that
cannot map one-to-one to an existing ActionQ settlement, an SDK/session field proposed for
the portable schema, or an implementation larger than one thin adapter plus
packaging.

## Decision and removal cost

The current seam is intentionally less expressive but already released,
portable, independently verified, and cheap to remove or replace: each harness
is a subprocess adapter behind one ActionQ interface. Embedding a native SDK now
would add provider packaging, event normalization, version coupling, and a
second cancellation mechanism before a fair corpus exists.

Accordingly:

- **retain-existing-adapters** now;
- do not alter AgentOps schemas, ActionQ lifecycle, or Vuoro composition;
- permit one Claude TypeScript SDK assessment only after the corpus gate passes;
- choose `narrow-native` later only if all stop conditions remain false and the
  SDK materially improves tool evidence or cancellation observability;
- otherwise `abandon` the challenger by deleting its disposable adapter and
  reverting its dependency and lockfile entries, with no migration or persisted
  portable data to unwind.
