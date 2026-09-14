# Harness evidence redaction and retention policy

**Status:** Proposed — pending operator acceptance (2026-09-14); backend Langfuse is operator-selected.

This policy governs everything the native-harness telemetry path is allowed to
emit and how long any of it may live. It exists because
[`docs/ecosystem.md`](../ecosystem.md) (~36, ~96–100) already names native
harness telemetry and raw evidence as **non-authoritative** and requires "an
explicit redaction and retention policy" before that path carries any weight;
this document is that policy. Nothing here grants the telemetry path
authority it did not have — it only bounds what it may collect and for how
long.

## Scope & non-authority

This policy covers attributes and payloads emitted by native-harness
adapters (Claude Code, Codex, and any other selected first-party
harness/runtime) onto the OpenTelemetry pipeline and the operator-selected
backend (Langfuse, selected 2026-09-14; Phoenix/object storage remains a
documented alternative in `docs/ecosystem.md` ~36 but is not the accepted
path). It does not cover Sprintctl, ActionQ, auditctl, or kctl domain state —
those remain their own authorities per `docs/ecosystem.md`.

Everything this policy governs is **non-authoritative observation**, per
[`docs/plans/agentops/volatile-context-native-runtime-integration-mapping-2026-08-20.md`](../plans/agentops/volatile-context-native-runtime-integration-mapping-2026-08-20.md)
(~39–40): native hooks are projection/feedback **adapters**, never execution
launchers, authorities, or a substitute for a domain's own ledger. No
metric, log event, span, or transcript defined here may gate a mutation,
claim, reservation, or acceptance decision. Nothing in this pipeline may be
cited as proof of Sprintctl/ActionQ state; it may only be cited as harness
telemetry about a session that separately correlates (by ID or digest) with
that state.

## Signal classes

| Class | Carries | Sink |
|---|---|---|
| Metrics | Numeric/enum labels only — see attribute allowlist below | OpenTelemetry → Prometheus (existing path) |
| Log events | Identifiers and result classes only, no raw content | Existing deployment logging/Loki path |
| Spans | Trace/span IDs, timing, result class — same allowlist as metrics | OpenTelemetry → Langfuse (operator-selected 2026-09-14) |
| Rate-limit gauges | Window, used-percent, reset time | OpenTelemetry → Prometheus |
| Raw transcripts | Opt-in evidence artifact, referenced by digest/URI, never inline in a metric/log/span | Host-local under `retention_days`, referenced from Langfuse/Loki by digest only |

This mirrors the mapping document's per-row acceptance criteria: metrics are
"provider ID, revision, bytes, latency, result class, runtime and assurance
labels; no raw projected content" with a "schema check plus redaction test"
(~37); structured logs carry "identifiers and result classes only" while
"transcripts and raw projections are opt-in evidence with separate
retention" (~38); raw evidence stays "non-authoritative, redacted,
retention-scoped, and referenced by digest/URI" with a "retention/redaction
decision plus digest retrieval test before enablement" as the gate (~41).
[`docs/plans/agentops/session-mechanization-plan.md`](../plans/agentops/session-mechanization-plan.md)
(~57–64) states the same privacy contract independently for session
capsules: "Raw prompts and transcripts are opt-in private artifacts with
explicit retention. A prompt digest is correlation evidence — enough to tie
sessions together, not enough semantic evidence for reconciliation on its
own."

## Attribute allowlist

[`templates/dispatch/schemas/harness-evidence-attributes.schema.json`](../../templates/dispatch/schemas/harness-evidence-attributes.schema.json)
is the machine source of truth. It is an `additionalProperties: false` JSON
Schema (draft 2020-12): any key an exporter attempts to attach that is not
explicitly listed there is a schema violation, not a permissive pass-through.
The allowlisted keys, summarized:

- **Correlation:** `session_id`, `agent_id`, `subagent_id`, `trace_id`,
  `span_id` — opaque identifiers only, never content.
