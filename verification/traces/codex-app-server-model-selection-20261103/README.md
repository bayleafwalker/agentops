# Codex app-server model selection observation

This trace qualifies the local Codex app-server `thread/start` response as a
source for the model/provider selected in a thread configuration. It does not
qualify the provider that would serve an inference request.

## Reproduce

On a host with `codex-cli 0.166.0` on `PATH`, run:

```sh
python3 verification/traces/codex-app-server-model-selection-20261103/probe.py \
  > verification/traces/codex-app-server-model-selection-20261103/result.json
```

The probe generates experimental TypeScript protocol bindings in a temporary
directory, recording SHA-256 digests for the start/resume request and response
types. It then launches the stdio app-server with a temporary workspace and a
temporary `CODEX_HOME` whose only config is `model = "gpt-6.1-terra"`. The
server child environment contains only `PATH`, temporary `HOME`/`CODEX_HOME`,
and `LANG`; it does not inherit ambient credentials or provider variables.
Standard error and unrecognized protocol messages are discarded. The output
contains only selected response fields and JSON-RPC error codes; it records no
thread ids, paths, raw messages, prompts, or transcript content.

The probe sends `initialize`, then three ephemeral `thread/start` requests:

1. no model/provider fields, to observe the configured default;
2. explicit `gpt-6-luna` / `openai`;
3. the deliberately nonexistent model
   `codex-routing-probe-model-does-not-exist-20261103`, with provider fallback
   disabled, as a negative control.

It also attempts `thread/resume` on the explicit ephemeral thread with model
and provider omitted. All thread requests use a read-only sandbox and
`approvalPolicy: never`. No `turn/start` request is issued. Thus this probe
makes no inference or provider call.

## Observation

The configured-default response reports `gpt-6.1-terra` / `openai`; the
explicit response reports `gpt-6-luna` / `openai`. Both return `serviceTier:
null` and an idle thread. The unsupported-model negative control also succeeds
and returns the exact nonexistent model string. That is evidence that
`thread/start` does not reject this model identifier at thread creation; it is
not evidence that the model exists, is entitled, or can serve a request.

The ephemeral resume attempt returns JSON-RPC error code `-32600`. The error
message is intentionally not retained. Resume request/response schema fields
are present in the generated protocol bindings, but runtime resume behavior
for this ephemeral thread is not qualified by this observation.

## Assurance and limits

The response fields are app-server-reported selected thread configuration.
They can support requested-versus-reported configuration observation at
thread creation. The explicit and unsupported identifiers are accepted as
thread configuration strings, so a returned value is not evidence of model
catalog validation, entitlement, backend identity, provider execution, token
usage, subscription consumption, or billing. `modelProvider: "openai"` is a
local provider label only. Billing remains unknown.

This is one local observation of CLI 0.166.0 with a synthetic isolated
configuration. It makes no claim about other versions, hosts, defaults, or
live provider behavior.
