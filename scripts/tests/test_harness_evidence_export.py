"""Tests for `scripts/harness_evidence`: allowlist enforcement, span/gauge shape,
and the network posture of `export()`.

`scripts/tests/test_harness_evidence_attributes.py` audits
`schemas/harness-evidence-attributes.schema.json` itself (the allowlist)
against positive/negative fixtures -- those are the WP2 (#2391) redaction
fixtures this item must not break. This file audits the *library* built on
top of that schema: `build_session_span`, `build_rate_limit_gauges` and
`export`, using the schema file itself (not a copied literal key list) as
the source of truth for what is allowed to appear.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "harness_evidence"

# `scripts` has no `__init__.py`; it is an implicit namespace package. Putting the
# repo root on `sys.path` (rather than `scripts/`, the pattern the sibling tests in
# this directory use for single-file modules) is what makes `scripts.harness_evidence`
# importable as the dotted package the acceptance criteria's own invocation
# (`python -m scripts.harness_evidence --dry-run ...`) uses.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.harness_evidence import attributes, export as export_module  # noqa: E402
from scripts.harness_evidence.metrics import build_rate_limit_gauges  # noqa: E402
from scripts.harness_evidence.spans import build_session_span  # noqa: E402

SCHEMA = attributes.load_schema()
ALLOWED_TOP_LEVEL = attributes.allowed_top_level_keys(SCHEMA)

# The negative fixture's forbidden keys, verified absent from every emitted attribute
# map by name -- not merely "not the whole allowlist", so a bug that let an unrelated
# unknown key slip through as if it were harmless would still be caught by the same
# assertion the schema's own additionalProperties: false is meant to guarantee.
FORBIDDEN_KEYS = {"prompt", "tool_output", "authorization", "raw_tail", "raw_header", "raw_quota_message"}


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _span_attribute_keys(span: dict[str, Any]) -> set[str]:
    return {kv["key"] for kv in span["attributes"]}


def _all_spans(batch: dict[str, Any]) -> list[dict[str, Any]]:
    spans = []
    for resource_span in batch["resourceSpans"]:
        for scope_span in resource_span["scopeSpans"]:
            spans.extend(scope_span["spans"])
    return spans


def _all_gauge_points(batch: dict[str, Any]) -> list[dict[str, Any]]:
    points = []
    for resource_metric in batch["resourceMetrics"]:
        for scope_metric in resource_metric["scopeMetrics"]:
            for metric in scope_metric["metrics"]:
                points.extend(metric["gauge"]["dataPoints"])
    return points


class AllowlistIsReadFromTheSchemaFile(unittest.TestCase):
    """`attributes` must read the schema file itself, never a copy of its keys."""

    def test_allowed_top_level_keys_match_schema_properties_on_disk(self) -> None:
        on_disk = json.loads(attributes.SCHEMA_PATH.read_text())
        self.assertEqual(ALLOWED_TOP_LEVEL, frozenset(on_disk["properties"].keys()))

    def test_filter_attributes_reflects_a_schema_reloaded_at_call_time(self) -> None:
        # A schema with one fewer property than the real one must change what
        # filter_attributes keeps -- proof the function consults its `schema`
        # argument rather than a module-level snapshot taken at import time.
        trimmed = json.loads(attributes.SCHEMA_PATH.read_text())
        del trimmed["properties"]["model"]
        result = attributes.filter_attributes({"schema_version": "x", "model": "claude-sonnet-5"}, trimmed)
        self.assertNotIn("model", result.attributes)
        self.assertIn("model", result.dropped_keys)


class FilterAttributesDropsAndCounts(unittest.TestCase):
    def test_unknown_top_level_key_is_dropped_and_counted(self) -> None:
        result = attributes.filter_attributes(
            {"schema_version": "harness-evidence-attributes/v1", "favorite_color": "blue"}
        )
        self.assertNotIn("favorite_color", result.attributes)
        self.assertEqual(result.dropped_keys, ["favorite_color"])
        self.assertEqual(result.dropped_count, 1)

    def test_unknown_nested_key_under_durations_is_dropped_without_losing_the_field(self) -> None:
        result = attributes.filter_attributes(
            {
                "schema_version": "harness-evidence-attributes/v1",
                "durations": {"wall_seconds": 1.0, "raw_header": "Authorization: Bearer x"},
            }
        )
        self.assertEqual(result.attributes["durations"], {"wall_seconds": 1.0})
        self.assertIn("durations.raw_header", result.dropped_keys)

    def test_fully_allowlisted_map_drops_nothing(self) -> None:
        result = attributes.filter_attributes(
            {"schema_version": "harness-evidence-attributes/v1", "session_id": "sess-1", "input_tokens": 10}
        )
        self.assertEqual(result.dropped_count, 0)
        self.assertEqual(result.attributes["session_id"], "sess-1")


class InteractiveSessionFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _load_fixture("session.json")
        self.batch = build_session_span(self.payload)

    def test_span_attribute_keys_are_a_subset_of_the_allowlist(self) -> None:
        for span in _all_spans(self.batch):
            self.assertTrue(_span_attribute_keys(span) <= ALLOWED_TOP_LEVEL, _span_attribute_keys(span))

    def test_root_span_carries_the_session_identity(self) -> None:
        (root,) = _all_spans(self.batch)
        keys = _span_attribute_keys(root)
        self.assertIn("session_id", keys)
        self.assertIn("terminal_reason", keys)
        self.assertNotIn("parentSpanId", root)

    def test_gates_and_rework_rounds_are_dropped_and_counted(self) -> None:
        self.assertIn("gates", self.batch["dropped_attribute_keys"])
        self.assertIn("rework_rounds", self.batch["dropped_attribute_keys"])
        self.assertGreaterEqual(self.batch["dropped_attribute_count"], 2)

    def test_rate_limit_gauges_cover_5h_and_7d(self) -> None:
        gauges = build_rate_limit_gauges(self.payload)
        points = _all_gauge_points(gauges)
        rendered_windows = set()
        for point in points:
            for kv in point["attributes"]:
                if kv["key"] == "rate_limit":
                    sub = {inner["key"]: inner for inner in kv["value"]["kvlistValue"]["values"]}
                    rendered_windows.add(sub["window"]["value"]["stringValue"])
        self.assertEqual(rendered_windows, {"5h", "7d"})
        for point in points:
            for kv in point["attributes"]:
                self.assertIn(kv["key"], ALLOWED_TOP_LEVEL)

    def test_dry_run_cli_prints_the_same_batch_shape(self) -> None:
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "scripts.harness_evidence", "--dry-run", str(FIXTURES / "session.json")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        printed = json.loads(result.stdout)
        self.assertIn("spans", printed)
        self.assertIn("metrics", printed)


class SubagentSessionFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _load_fixture("session_with_subagent.json")
        self.batch = build_session_span(self.payload)
        self.spans = _all_spans(self.batch)

    def test_span_attribute_keys_are_a_subset_of_the_allowlist(self) -> None:
        for span in self.spans:
            self.assertTrue(_span_attribute_keys(span) <= ALLOWED_TOP_LEVEL, _span_attribute_keys(span))

    def test_three_spans_are_built_root_plus_two_subagents(self) -> None:
        self.assertEqual(len(self.spans), 3)

    def test_subagent_matching_the_parent_transcript_is_a_child_of_the_root(self) -> None:
        root, matching_child, other_child = self.spans
        self.assertNotIn("parentSpanId", root)
        self.assertEqual(matching_child.get("parentSpanId"), root["spanId"])
        # The second subagent fixture's parent_transcript_path points at an unrelated
        # session on purpose: it must NOT be linked under this session's root.
        self.assertNotEqual(other_child.get("parentSpanId"), root["spanId"])

    def test_all_spans_in_one_session_share_a_trace_id(self) -> None:
        trace_ids = {span["traceId"] for span in self.spans}
        self.assertEqual(len(trace_ids), 1)


class CodexSessionFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _load_fixture("session_codex.json")
        self.batch = build_session_span(self.payload)

    def test_span_attribute_keys_are_a_subset_of_the_allowlist(self) -> None:
        for span in _all_spans(self.batch):
            self.assertTrue(_span_attribute_keys(span) <= ALLOWED_TOP_LEVEL, _span_attribute_keys(span))

    def test_codex_trace_id_correlates_rather_than_minting_a_new_one(self) -> None:
        (root,) = _all_spans(self.batch)
        self.assertEqual(root["traceId"], self.payload["codex_trace_id"])

    def test_exactly_one_span_is_built_codex_spans_are_never_re_emitted(self) -> None:
        # This library only ever builds a span for the Claude-Code-shaped session
        # payload it was given; it has no notion of Codex's own span tree to walk,
        # so "never re-emit Codex spans" holds simply by construction: one payload
        # in, one root span out (plus its own subagents, of which this fixture has
        # none).
        self.assertEqual(len(_all_spans(self.batch)), 1)


class NegativeFixtureIsFullyRedacted(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _load_fixture("session_negative.json")
        self.span_batch = build_session_span(self.payload)
        self.gauge_batch = build_rate_limit_gauges(self.payload)

    def test_zero_forbidden_keys_reach_any_span_attribute(self) -> None:
        for span in _all_spans(self.span_batch):
            self.assertTrue(_span_attribute_keys(span).isdisjoint(FORBIDDEN_KEYS), span["attributes"])

    def test_zero_forbidden_keys_reach_any_gauge_attribute(self) -> None:
        for point in _all_gauge_points(self.gauge_batch):
            keys = {kv["key"] for kv in point["attributes"]}
            self.assertTrue(keys.isdisjoint(FORBIDDEN_KEYS), point["attributes"])

    def test_dropped_count_is_non_zero(self) -> None:
        self.assertGreater(self.span_batch["dropped_attribute_count"], 0)
        self.assertGreater(self.gauge_batch["dropped_attribute_count"], 0)

    def test_every_forbidden_key_is_named_in_dropped_keys(self) -> None:
        dropped = set(self.span_batch["dropped_attribute_keys"])
        self.assertIn("prompt", dropped)
        self.assertIn("tool_output", dropped)
        self.assertIn("authorization", dropped)
        self.assertIn("durations.raw_header", dropped)
        # The subagent's own forbidden key is dropped independently of the
        # session's, proving the filter runs per-span, not once at the top.
        self.assertIn("raw_tail", dropped)

    def test_credential_shaped_value_never_appears_verbatim_anywhere_in_the_batch(self) -> None:
        rendered = json.dumps(self.span_batch)
        self.assertNotIn("sk-live-abcdef0123456789", rendered)
        self.assertNotIn("/etc/shadow", rendered)


class ExportPerformsNoIOWhenEndpointIsUnset(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[Any] = []

        def _fake_urlopen(request, timeout=None):  # noqa: ARG001 - matches urlopen's signature
            self.calls.append(request)
            raise AssertionError("urlopen must not be called when the endpoint is unset")

        self._orig_urlopen = export_module.urllib.request.urlopen
        export_module.urllib.request.urlopen = _fake_urlopen

    def tearDown(self) -> None:
        export_module.urllib.request.urlopen = self._orig_urlopen

    def test_export_is_a_no_op_with_no_endpoint_env_var(self) -> None:
        import os

        env_backup = os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        try:
            batch = {
                "spans": [build_session_span(_load_fixture("session.json"))],
                "metrics": [build_rate_limit_gauges(_load_fixture("session.json"))],
            }
            export_module.export(batch)
        finally:
            if env_backup is not None:
                os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = env_backup
        self.assertEqual(self.calls, [])

    def test_export_is_a_no_op_with_endpoint_set_to_empty_string(self) -> None:
        import os

        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
        try:
            export_module.export({"spans": [build_session_span(_load_fixture("session.json"))]})
        finally:
            del os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]
        self.assertEqual(self.calls, [])


class ExportPostsWhenEndpointIsSet(unittest.TestCase):
    def test_export_posts_spans_and_metrics_to_the_right_paths_with_headers(self) -> None:
        import os

        requests_seen = []

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def _fake_urlopen(request, timeout=None):
            requests_seen.append(request)
            return _FakeResponse()

        orig_urlopen = export_module.urllib.request.urlopen
        export_module.urllib.request.urlopen = _fake_urlopen
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://collector.example/otlp"
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = "x-api-key=secret-value, x-team=agentops"
        try:
            span_batch = build_session_span(_load_fixture("session.json"))
            gauge_batch = build_rate_limit_gauges(_load_fixture("session.json"))
            export_module.export({"spans": [span_batch], "metrics": [gauge_batch]})
        finally:
            export_module.urllib.request.urlopen = orig_urlopen
            del os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]
            del os.environ["OTEL_EXPORTER_OTLP_HEADERS"]

        urls = {request.full_url for request in requests_seen}
        self.assertEqual(urls, {"https://collector.example/otlp/v1/traces", "https://collector.example/otlp/v1/metrics"})
        for request in requests_seen:
            self.assertEqual(request.get_header("X-api-key"), "secret-value")
            self.assertEqual(request.get_header("X-team"), "agentops")

    def test_wire_body_carries_only_the_otlp_envelope_never_the_drop_summary(self) -> None:
        # dropped_attribute_count / dropped_attribute_keys are this library's own
        # summary for callers (--dry-run, tests), not OTLP fields: a protojson
        # receiver rejects unknown top-level fields, and dropped_attribute_keys
        # names exactly the content the allowlist refused to let off this host.
        # Asserted on the serialised bytes actually handed to urlopen, not on the
        # dict passed into export() -- a body built from a stray reference to that
        # dict, rather than a fresh resourceSpans-only envelope, would still pass a
        # same-object check but fail this one.
        import os

        requests_seen = []

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def _fake_urlopen(request, timeout=None):
            requests_seen.append(request)
            return _FakeResponse()

        orig_urlopen = export_module.urllib.request.urlopen
        export_module.urllib.request.urlopen = _fake_urlopen
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://collector.example/otlp"
        try:
            payload = _load_fixture("session_negative.json")
            span_batch = build_session_span(payload)
            gauge_batch = build_rate_limit_gauges(payload)
            self.assertGreater(span_batch["dropped_attribute_count"], 0)
            self.assertGreater(gauge_batch["dropped_attribute_count"], 0)
            export_module.export({"spans": [span_batch], "metrics": [gauge_batch]})
        finally:
            export_module.urllib.request.urlopen = orig_urlopen
            del os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]

        self.assertEqual(len(requests_seen), 2)
        for request in requests_seen:
            raw = request.data
            self.assertIsInstance(raw, bytes)
            decoded = json.loads(raw.decode("utf-8"))
            self.assertIn(set(decoded.keys()), ({"resourceSpans"}, {"resourceMetrics"}))
            self.assertNotIn("dropped_attribute_count", decoded)
            self.assertNotIn("dropped_attribute_keys", decoded)
            # Belt and braces: the forbidden key *names* this fixture drops must not
            # appear anywhere in the serialised bytes, not just absent from the two
            # top-level fields checked above.
            self.assertNotIn(b"dropped_attribute", raw)
            self.assertNotIn(b"prompt", raw)
            self.assertNotIn(b"tool_output", raw)
            self.assertNotIn(b"authorization", raw)


if __name__ == "__main__":
    unittest.main()