- **Provenance:** `runtime`, `harness`, `model`, `environment`.
- **Volume/cost:** `input_tokens`, `output_tokens`, `context_tokens`,
  `cost_usd_list`.
- **Timing/outcome:** `durations` (wall/queue/tool seconds), `result_class`,
  `terminal_reason` (the same seven-code vocabulary auditctl's
  `TERMINAL_REASON_CODES` already enforces: `completed`, `process-exit`,
  `start-failed`, `cancelled`, `timeout`, `usage-limit`, `crash-inferred`).
- **Rate limits:** `rate_limit.window`, `rate_limit.used_percent`,
  `rate_limit.resets_at`.
- **Evidence references only:** `transcript_sha256`, `evidence_uri`.

Every non-reference string field (`session_id`, `agent_id`, `runtime`,
`harness`, `model`, `environment`, `rate_limit.window`) is constrained to an
identifier pattern with no `/` and no whitespace, so neither a filesystem
path nor a header-shaped secret ("Authorization: Bearer ...") can be carried
through a field that was never meant to hold one.

## Forbidden content

The following must never appear in any metric label, log field, span
attribute, or gauge value emitted onto this pipeline, regardless of key
name:

- Prompt or completion text, in whole or excerpted.
- Tool call arguments or tool outputs.
- File contents of any kind.
- Environment variables.
- Credentials, tokens, API keys, or `Authorization`/cookie header values.
- Absolute host paths used as bind mounts, working directories, or any other
  binding — per the mapping document's write-path inventory (~36): "Treat
  absolute worktree paths as host-local observations, never durable bindings
  or handoff references."

**One narrow exception:** a transcript's host path is allowed to appear, but
only as an evidence reference (`evidence_uri`, e.g. a `file://` or `s3://`
URI) and only when paired with that same transcript's `transcript_sha256`.
The schema enforces this pairing directly: `evidence_uri` present without
`transcript_sha256` is a schema violation. A bare path with no digest is
never acceptable — it is not a reference, it is unredacted host detail with
no integrity binding.

## Digest/URI rule

Any raw evidence (a transcript, a large tool output someone chose to keep)
is never embedded inline in telemetry. It is written once to its retention
sink, hashed (`sha256`), and only the digest and a locator (`evidence_uri`)
travel through metrics/logs/spans. Digest-first referencing is what makes
"non-authoritative" enforceable rather than aspirational: a consumer of the
telemetry stream can prove it is looking at the artifact the session
actually produced (by re-hashing on retrieval) without the telemetry stream
itself ever having carried the content. This is the same shape as
`session-capsule.schema.json`'s `privacy.raw_transcript_ref` /
`raw_transcript_captured` fields (~200–209) and `immutableRef`-typed
references elsewhere in that schema — evidence is addressed, not embedded.

## Per-sink retention (proposed)

| Sink | Data | Proposed retention | Mechanism |
|---|---|---|---|
| Langfuse (traces/spans) | Allowlisted attributes only | 30 days | ClickHouse TTL on the traces/observations tables, paired with an S3 lifecycle rule on the `langfuse/` prefix for any associated blob storage |
| Loki | Structured log events (identifiers, result classes) | 720h (existing deployment retention, unchanged) | Existing Loki retention config |
| Prometheus | Metrics, rate-limit gauges | 15d (existing deployment retention, unchanged) | Existing Prometheus retention config |
| Host-local transcript store | Raw transcripts (opt-in) | `retention_days` per session, default proposal 30 days | Host-local cleanup job keyed off `session-capsule.schema.json`'s `privacy.retention_days` (~209, nullable — `null` means "no automatic expiry," which requires explicit operator opt-in per session, not a default) |

Loki and Prometheus values are the deployment's existing configured
retention and are listed for completeness, not proposed as new. Langfuse and
host-local transcript retention are new and are exactly the "explicit
redaction and retention policy" `docs/ecosystem.md` requires before this
path may be treated as anything more than deployment-selected instrumentation.

