from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "templates/dispatch/scripts/probe_opencode_profile.py"
PROFILE = ROOT / "templates/dispatch/harness-profiles/opencode-nixpkgs-devbox-1.18.4.json"
CONFIG = ROOT / "templates/dispatch/hybrid/opencode.hybrid.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("probe_opencode_profile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


probe = _load_module()


class OpenCodeLifecycleProbeTests(unittest.TestCase):
    def test_fake_probe_is_offline_and_does_not_claim_qualification(self) -> None:
        result = probe.run_fake_probes(PROFILE, CONFIG)
        self.assertFalse(result["provider_contacted"])
        self.assertFalse(result["qualification_eligible"])
        self.assertEqual(result["outstanding_evidence"], ["contained-identity", "provider-qualification"])
        self.assertEqual(result["probes"], {
            "json-events": "pass",
            "stable-session-identity": "pass",
            "session-continuation": "pass",
            "no-tools-finalizer": "pass",
        })

    def test_fake_probe_fails_closed_when_finalizer_receives_a_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "opencode.json"
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
            config["agent"]["ao-finalizer"]["permission"]["read"] = "allow"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(probe.ProbeError, "allowed or unspecified tool"):
                probe.run_fake_probes(PROFILE, config_path)

    def test_fake_probe_fails_closed_when_finalizer_declares_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "opencode.json"
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
            config["agent"]["ao-finalizer"]["mcp"] = {"filesystem": True}
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(probe.ProbeError, "MCP tools"):
                probe.run_fake_probes(PROFILE, config_path)

    def test_fake_probe_fails_closed_when_ao_finalizer_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "opencode.json"
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
            del config["agent"]["ao-finalizer"]
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(probe.ProbeError, "ao-finalizer is missing"):
                probe.run_fake_probes(PROFILE, config_path)

    def test_event_parser_requires_type_properties_session_and_rejects_errors(self) -> None:
        good = {"type": "session.status", "properties": {"sessionID": "ses_1"}}
        self.assertEqual(probe._session_ids(probe._events(json.dumps(good), label="good"), "properties.sessionID"), {"ses_1"})
        cases = [
            ({"properties": {"sessionID": "ses_1"}}, "no type"),
            ({"type": "session.status", "properties": {}}, "no properties.sessionID"),
            ({"type": "session.status", "sessionID": "ses_1"}, "no properties envelope"),
            ({"type": "session.status", "sessionID": "ses_2", "properties": {"sessionID": "ses_1"}}, "multiple session IDs"),
            ({"type": "session.error", "properties": {"sessionID": "ses_1", "error": {}}}, "error event"),
        ]
        for event, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(probe.ProbeError, message):
                probe._events(json.dumps(event), label="bad")

    def test_event_parser_rejects_nested_error_variants(self) -> None:
        cases = [
            {"type": "session.status", "properties": {"sessionID": "ses_1", "status": "failed"}},
            {"type": "session.status", "properties": {"sessionID": "ses_1", "status": {"type": "error"}}},
            {"type": "message.updated", "properties": {"sessionID": "ses_1", "info": {"type": "failure"}}},
            {"type": "message.updated", "properties": {"sessionID": "ses_1", "info": {"state": "timed_out"}}},
            {"type": "message.updated", "properties": {"sessionID": "ses_1", "result": {"status": "cancelled"}}},
            {"type": "message.updated", "properties": {"sessionID": "ses_1", "errors": []}},
            {"type": "session.timeout", "properties": {"sessionID": "ses_1"}},
        ]
        for event in cases:
            with self.subTest(event=event), self.assertRaisesRegex(probe.ProbeError, "error"):
                probe._events(json.dumps(event), label="nested-error")

    def test_event_parser_accepts_nonterminal_nested_status(self) -> None:
        event = {
            "type": "session.status",
            "properties": {
                "sessionID": "ses_1",
                "status": {"type": "idle"},
                "info": {"state": "working", "type": "assistant"},
            },
        }
        self.assertEqual(
            probe._session_ids(probe._events(json.dumps(event), label="nonterminal"), "properties.sessionID"),
            {"ses_1"},
        )

    def test_event_parser_rejects_multiple_session_ids(self) -> None:
        stdout = "\n".join([
            json.dumps({"type": "session.status", "properties": {"sessionID": "ses_1"}}),
            json.dumps({"type": "session.status", "properties": {"sessionID": "ses_2"}}),
        ])
        with self.assertRaisesRegex(probe.ProbeError, "multiple session IDs"):
            probe._events(stdout, label="mismatch")

    def test_finalizer_agent_must_be_effective_agent_not_cli_default(self) -> None:
        events = [{
            "type": "message.updated",
            "properties": {"sessionID": "ses_1", "info": {"role": "assistant", "agent": "ao-mechanical-bulk"}},
        }]
        with self.assertRaisesRegex(probe.ProbeError, "effective agent"):
            probe._effective_agent(events, "ao-finalizer", label="fallback")

    def test_no_tool_events_rejects_nested_tool_shapes(self) -> None:
        for event in (
            {"type": "tool", "properties": {"sessionID": "ses_1"}},
            {"type": "message.updated", "properties": {"sessionID": "ses_1", "part": {"type": "tool"}}},
            {"type": "message.updated", "properties": {"sessionID": "ses_1", "info": {"role": "tool"}}},
            {"type": "tool_result", "properties": {"sessionID": "ses_1"}},
        ):
            with self.subTest(event=event), self.assertRaisesRegex(probe.ProbeError, "tool event"):
                probe._assert_no_tool_events([event], label="finalizer")

    def test_fake_probe_fails_closed_on_profile_continuation_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile_path = Path(temporary) / "profile.json"
            profile = json.loads(PROFILE.read_text(encoding="utf-8"))
            profile["lifecycle"]["continuation"]["fork"] = True
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(probe.ProbeError, "same-session continuation"):
                probe.run_fake_probes(profile_path, CONFIG)

    def test_real_mode_is_explicit_and_keeps_provider_evidence_separate(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('choices=("fake", "contained", "all")', source)
        self.assertIn('"provider_contacted": False', source)
        self.assertIn('"provider_contacted": True', source)


if __name__ == "__main__":
    unittest.main()
