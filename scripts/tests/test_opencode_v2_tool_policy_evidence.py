"""Keep the checked-in OpenCode v2 qualification result bound and scoped."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/2026-11-03-opencode-v2"
PROBE = EVIDENCE / "opencode-v2-tool-policy-probe-2026-11-03.py"
RESULT = EVIDENCE / "opencode-v2-tool-policy-result-2026-11-03.json"
MCP_PROBE = EVIDENCE / "opencode-v2-mcp-discovery-probe-2026-11-03.py"
MCP_RESULT = EVIDENCE / "opencode-v2-mcp-discovery-result-2026-11-03.json"


def test_tool_policy_result_is_bound_to_probe_and_pinned_binary():
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    assert hashlib.sha256(PROBE.read_bytes()).hexdigest() == (
        "b449e4f3fc413909d1d129009e9bf9e508dfdbc3c43356b048138c139f886106"
    )
    assert hashlib.sha256(RESULT.read_bytes()).hexdigest() == (
        "90d282af1e69c1c0f91978bcf9ca53c7ea971e55d8abb3a816f3df9ccd8342dc"
    )
    assert result["schema"] == "opencode-v2-tool-policy-probe/v1"
    assert result["version"] == "2.0.32"
    assert result["isolation"]["network"].startswith("bubblewrap --unshare-net")
    assert result["isolation"]["production_effects"] == "none"


def test_tool_policy_denials_have_positive_controls():
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    cases = {item["case"]: item for item in result["results"]}

    for name in ("read-deny", "write-deny", "webfetch-deny", "subagent-deny", "skill-deny"):
        assert cases[name]["tool_offered"] is False
        assert cases[name]["tool_status"] == "error"

    assert cases["read-deny"]["read_canary_returned"] is False
    assert cases["read-allow"]["read_canary_returned"] is True
    assert cases["write-deny"]["write_target_created"] is False
    assert cases["write-allow"]["write_target_created"] is True
    assert cases["webfetch-deny"]["loopback_http_hits"] == 0
    assert cases["webfetch-allow"]["loopback_http_hits"] == 1
    assert cases["subagent-allow"]["fake_provider_requests"] >= 3
    assert cases["skill-allow"]["skill_marker_in_tool_output"] is True


def test_mutated_rule_fails_denial_and_restart_preserves_the_ordered_policy():
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    mutation = result["mutated_negative_control"]
    assert mutation["rule_mutation"] == "wildcard deny changed to wildcard allow"
    assert mutation["observed_canary_read"] is True
    assert mutation["denial_assertion_failed_as_expected"] is True

    restart = result["restart_recovery"]
    assert restart["same_session_id"] is True
    assert restart["ordered_permissions_exact"] is True
    assert restart["read_tool_offered"] is False
    assert restart["read_tool_rejected"] is True
    assert restart["read_canary_returned"] is False


def test_mcp_scope_is_explicitly_unqualified():
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    assert result["mcp"]["status"] == "untested"
    mcp = json.loads(MCP_RESULT.read_text(encoding="utf-8"))
    assert hashlib.sha256(MCP_PROBE.read_bytes()).hexdigest() == (
        "286b6c7c64b9c41d973119d8fd00d1bdcc43d39997f90631424acc61b4a395e7"
    )
    assert hashlib.sha256(MCP_RESULT.read_bytes()).hexdigest() == (
        "625c9a23875bd39af5e91a5cd093ee1db163a2edc9f83214181df49299cfbe37"
    )
    assert mcp["schema"] == "opencode-v2-mcp-discovery-probe/v1"
    assert mcp["version"] == "2.0.32"
    assert mcp["mcp_cli"]["stdout"].strip() == "No MCP servers configured"
    assert "mcp__localtest__echo" not in mcp["discovery_tool_names"]
    assert mcp["mcp_tool_name"] is None
    assert mcp["mcp_calls"] == []
    assert "permission allow/deny was not tested" in mcp["limitation"]
    assert mcp["denied"]["parts"][0]["status"] == "error"
    assert all(case["parts"][0]["status"] == "error" for case in mcp["allow_rule_candidates"].values())
    doc = (EVIDENCE / "lifecycle-qualification.md").read_text(encoding="utf-8")
    assert "MCP allow/deny remains untested because this binary did not" in doc
    assert "unknown-tool rejections, not permission" in doc
