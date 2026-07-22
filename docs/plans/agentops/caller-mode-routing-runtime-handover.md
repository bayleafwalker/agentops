# Caller-Mode Routing Runtime Handover

Date: 2026-07-22

This handover is for the sessions changing `/projects/dev/actionq` and
`/projects/dev/actionq-dispatcher`. The canonical policy and portable manifest contract are now in
`agentops`; no runtime files in either owning repository were changed as part of this work.

## Accepted contract

- `routing.default_harness = "caller"` means inherit the trusted calling-session harness.
- An explicit action harness wins. A concrete action-class harness override is next, followed by a
  concrete project default, caller inheritance, and finally a single configured-harness fallback.
- `caller` is never passed to a harness registry as an executable adapter name.
- Caller identity comes from trusted runtime/session metadata. A prompt field or worker output is
  not trusted routing identity.
- Once the harness is resolved, use
  `templates/dispatch/model-routing.json:caller_harness_providers` to choose the provider branch of
  the logical alias.
- Same-provider model fallback is data in that branch. Cross-provider fallback must be explicitly
  configured because it consumes a different subscription.
- Record the requested selector, trusted caller harness, resolved harness/provider/model,
  transport, routing source, and fallback reason in dispatch/session events.

## Spark behavior

The Codex branch of `fast-build` now prefers `gpt-5.3-codex-spark`, with
`gpt-5.6-luna` as its same-provider fallback. Spark is usable through authenticated Codex surfaces,
not as a general API-key model. Runtime resolution must check the branch's `transport`/`surfaces`
before launch. A confirmed Spark limit or unavailable-preview response may re-dispatch from the
existing handoff using Luna; it must not silently switch to Claude.

Build prompts must continue to name required tests explicitly. Spark intentionally defaults to
targeted edits and may not run tests unless asked.

## `actionq` gaps

- The minimum daemon's `ActionConfig` still models only `fake`, `fake-commit`, and deterministic
  `command` runners. `_start_child` does not invoke the existing harness registry/adapters.
- The repository already has a current Codex command builder under `actionq/harnesses/codex.py`;
  wire that abstraction into daemon execution rather than duplicating CLI syntax.
- The daemon config does not yet carry a trusted caller harness, logical model alias, provider
  mapping, transport, resolved model, or routing source.
- Usage-limit classification and durable handoff already recognize Codex output. Extend the
  re-dispatch policy to use an explicitly declared same-provider fallback; preserve the existing
  checkpoint-and-redispatch semantics rather than pretending the process can resume.
- Add contract tests for Claude caller, Codex caller, explicit override, missing caller with
  multiple harnesses, unsupported provider branch, Spark transport incompatibility, Spark-to-Luna
  handoff, and rejection of implicit cross-provider fallback.

## `actionq-dispatcher` gaps

- `routing.py` resolves explicit action, project, then action-kind defaults. It has no `caller`
  selector or trusted origin input, and its project-before-action-class ordering makes a required
  project default mask class-specific concrete overrides. Align it with the accepted precedence.
- The daemon-side harness registry is present, but `harness.py::CodexAdapter` still emits the old
  `codex --approval-mode full-auto --model ... <prompt>` form. Current noninteractive syntax is
  `codex exec --json --sandbox workspace-write -C <worktree> --model <model> -`, with the prompt on
  stdin. Preserve the existing external sandbox/ACL posture when updating it.
- The one-shot `ConfiguredWorker` path in `worker.py` remains Claude-only for `runner = "local"`
  even though daemon-side adapters exist. Either route it through the same adapter registry or
  explicitly deprecate the divergent path.
- Config currently accepts harness/project/action model values but does not resolve logical aliases
  from the canonical policy or evaluate transport constraints. Do not copy model literals into a
  second policy file; load or generate runtime config from the canonical mapping.
- Codex reasoning emission remains deliberately unverified in current policy. Do not infer Claude's
  `--effort` syntax for Codex while doing this routing work.

## Future Kimi mode

The manifest schema now permits a concrete `kimi` harness identifier and the provider map reserves
the `kimi` family. Runtime support remains fail-closed until another change supplies a verified
adapter, authentication/transport contract, concrete model branches, usage-limit signals, and a
disposable smoke result. OpenCode must carry an explicit provider mapping because its harness name
alone does not prove which subscription it will consume.

## Suggested completion evidence

1. Unit tests cover routing precedence, caller inheritance, provider mapping, transport checks, and
   same-provider fallback.
2. Adapter command-shape tests match the installed CLI help.
3. One disposable Claude caller dispatch and one disposable Codex/Spark caller dispatch record the
   complete routing provenance without exposing credentials.
4. A simulated Spark-limit result produces a durable handoff and a Luna re-dispatch, while a
   Claude fallback remains impossible without explicit policy.
