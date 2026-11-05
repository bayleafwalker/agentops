# Execution placement responsibility map

Status: source-reviewed design aid, 5 November 2026. This records documented
provider boundaries for **Claude Managed Agents** and the **OpenAI Agents API
and Python Agents SDK**. It is not account, runtime, security or paid-workflow
qualification. The machine-readable source is
[`execution-placement-matrix.json`](execution-placement-matrix.json); validate
it with `python scripts/validate_execution_placement.py`.

## Separate the three locations

| Placement | Model and harness | Tool execution | Environment operator | Tool/data boundary | Stop and usage boundary |
|---|---|---|---|---|---|
| Claude Managed Agents, cloud | Anthropic operates the Claude model and agent loop. | Anthropic-managed isolated Linux sandbox per session. | Anthropic operates the sandbox; the application configures network rules and packages. | Bash/file, web search/fetch and configured MCP. Conversation, tool results, sandbox files/state, skills and memory are available to Managed Agents. | Session interrupt does not end open workflow runs. Usage includes tracked list cost; budget pauses model requests. Neither is target-effect cancellation. |
| Claude Managed Agents, self-hosted | Claude and the agent loop stay on Anthropic's side. | The operator's worker runs bash/file calls; web search/fetch and MCP connections remain service-side. | Application/operator hardens workers, network limits, isolation and environment-key handling. | Worker filesystem/processes stay local; conversation, tool results, skills and memory reach Anthropic. | Session interrupt does not end workflow runs or prove worker shutdown. Provider list-cost usage excludes local per-item cost allocation. |
| OpenAI Agents API, OpenAI-hosted | OpenAI operates the Codex harness, model/tool loop, sessions, compaction and recovery. | Shell/code/files in an OpenAI sandbox; app function tools execute on the application server. | OpenAI manages the sandbox; the application selects tools, files, packages and network policy. | Session inputs/events and tool results go through the hosted harness; exact retention and tool data flows depend on configuration. | A cancel-turn event is available; the sandbox can outlive a session. Model, tool and container charges are separate. |
| OpenAI Agents API, self-hosted | OpenAI operates the harness and durable session. | Application-managed executor runs commands in the selected environment. | Application/operator manages executor setup, connection, lifecycle and private-network access. | Tool results and agent context return to OpenAI; keeping the filesystem local does not keep returned content local. | Cancel-turn does not replace executor cleanup or effect reconciliation. Self-hosted compute cost belongs to the operator. |
| OpenAI Agents SDK, local function tools | Model location follows the configured provider; the SDK does not make a local session a local model. | Local function tools run in the application process. Hosted OpenAI tools run on OpenAI; other tools follow their configured runtime. | Application owns its process and local tools; hosted tools retain their own boundary. | Model inputs/outputs reach the configured provider. Tool I/O may be included in traces; tracing sensitivity and each tool's egress need separate review. | Interrupt/resume state is separate from cancellation of an in-flight local tool. Per-run token usage is reported; provider pricing and local compute need separate records. |

The current official sources document identifiers for a provider's own
resources. Anthropic exposes session, event, workflow-run and thread IDs. The
Agents API exposes agent, session, environment, event, turn and tool-call IDs.
In the Agents SDK, a session is client-managed history, while `conversation_id`
and `previous_response_id` are Responses API continuation. Trace and group IDs
are for observation. These identities must be joined to the estate's own work
item, attempt, artifact revision/digest, current owner revision, acceptance
reference and (when applicable) effect receipt. A session/thread/trace ID does
not become a work ID or evidence of acceptance.

## Preserve owner semantics under interruption

[W41-R5](../2026-10-11-agent-systems-w39-w41.md) calls for these cases to use
synthetic event fixtures. The matrix records their required result and marks
each `not-run` until the owner-side implementation produces evidence:

| Fixture | Required owner result |
|---|---|
| Duplicate event after a lost acknowledgement | Same event and existing owner idempotency key reconcile to one durable observation/effect. A distinct event is not deduplicated only because its payload matches. |
| Missing child evidence | Keep the child in the expected coverage denominator; outcome and acceptance remain unknown until owner evidence closes the gap. |
| Failed child with parent summary | Preserve the child's failure; parent prose or a terminal provider status cannot override owner acceptance criteria. |
| Late result after replacement | Bind the result to its originating attempt and artifact revision; retain it as evidence without settling or overwriting current owner state. |

The source map does not add another work ledger, provider adapter or effect
writer. Anthropic documents that a repeated custom-tool result for the same call
has no further effect at the session endpoint; this does not establish
exactly-once effects in a self-hosted worker or target system. The reviewed
OpenAI material does not promise exactly-once executor delivery. In both cases,
an ambiguous target effect must be reconciled by its owner before retry.
The self-hosted executor cleanup requirement is an operational consequence of
the application owning that executor's lifecycle; it is not a claim that the
provider's cancel event can never stop a running command.

## Qualification boundary

`validate_execution_placement.py` checks that every placement distinguishes
model location, tool location, environment custody, context egress, tool
surface, provider IDs, retry/completion limits, cancellation, usage/cost and
effect authority; it also checks official source references and the four
required scenario definitions. It reports
`source-mapped-not-qualified` and `scenarios_run: 0` even when the document is
valid. It cannot verify account settings, credential scope, runtime identity,
event delivery or owner-side behavior.

Before paid onboarding, the relevant operator still needs to verify the actual
agent/model, environment, network, data controls, enabled tools, credentials,
usage/cost capture, interruption handling and evidence coverage. W41-R5's four
fixtures must pass in the owner implementation; their outcomes belong to the
owner's evidence record. No managed session was started for this source review.

## Reviewed primary sources

- Anthropic: [Managed Agents overview](https://platform.claude.com/docs/en/managed-agents/overview), [choosing an environment](https://platform.claude.com/docs/en/managed-agents/choosing-an-environment), [workflow runs](https://platform.claude.com/docs/en/managed-agents/workflow-runs), [session event stream](https://platform.claude.com/docs/en/managed-agents/events-and-streaming), [session threads](https://platform.claude.com/docs/en/managed-agents/session-threads), [session budgets](https://platform.claude.com/docs/en/managed-agents/budgets) and [secure deployment](https://platform.claude.com/docs/en/managed-agents/secure-deployment).
- OpenAI: [Agents API overview](https://developers.openai.com/api/docs/guides/agents-api/overview), [architecture](https://developers.openai.com/api/docs/guides/agents-api/architecture), [sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions), [session events](https://developers.openai.com/api/docs/guides/agents-api/sessions/events), [hosted environments](https://developers.openai.com/api/docs/guides/agents-api/environments/openai-hosted), [self-hosted environments](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted), [sandbox lifecycle](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle), and the Python SDK's [tools](https://openai.github.io/openai-agents-python/tools/), [models](https://openai.github.io/openai-agents-python/models/), [sessions](https://openai.github.io/openai-agents-python/sessions/), [running agents](https://openai.github.io/openai-agents-python/running_agents/) and [usage](https://openai.github.io/openai-agents-python/usage/) references.
- Estate boundary: [TS-16](../2026-09-17-target-state.md) and [W41-R5](../2026-10-11-agent-systems-w39-w41.md).
