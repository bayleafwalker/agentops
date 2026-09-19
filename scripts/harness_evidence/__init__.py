"""Harness-evidence telemetry library (agentops#2443).

Builds OTLP/JSON spans and rate-limit gauges from the Stop cost-snapshot
inputs `hooks/log-session-cost.sh` already assembles (usage, context,
terminal_reason, rework_rounds, gates -- record shape at lines 119-122 of
that hook) and from the headroom file format (`.claude-headroom.json`,
#2372). This package builds the library only: nothing here is called from a
hook, and nothing here edits `hooks/log-session-cost.sh` or changes what it
writes to auditctl -- that wiring is the successor item.

Every attribute this library emits is checked against
`schemas/harness-evidence-attributes.schema.json`
(`additionalProperties: false`), the machine source of truth for
`docs/architecture/harness-evidence-policy.md`. A key the schema does not
list -- prompt text, tool output, a credential-shaped value, an internal
control field like `gates` or `rework_rounds` -- is dropped and counted,
never sent. `scripts/tests/test_harness_evidence_attributes.py` audits the
schema itself; this package only consumes it.

Public surface:

* `attributes.load_schema()`, `attributes.filter_attributes()` -- the
  allowlist enforcement both `spans` and `metrics` are built on.
* `spans.build_session_span(payload)` -- OTLP/JSON span dict: the session as
  a root span, subagents as child spans keyed by the parent transcript
  `hooks/subagent-exit.sh` records.
* `metrics.build_rate_limit_gauges(payload)` -- OTLP/JSON metric points for
  the 5h/7d utilisation windows in the headroom file format.
* `export.export(batch)` -- posts a batch built from the two functions
  above to `$OTEL_EXPORTER_OTLP_ENDPOINT`; a no-op (no I/O at all) when that
  variable is unset.

Codex sessions are correlated, never re-emitted: a Codex trace id present on
the payload is attached to the span this library builds so it can be joined
against Codex's own native trace, but this library never constructs or
sends a span on Codex's behalf.
"""
from __future__ import annotations

from . import attributes, export, metrics, spans
from .export import export as export_batch
from .metrics import build_rate_limit_gauges
from .spans import build_session_span

__all__ = [
    "attributes",
    "export",
    "metrics",
    "spans",
    "build_session_span",
    "build_rate_limit_gauges",
    "export_batch",
]