## Fail-open posture

Exporters on this path must never block or change the exit behavior of a
hook, wrapper, or harness invocation, and must never extend it unboundedly.
This mirrors the plan's existing distinction between recording and authority
paths: "Hooks and wrappers instrumenting manual work fail **open**: a broken
recorder must never block a human from working. Claim acquisition and
dispatcher verification gates fail **closed**"
([`session-mechanization-plan.md`](../plans/agentops/session-mechanization-plan.md)
~57–64). Concretely:

- Every exporter call runs with a short, bounded timeout; a timeout or
  export failure is logged locally (if anything) and discarded — it never
  raises through to the caller.
- No exporter call may run synchronously in the critical path of a hook's
  exit code. If asynchronous/batched export is unavailable, the call is
  best-effort and its failure is swallowed.
- A misconfigured backend (auth failure, unreachable Langfuse, full disk)
  degrades to "no telemetry for this session," never to "the session
  cannot proceed."

## Deletion procedure

- **Langfuse:** delete by trace ID or session ID via the Langfuse
  API/console, or let ClickHouse TTL expire the row at 30 days. An operator
  deletion request within the retention window is honored via the API,
  scoped to the identifying `session_id`/`trace_id` attributes.
- **Loki:** follows the existing deployment's log-deletion process (out of
  scope of this document — no new mechanism introduced).
- **Prometheus:** metrics are aggregate/numeric only; there is no per-session
  raw content to delete, only the numeric series, which ages out at 15d.
- **Host-local transcripts:** delete the file at the path named by the
  session's `evidence_uri` and drop the corresponding
  `raw_transcript_ref`/`transcript_sha256` correlation fields from any
  session record that still lists them, either on `retention_days` expiry
  or on an explicit operator deletion request.

## Enablement gate checklist

Mirrors [`volatile-context-native-runtime-integration-mapping-2026-08-20.md`](../plans/agentops/volatile-context-native-runtime-integration-mapping-2026-08-20.md)
~41 ("Retention/redaction decision plus digest retrieval test before
enablement"). None of the following may be skipped before this pipeline is
turned on for any session:

- [ ] This policy is operator-accepted (see Open items below).
- [ ] `harness-evidence-attributes.json` schema check passes in CI
      (`python -m pytest templates/dispatch/tests/test_harness_evidence_attributes.py`).
- [ ] A redaction test demonstrates that prompt/completion text, tool
      arguments/outputs, and credential-shaped values are rejected by the
      allowlist (the negative fixtures in the test file above).
- [ ] A digest retrieval test demonstrates that a transcript referenced by
      `evidence_uri` + `transcript_sha256` can be fetched and its hash
      re-verified.
- [ ] Per-sink retention is configured and observable (Langfuse ClickHouse
      TTL + S3 lifecycle rule exist and are queryable; host-local cleanup job
      is scheduled).
- [ ] Fail-open behavior is demonstrated: killing/blackholing the exporter
      backend does not change a hook's exit code or add unbounded latency.

## Open items needing operator acceptance

- Confirm 30 days as the Langfuse trace retention and default
  `retention_days` for host-local transcripts (this document proposes 30d;
  no operator value is recorded yet).
- Confirm Langfuse (over Phoenix/object storage) as the accepted backend for
  production use, not just the currently selected one — `docs/ecosystem.md`
  (~96–100) records the selection but this document treats acceptance of
  *this redaction/retention policy* as the separate, still-open gate.
- Decide whether host-local transcript storage needs an upper disk-usage
  bound in addition to a time-based `retention_days`, since `retention_days:
  null` is schema-legal and defers expiry indefinitely per session.
- Decide the actual deletion SLA (how promptly an operator delete request
  must be honored) — this document specifies the mechanism, not a time
  bound.
