"""Build an OTLP/JSON trace batch: the session as a root span, subagents as
children.

`payload` is shaped like the allowlisted attributes it will become (its keys
mostly line up 1:1 with `schemas/harness-evidence-attributes.schema.json`
properties -- `session_id`, `input_tokens`, `durations`, `terminal_reason`,
...), plus a small set of control keys this module consumes for linking and
strips before anything reaches the allowlist filter:

* `transcript_path` -- the session's own transcript, matched against each
  subagent's `parent_transcript_path` to decide whether it is this session's
  child. `hooks/subagent-exit.sh` records the *parent* session's transcript
  on a SubagentStop event (its own comment: "transcript_path on a
  SubagentStop event is the PARENT session's transcript, not the
  subagent's own"), which is the join key reused here.
* `subagents` -- a list of subagent payload dicts, each shaped the same way
  as the session payload (plus its own `parent_transcript_path`).
* `codex_trace_id` -- present only on a Codex-correlated session; attached
  as this span's `trace_id` so it can be joined against Codex's own native
  trace. This library never builds or sends a span *for* Codex -- Codex
  spans are its own harness's, not re-emitted here.

Every other key that is not in the allowlist schema (a raw prompt, tool
output, `gates`, `rework_rounds`, anything shaped like a credential) is
dropped by `attributes.filter_attributes` and counted in
`dropped_attribute_count` / `dropped_attribute_keys` on the returned batch --
it never reaches an OTLP attribute.
"""
from __future__ import annotations

import hashlib
from typing import Any

from . import attributes
from .otlp import kv_list

_SESSION_CONTROL_KEYS = frozenset({"transcript_path", "subagents", "codex_trace_id"})
_SUBAGENT_CONTROL_KEYS = frozenset({"parent_transcript_path"})


def _hex_id(*parts: str, length: int) -> str:
    """A deterministic, schema-shaped hex id derived from `parts`.

    Deterministic rather than random so the same payload always produces the
    same trace/span ids -- useful for tests and for re-running a dry-run
    without minting a new identity for the same session each time.
    """
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:length]


def _span(
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    name: str,
    filtered_attributes: dict[str, Any],
) -> dict[str, Any]:
    span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": "SPAN_KIND_INTERNAL",
        "attributes": kv_list(filtered_attributes),
    }
    durations = filtered_attributes.get("durations") or {}
    wall_seconds = durations.get("wall_seconds")
    span["startTimeUnixNano"] = "0"
    span["endTimeUnixNano"] = str(int(wall_seconds * 1_000_000_000)) if wall_seconds else "0"
    if parent_span_id:
        span["parentSpanId"] = parent_span_id
    return span


def build_session_span(payload: dict[str, Any]) -> dict[str, Any]:
    """Return an OTLP/JSON resourceSpans batch for one session and its subagents."""
    schema = attributes.load_schema()
    session_transcript = payload.get("transcript_path")

    session_candidate = attributes.candidate_from_payload(payload, _SESSION_CONTROL_KEYS)
    if "trace_id" not in session_candidate and payload.get("codex_trace_id"):
        session_candidate["trace_id"] = payload["codex_trace_id"]
    session_result = attributes.filter_attributes(session_candidate, schema)

    session_id = str(payload.get("session_id") or payload.get("session") or "session")
    trace_id = session_result.attributes.get("trace_id") or _hex_id(session_id, length=32)
    root_span_id = _hex_id(session_id, "root", length=16)
    root_span = _span(trace_id, root_span_id, None, "claude_code.session", session_result.attributes)

    dropped_keys = list(session_result.dropped_keys)
    spans = [root_span]
    for subagent in payload.get("subagents", []) or []:
        sub_candidate = attributes.candidate_from_payload(subagent, _SUBAGENT_CONTROL_KEYS)
        sub_result = attributes.filter_attributes(sub_candidate, schema)
        dropped_keys.extend(sub_result.dropped_keys)

        sub_id = str(
            subagent.get("subagent_id") or subagent.get("agent_id") or f"subagent-{len(spans)}"
        )
        parent_span_id = (
            root_span_id
            if session_transcript is not None and subagent.get("parent_transcript_path") == session_transcript
            else None
        )
        sub_span_id = _hex_id(session_id, sub_id, length=16)
        spans.append(
            _span(trace_id, sub_span_id, parent_span_id, "claude_code.subagent", sub_result.attributes)
        )

    resource_attrs = {
        key: session_result.attributes[key]
        for key in ("runtime", "harness", "environment")
        if key in session_result.attributes
    }

    return {
        "resourceSpans": [
            {
                "resource": {"attributes": kv_list(resource_attrs)},
                "scopeSpans": [
                    {
                        "scope": {"name": "agentops.harness_evidence", "version": "1"},
                        "spans": spans,
                    }
                ],
            }
        ],
        "dropped_attribute_count": len(dropped_keys),
        "dropped_attribute_keys": dropped_keys,
    }
