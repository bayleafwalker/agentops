from __future__ import annotations

import contextlib
import importlib.util
import io
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[3]
HYBRID = ROOT / "templates/dispatch/hybrid"
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dispatch = _load_module("hybrid_dispatch", SCRIPTS / "hybrid_dispatch.py")
validator = _load_module("validate_hybrid_dispatch", SCRIPTS / "validate_hybrid_dispatch.py")


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class PolicyContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = _json(HYBRID / "hybrid-dispatch.v1.json")
        self.worker_config = _json(HYBRID / "opencode.hybrid.json")

    def test_policy_and_worker_config_agree(self) -> None:
        validator.validate_policy(self.policy, self.worker_config)

    def test_worker_uses_a_named_implementation_profile(self) -> None:
        self.assertEqual(
            self.policy["worker"]["implementation_profile"],
            "opencode-nixpkgs-devbox-1.18.4",
        )
        self.assertNotIn("cli_version_verified", self.policy["worker"])

    def test_vuoro_tooling_mechanical_bulk_is_a_named_pilot(self) -> None:
        qualification = self.policy["qualification"]
        self.assertEqual(qualification["mode"], "named_pilot")
        self.assertEqual(qualification["repositories"], [
            "agentops",
            "1deb57d0-af6f-479c-811a-b5b7254841f9",
            "2be118eb-8e89-433a-8d32-ada157624f95",
            "kctl",
            "actionq",
        ])
        self.assertEqual(qualification["routes"], ["mechanical_bulk"])
        self.assertEqual(qualification["default"], "unqualified")
        self.assertEqual(self.policy["routes"]["mechanical_bulk"]["status"], "available_named_pilot")
        for name, route in self.policy["routes"].items():
            if name != "mechanical_bulk" and "status" in route:
                with self.subTest(route=name):
                    self.assertNotEqual(route["status"], "available_named_pilot")

    def test_bindery_route_is_project_scoped_and_unqualified(self) -> None:
        route = self.policy["routes"]["bindery_external_runtime_w0"]
        self.assertEqual(route["harness_model"], "local3090/worker-fast")
        self.assertEqual(route["profile_id"], "opencode-workstation-local3090-1.18.21")
        self.assertEqual(route["status"], "project_scoped_preflight")
        self.assertEqual(
            route["repository_scope"]["repositories"],
            ["bindery-core"],
        )
        self.assertNotIn("bindery_external_runtime_w0", self.policy["qualification"]["routes"])
        self.assertNotIn("local3090/worker-fast", self.policy["qualification"]["models"])
        self.assertEqual(self.policy["qualification"]["default"], "unqualified")

    def test_bindery_worker_config_declares_its_local_provider(self) -> None:
        provider = self.worker_config["provider"]["local3090"]
        self.assertEqual(provider["npm"], "@ai-sdk/openai-compatible")
        self.assertEqual(provider["options"]["baseURL"], "http://127.0.0.1:8020/v1")
        self.assertEqual(provider["models"]["worker-fast"]["limit"], {
            "context": 32768,
            "output": 8192,
        })

    def test_worker_is_denied_state_bearing_authority(self) -> None:
        denied = self.policy["worker"]["denied_authority"]
        for authority in ("git", "sprintctl", "kctl", "actionq", "acceptance or merge"):
            with self.subTest(authority=authority):
                self.assertIn(authority, denied)

    def test_sprint_state_and_acceptance_stay_outside_the_worker(self) -> None:
        self.assertEqual(self.policy["sprintctl_authority"], "coordinator_only")
        self.assertEqual(self.policy["acceptance_authority"], "human")

    def test_k3_is_benchmark_only_and_never_replaces_coordinator_review(self) -> None:
        challenger = self.policy["routes"]["k3_benchmark"]
        self.assertEqual(challenger["status"], "benchmark_only")
        self.assertEqual(self.policy["model_states"]["opencode-go/kimi-k3"]["routes"], [])
        self.assertIn("coordinator-review-recorded", self.policy["gates"]["post"])

    def test_rejects_a_worker_config_that_pre_authorizes_bash(self) -> None:
        broken = json.loads(json.dumps(self.worker_config))
        broken["agent"]["ao-mechanical-bulk"]["permission"]["webfetch"] = "allow"
        with self.assertRaises(ValueError):
            validator.validate_policy(self.policy, broken)

    def test_rejects_missing_finalizer_instead_of_allowing_default_agent_fallback(self) -> None:
        broken = json.loads(json.dumps(self.worker_config))
        del broken["agent"]["ao-finalizer"]
        with self.assertRaisesRegex(ValueError, "ao-finalizer must be configured"):
            validator.validate_policy(self.policy, broken)

    def test_rejects_finalizer_tool_or_mcp_permission(self) -> None:
        for mutation in (
            lambda config: config["agent"]["ao-finalizer"]["permission"].update({"mcp.filesystem": "allow"}),
            lambda config: config["agent"]["ao-finalizer"].update({"tools": {"read": True}}),
        ):
            with self.subTest(mutation=mutation):
                broken = json.loads(json.dumps(self.worker_config))
                mutation(broken)
                with self.assertRaises(ValueError):
                    validator.validate_policy(self.policy, broken)


class ManifestHybridBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = _json(HYBRID / "hybrid-dispatch.v1.json")

    def test_agentops_manifest_block_is_valid(self) -> None:
        path = ROOT / "agentops.dispatch.json"
        self.assertTrue(validator.validate_manifest_hybrid(_json(path), self.policy, path))

    def test_dispatch_contract_paths_are_protected_from_the_worker(self) -> None:
        hybrid = _json(ROOT / "agentops.dispatch.json")["hybrid"]
        self.assertIn("templates/dispatch/hybrid/**", hybrid["protected_paths"])
        self.assertIn("templates/dispatch/scripts/hybrid_dispatch.py", hybrid["protected_paths"])

    def test_empty_protected_paths_are_rejected(self) -> None:
        manifest = _json(ROOT / "agentops.dispatch.json")
        manifest["hybrid"]["protected_paths"] = []
        with self.assertRaises(ValueError):
            validator.validate_manifest_hybrid(manifest, self.policy, Path("x.dispatch.json"))


class PacketValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = _json(HYBRID / "hybrid-dispatch.v1.json")
        self.manifest = {
            "repo_id": "example",
            "scope": {"allowed_path_roots": ["src/", "tests/"]},
            "hybrid": {
                "enabled": True,
                "worker_routes": ["mechanical_bulk"],
                "commands": {"example.tests": "pytest -q"},
                "protected_paths": ["src/authority/**"],
                "max_timeout_seconds": 1200,
                "max_cost_usd": 3.0,
                "soft_token_ceiling": 500000,
                "hard_token_ceiling": 1000000,
            },
        }
        self.packet = {
            "schema_version": "agentops-task/v2",
            "task_id": "EX-1",
            "repo_id": "example",
            "sprint_item": {"ref": "example#42", "claim_id": 7, "claim_actor": "coordinator/claude-code"},
            "route": "mechanical_bulk",
            "task_class": "mechanical_implementation",
            "risk": "low",
            "oracle": {
                "ownership": "externally_defined",
                "worker_may_modify": False,
                "description": "Coordinator-authored executable oracle",
            },
            "attempt": 1,
            "starting_commit": "a" * 40,
            "purpose": "p",
            "readable_context_paths": ["src/**"],
            "writable_patch_paths": ["tests/**"],
            "protected_paths": ["src/authority/**"],
            "required_outcomes": ["o"],
            "acceptance_properties": [
                {
                    "id": "REQ-001",
                    "requirement": "o",
                    "command_id": "example.tests",
                    "fails_when": "o is not implemented",
                }
            ],
            "non_goals": ["n"],
            "allowed_command_ids": ["example.tests"],
            "limits": {
                "timeout_seconds": 600,
                "max_cost_usd": 0.25,
                "soft_token_ceiling": 500000,
                "hard_token_ceiling": 1000000,
            },
            "context_churn": {
                "max_repeated_reads_per_path": 4,
                "max_reasoning_steps_without_mutation": 8,
                "max_identical_context_tokens": 250000,
                "handoff_when_candidate_ready": True,
            },
            "network_policy": "disabled",
            "worktree": {"root": "/tmp/wt", "branch": "hybrid/ex-1", "cleanup": "retain-for-review"},
        }

    def _validate(self):
        return dispatch.validate_packet(self.packet, self.manifest, self.policy)

    #: What ``validate_packet`` alone can observe. The remaining configured
    #: gates are not knowable without a workspace or an oracle run, and are
    #: reported ``not_evaluated`` with the evaluator that owns them.
    OBSERVED_AT_VALIDATE = [
        "packet-schema-valid",
        "scope-within-manifest",
        "protected-paths-untouched",
    ]

    def test_a_fit_packet_reports_only_the_gates_actually_observed(self) -> None:
        """It used to return ``policy["gates"]["pre"]`` -- the policy's own list,
        echoed back whether or not anything had been checked. Six of those eight
        names were computed by nothing, which is how a schema-invalid packet was
        dispatched twice under ``packet-schema-valid``."""
        results = self._validate()
        self.assertEqual(
            dispatch.satisfied_pre_gates(results), self.OBSERVED_AT_VALIDATE)
        self.assertEqual(
            sorted(r.name for r in results), sorted(self.policy["gates"]["pre"]),
            "every configured gate must be reported, passed or not")
        for result in results:
            self.assertNotEqual(
                result.evaluator, "unregistered",
                f"{result.name} has no evaluator and must fail closed")

    def test_an_unregistered_gate_fails_closed(self) -> None:
        """A gate configured in policy with nothing to compute it blocks."""
        policy = json.loads(json.dumps(self.policy))
        policy["gates"]["pre"] = policy["gates"]["pre"] + ["invented-gate"]
        results = dispatch.validate_packet(self.packet, self.manifest, policy)
        invented = [r for r in results if r.name == "invented-gate"]
        self.assertEqual(1, len(invented))
        self.assertEqual("not_evaluated", invented[0].status)
        self.assertEqual("unregistered", invented[0].evaluator)
        self.assertIn(invented[0], dispatch.blocking_pre_gates(results))

    def test_a_schema_invalid_packet_fails_its_own_gate(self) -> None:
        """V6-K's actual defect: debt frozen as a string, reported fit twice."""
        packet = json.loads(json.dumps(self.packet))
        packet["debt"] = "a string, where the schema requires an array"
        results = dispatch.validate_packet(packet, self.manifest, self.policy)
        schema_gate = next(r for r in results if r.name == "packet-schema-valid")
        self.assertEqual("failed", schema_gate.status)
        self.assertTrue(any("debt" in line for line in schema_gate.evidence))
        self.assertNotIn("packet-schema-valid", dispatch.satisfied_pre_gates(results))

    def test_every_gate_result_carries_its_input_digest(self) -> None:
        expected = dispatch.packet_input_digest(self.packet)
        for result in self._validate():
            self.assertEqual(expected, result.input_digest)

    def test_only_the_named_scope_is_labelled_as_pilot(self) -> None:
        self.assertEqual(dispatch.qualification_state(self.policy, self.packet), "unqualified")
        pilot = json.loads(json.dumps(self.packet))
        pilot["repo_id"] = "1deb57d0-af6f-479c-811a-b5b7254841f9"
        pilot["sprint_item"]["ref"] = "1deb57d0-af6f-479c-811a-b5b7254841f9#42"
        self.assertEqual(dispatch.qualification_state(self.policy, pilot), "named_pilot:vuoro-tooling-bulk-2026-07-28")

    def test_bound_project_route_is_accepted_but_remains_unqualified(self) -> None:
        core_repo = "bindery-core"
        packet = json.loads(json.dumps(self.packet))
        manifest = json.loads(json.dumps(self.manifest))
        packet["route"] = "bindery_external_runtime_w0"
        packet["repo_id"] = core_repo
        packet["sprint_item"]["ref"] = f"{core_repo}#42"
        manifest["repo_id"] = core_repo
        manifest["hybrid"]["worker_routes"] = ["bindery_external_runtime_w0"]
        self.assertEqual(
            dispatch.satisfied_pre_gates(
                dispatch.validate_packet(packet, manifest, self.policy)),
            self.OBSERVED_AT_VALIDATE)
        self.assertEqual(dispatch.qualification_state(self.policy, packet), "unqualified")

    def test_project_route_rejects_a_repository_outside_its_scope(self) -> None:
        core_repo = "bindery-core"
        packet = json.loads(json.dumps(self.packet))
        manifest = json.loads(json.dumps(self.manifest))
        policy = json.loads(json.dumps(self.policy))
        packet["route"] = "bindery_external_runtime_w0"
        packet["repo_id"] = core_repo
        packet["sprint_item"]["ref"] = f"{core_repo}#42"
        manifest["repo_id"] = core_repo
        manifest["hybrid"]["worker_routes"] = ["bindery_external_runtime_w0"]
        policy["routes"]["bindery_external_runtime_w0"]["repository_scope"]["repositories"] = ["another-project"]
        with self.assertRaisesRegex(dispatch.PacketError, "different project repository"):
            dispatch.validate_packet(packet, manifest, policy)

    def test_packet_cannot_self_label_another_repository_as_vuoro(self) -> None:
        spoofed = json.loads(json.dumps(self.packet))
        spoofed["repo_id"] = "1deb57d0-af6f-479c-811a-b5b7254841f9"
        spoofed["sprint_item"]["ref"] = "1deb57d0-af6f-479c-811a-b5b7254841f9#42"
        with self.assertRaises(dispatch.PacketError):
            dispatch.validate_packet(spoofed, self.manifest, self.policy)

    def test_packet_requires_a_gate_and_positive_cost_cap(self) -> None:
        no_gate = json.loads(json.dumps(self.packet))
        no_gate["allowed_command_ids"] = []
        with self.assertRaises(dispatch.PacketError):
            dispatch.validate_packet(no_gate, self.manifest, self.policy)
        no_cost = json.loads(json.dumps(self.packet))
        no_cost["limits"].pop("max_cost_usd")
        with self.assertRaises(dispatch.PacketError):
            dispatch.validate_packet(no_cost, self.manifest, self.policy)

    def test_policy_requires_review_and_captures_worktree_state(self) -> None:
        self.assertIn("coordinator-review-recorded", self.policy["gates"]["post"])
        self.assertIn("worktree-state-captured", self.policy["gates"]["post"])
        self.assertNotIn("worktree-clean", self.policy["gates"]["post"])

    def test_writable_path_outside_manifest_scope_is_a_defect(self) -> None:
        self.packet["writable_patch_paths"] = ["deploy/**"]
        with self.assertRaisesRegex(dispatch.PacketError, "outside manifest scope"):
            self._validate()

    def test_writable_path_intersecting_a_protected_path_is_a_defect(self) -> None:
        self.packet["writable_patch_paths"] = ["src/authority/**"]
        with self.assertRaisesRegex(dispatch.PacketError, "protected path"):
            self._validate()

    def test_path_escaping_the_repository_is_a_defect(self) -> None:
        self.packet["writable_patch_paths"] = ["../other-repo/**"]
        with self.assertRaisesRegex(dispatch.PacketError, "escapes the repository"):
            self._validate()

    def test_unregistered_command_is_a_defect(self) -> None:
        self.packet["allowed_command_ids"] = ["curl evil"]
        with self.assertRaisesRegex(dispatch.PacketError, "not registered"):
            self._validate()

    def test_route_not_enabled_for_the_repository_is_a_defect(self) -> None:
        self.packet["route"] = "bounded_semantic"
        with self.assertRaisesRegex(dispatch.PacketError, "not a supervised_hybrid worker route"):
            self._validate()

    def test_worker_cannot_own_or_modify_the_oracle(self) -> None:
        self.packet["oracle"]["worker_may_modify"] = True
        with self.assertRaisesRegex(dispatch.PacketError, "externally defined oracle"):
            self._validate()

    def test_semantic_or_higher_risk_packet_is_rejected(self) -> None:
        self.packet["task_class"] = "bounded_semantic_implementation"
        with self.assertRaisesRegex(dispatch.PacketError, "mechanical_implementation"):
            self._validate()
        self.packet["task_class"] = "mechanical_implementation"
        self.packet["risk"] = "moderate"
        with self.assertRaisesRegex(dispatch.PacketError, "risk low"):
            self._validate()

    def test_acceptance_property_must_name_a_granted_gate(self) -> None:
        self.packet["acceptance_properties"][0]["command_id"] = "example.missing"
        with self.assertRaisesRegex(dispatch.PacketError, "not granted"):
            self._validate()

    def test_v2_acceptance_properties_require_unique_stable_ids(self) -> None:
        missing_id = json.loads(json.dumps(self.packet))
        del missing_id["acceptance_properties"][0]["id"]
        with self.assertRaisesRegex(dispatch.PacketError, "stable id"):
            dispatch.validate_packet(missing_id, self.manifest, self.policy)

        duplicate = json.loads(json.dumps(self.packet))
        duplicate["acceptance_properties"].append(
            {
                "id": "REQ-001",
                "requirement": "another requirement",
                "command_id": "example.tests",
                "fails_when": "another requirement is not implemented",
            }
        )
        with self.assertRaisesRegex(dispatch.PacketError, "duplicated"):
            dispatch.validate_packet(duplicate, self.manifest, self.policy)

    def test_legacy_v1_packet_preserves_pre_id_validation(self) -> None:
        legacy = json.loads(json.dumps(self.packet))
        legacy["schema_version"] = dispatch.LEGACY_PACKET_SCHEMA_VERSION
        del legacy["acceptance_properties"][0]["id"]
        self.assertEqual(
            dispatch.satisfied_pre_gates(
                dispatch.validate_packet(legacy, self.manifest, self.policy)),
            self.OBSERVED_AT_VALIDATE,
        )
        self.assertEqual(
            dispatch.gate_set_hash_schema_version(legacy),
            "agentops-hybrid-gate-set/v1",
        )

    def test_v1_packet_cannot_silently_change_to_v2_id_semantics(self) -> None:
        legacy = json.loads(json.dumps(self.packet))
        legacy["schema_version"] = dispatch.LEGACY_PACKET_SCHEMA_VERSION
        with self.assertRaisesRegex(dispatch.PacketError, "cannot declare v2 stable ids"):
            dispatch.validate_packet(legacy, self.manifest, self.policy)

    def test_v2_id_grammar_matches_the_schema_contract(self) -> None:
        invalid = json.loads(json.dumps(self.packet))
        invalid["acceptance_properties"][0]["id"] = "REQ 001"
        with self.assertRaisesRegex(dispatch.PacketError, "must start with a letter"):
            dispatch.validate_packet(invalid, self.manifest, self.policy)

    def test_receipt_versions_the_gate_hash_break(self) -> None:
        legacy = json.loads(json.dumps(self.packet))
        legacy["schema_version"] = dispatch.LEGACY_PACKET_SCHEMA_VERSION
        del legacy["acceptance_properties"][0]["id"]
        dispatch.validate_packet(legacy, self.manifest, self.policy)

        legacy_receipt = dispatch._receipt(legacy, self.policy)
        v2_receipt = dispatch._receipt(self.packet, self.policy)
        legacy_gate_bytes = json.dumps(
            {
                "allowed_command_ids": legacy["allowed_command_ids"],
                "acceptance_properties": legacy["acceptance_properties"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.assertEqual(
            legacy_receipt["inputs"]["gate_set_hash"],
            f"sha256:{hashlib.sha256(legacy_gate_bytes).hexdigest()}",
        )
        self.assertEqual(
            legacy_receipt["inputs"]["packet_schema_version"],
            "agentops-task/v1",
        )
        self.assertEqual(
            legacy_receipt["inputs"]["gate_set_hash_schema_version"],
            "agentops-hybrid-gate-set/v1",
        )
        self.assertEqual(
            v2_receipt["inputs"]["packet_schema_version"],
            "agentops-task/v2",
        )
        self.assertEqual(
            v2_receipt["inputs"]["gate_set_hash_schema_version"],
            "agentops-hybrid-gate-set/v2",
        )
        self.assertNotEqual(
            legacy_receipt["inputs"]["gate_set_hash"],
            v2_receipt["inputs"]["gate_set_hash"],
        )

    def test_enabled_network_is_a_defect(self) -> None:
        self.packet["network_policy"] = "enabled"
        with self.assertRaisesRegex(dispatch.PacketError, "network_policy"):
            self._validate()

    def test_missing_sprint_claim_actor_is_a_defect(self) -> None:
        self.packet["sprint_item"] = {"ref": "example#42", "claim_id": 7}
        with self.assertRaisesRegex(dispatch.PacketError, "claim_actor"):
            self._validate()

    def test_missing_sprint_claim_id_is_a_defect(self) -> None:
        del self.packet["sprint_item"]["claim_id"]
        with self.assertRaisesRegex(dispatch.PacketError, "claim_id"):
            self._validate()

    def test_repository_without_a_hybrid_block_is_not_eligible(self) -> None:
        del self.manifest["hybrid"]
        with self.assertRaisesRegex(dispatch.PacketError, "not hybrid-eligible"):
            self._validate()

    def test_timeout_above_the_repository_ceiling_is_a_defect(self) -> None:
        self.packet["limits"]["timeout_seconds"] = 1800
        with self.assertRaisesRegex(dispatch.PacketError, "exceeds the repository ceiling"):
            self._validate()

    def test_cost_above_the_repository_ceiling_is_a_defect(self) -> None:
        # The timeout ceiling was enforced from the start and the cost ceiling
        # was not, so a packet could declare any budget it liked.
        self.packet["limits"]["max_cost_usd"] = 99.0
        with self.assertRaisesRegex(dispatch.PacketError, "exceeds the repository ceiling"):
            self._validate()

    def test_attempt_above_the_route_allowance_is_a_defect(self) -> None:
        # Derived, not hardcoded: the property is "one past the allowance is
        # refused", and the allowance is a policy decision that has moved once
        # already (one retry -> two, 2026-08-24). A literal here pins the
        # decision rather than the property.
        allowance = self.policy["routes"][self.packet["route"]]["max_attempts"]
        self.packet["attempt"] = allowance + 1
        with self.assertRaisesRegex(dispatch.PacketError, "exceeds max_attempts"):
            self._validate()

    def test_context_churn_defaults_preserve_v1_and_explicit_limits_are_bounded(self) -> None:
        missing = json.loads(json.dumps(self.packet))
        del missing["context_churn"]
        dispatch.validate_packet(missing, self.manifest, self.policy)
        self.assertEqual(
            dispatch.context_churn_limits(missing)["max_repeated_reads_per_path"], 4
        )
        self.packet["context_churn"]["max_repeated_reads_per_path"] = 13
        with self.assertRaisesRegex(dispatch.PacketError, "max_repeated_reads_per_path"):
            self._validate()

    def test_candidate_ready_requires_early_handoff(self) -> None:
        self.packet["context_churn"]["handoff_when_candidate_ready"] = False
        with self.assertRaisesRegex(dispatch.PacketError, "handoff_when_candidate_ready"):
            self._validate()


class OverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = _json(HYBRID / "hybrid-dispatch.v1.json")
        self.base = _json(HYBRID / "opencode.hybrid.json")
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
        packet_tests.setUp()
        self.packet = packet_tests.packet
        self.manifest = packet_tests.manifest

    def _overlay(self):
        return dispatch.build_overlay(self.packet, self.manifest, self.policy, self.base)

    def test_overlay_enumerates_every_tool_and_leaves_nothing_at_ask(self) -> None:
        overlay = self._overlay()
        # A blanket top-level "*": "deny" withholds every tool from the model
        # rather than gating calls, which leaves the worker unable to act and
        # guarantees an empty diff. Tools are enumerated instead.
        self.assertNotIn("*", overlay["permission"])
        # Noninteractive `opencode run` rejects any permission left at "ask",
        # so every resolved value must be an explicit allow or deny.
        blocks = [overlay["permission"], *(a["permission"] for a in overlay["agent"].values())]
        for block in blocks:
            for key, value in block.items():
                values = value.values() if isinstance(value, dict) else [value]
                for resolved in values:
                    with self.subTest(key=key):
                        self.assertIn(resolved, ("allow", "deny"))

    def test_overlay_grants_the_read_side_tools_the_worker_needs(self) -> None:
        permission = self._overlay()["permission"]
        for key in ("read", "glob", "grep", "list"):
            with self.subTest(key=key):
                self.assertEqual(permission[key], "allow")

    def test_overlay_allows_only_the_packet_commands(self) -> None:
        bash = self._overlay()["permission"]["bash"]
        self.assertEqual(list(bash), ["*", "pytest -q"])
        self.assertEqual(bash["pytest -q"], "allow")
        self.assertEqual(bash["*"], "deny")

    def test_overlay_grants_edit_whole_and_defers_scope_to_the_gates(self) -> None:
        # The qualified implementation profile withholds the edit tool outright
        # when an `edit` map denies "*", so per-path scoping here would only
        # ever produce an empty diff. writable_patch_paths stays enforced by
        # the cold post-gates.
        overlay = self._overlay()
        self.assertEqual(overlay["permission"]["edit"], "allow")
        self.assertEqual(overlay["permission"]["external_directory"], "deny")

    def test_benchmark_agent_withholds_every_write_surface(self) -> None:
        permission = self.base["agent"]["ao-review"]["permission"]
        for key in ("edit", "bash"):
            with self.subTest(key=key):
                self.assertEqual(permission[key], "deny")

    def test_finalizer_withholds_every_tool_surface(self) -> None:
        permission = self.base["agent"]["ao-finalizer"]["permission"]
        self.assertEqual(permission["*"], "deny")
        for key in ("read", "glob", "grep", "list", "edit", "write", "patch", "bash", "task"):
            with self.subTest(key=key):
                self.assertEqual(permission[key], "deny")

    def test_overlay_keeps_network_and_subagents_denied(self) -> None:
        agent = self._overlay()["agent"]["ao-mechanical-bulk"]["permission"]
        for key in ("task", "external_directory", "webfetch", "websearch"):
            with self.subTest(key=key):
                self.assertEqual(agent[key], "deny")

    def test_overlay_hash_is_stable_and_content_addressed(self) -> None:
        first = dispatch.overlay_hash(self._overlay())
        self.assertEqual(first, dispatch.overlay_hash(self._overlay()))
        reordered = self._overlay()
        bash = reordered["permission"]["bash"]
        reordered["permission"]["bash"] = {
            command: decision
            for command, decision in reversed(list(bash.items()))
        }
        self.assertNotEqual(first, dispatch.overlay_hash(reordered))
        # The overlay now carries the command vocabulary but not the writable
        # paths, so the hash tracks what the worker is actually granted.
        self.packet["allowed_command_ids"] = []
        self.assertNotEqual(first, dispatch.overlay_hash(self._overlay()))

    def test_writable_scope_is_enforced_by_the_gates_not_the_overlay(self) -> None:
        # Since the overlay no longer scopes `edit`, the packet's writable
        # contract has to bite somewhere. It bites in the cold post-gates.
        self.assertNotIn("tests/**", json.dumps(self._overlay()))
        self.assertIn("diff-scope-respected", self.policy["gates"]["post"])


class IndependentReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
        packet_tests.setUp()
        self.packet = packet_tests.packet

    def test_independent_candidate_review_requires_distinct_reviewer_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "gate.json"
            evidence.write_text("{}\n", encoding="utf-8")
            review_path = root / "review.json"
            review_path.write_text(json.dumps({
                "task_id": self.packet["task_id"],
                "reviewer": "reviewer/codex",
                "context": "independent",
                "decision": "candidate",
                "evidence_path": str(evidence),
            }), encoding="utf-8")
            self.assertEqual(
                dispatch.load_independent_review(review_path, self.packet)["reviewer"],
                "reviewer/codex",
            )

    def test_independent_review_cannot_be_authored_by_claim_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "gate.json"
            evidence.write_text("{}\n", encoding="utf-8")
            review_path = root / "review.json"
            review_path.write_text(json.dumps({
                "task_id": self.packet["task_id"],
                "reviewer": self.packet["sprint_item"]["claim_actor"],
                "context": "independent",
                "decision": "candidate",
                "evidence_path": str(evidence),
            }), encoding="utf-8")
            with self.assertRaisesRegex(dispatch.PacketError, "reviewer must differ"):
                dispatch.load_independent_review(review_path, self.packet)


class SelfCandidateTests(unittest.TestCase):
    """L-3 (D-8): a class the manifest marks self_candidate mints a candidate
    from green evidence alone; every other class still needs the record."""

    def setUp(self) -> None:
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
        packet_tests.setUp()
        self.packet = packet_tests.packet
        self.manifest = packet_tests.manifest
        self.manifest["routing"] = {
            "default_harness": "opencode", "default_model_alias": "fast-build",
            "action_classes": {"mechanical_bulk": {
                "enabled": True, "self_candidate": True, "self_candidate_ruling": "owner 2026-08-23",
                "permitted_routes": ["mechanical_bulk"],
            }},
        }

    def _gate(self, passed: bool, review_record: bool = False) -> tuple[int, dict]:
        originals = (dispatch.verify_live_coordinator_claim, dispatch.post_gates, dispatch.load_independent_review)
        dispatch.verify_live_coordinator_claim = lambda *a, **k: {"claim": "stubbed"}
        dispatch.post_gates = lambda *a, **k: {"passed": passed, "results": []}
        dispatch.load_independent_review = lambda *a, **k: {"reviewer": "reviewer/codex", "context": "independent"}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                packet_path = Path(tmp) / "p.json"
                self.packet["worktree"]["root"] = str(Path(tmp) / "wt")
                (Path(tmp) / "wt" / self.packet["repo_id"] / self.packet["task_id"]).mkdir(parents=True)
                packet_path.write_text(json.dumps(self.packet), encoding="utf-8")
                (Path(tmp) / "example.dispatch.json").write_text(json.dumps(self.manifest), encoding="utf-8")
                argv = ["--repo-root", tmp, "--packet", str(packet_path), "--agentops-root", str(ROOT)]
                if review_record:
                    argv += ["--review-record", str(packet_path)]
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = dispatch.main(argv + ["gate"])
                return code, json.loads(out.getvalue())
        finally:
            dispatch.verify_live_coordinator_claim, dispatch.post_gates, dispatch.load_independent_review = originals

    def test_schema_declares_self_candidate_default_false(self) -> None:
        schema = _json(ROOT / "templates/dispatch/manifest.schema.json")
        prop = schema["properties"]["routing"]["properties"]["action_classes"]["additionalProperties"]["properties"]["self_candidate"]
        self.assertEqual(prop["type"], "boolean")
        self.assertIs(prop["default"], False)

    def test_self_candidate_class_and_green_gates_is_candidate_without_a_record(self) -> None:
        code, receipt = self._gate(passed=True)
        self.assertEqual(code, 0, receipt)
        self.assertEqual(receipt["disposition"], "candidate")
        self.assertEqual(receipt["independent_review"],
                         {"mode": "self_candidate", "class": "mechanical_bulk", "basis": "manifest"})

    def test_self_candidate_class_with_a_red_gate_is_not_candidate(self) -> None:
        code, receipt = self._gate(passed=False)
        self.assertEqual(code, 2)
        self.assertEqual(receipt["disposition"], "coordinator_review_required")
        self.assertIsNone(receipt["independent_review"])

    def test_a_class_without_self_candidate_still_requires_the_record(self) -> None:
        self.manifest["routing"]["action_classes"]["mechanical_bulk"]["self_candidate"] = False
        code, receipt = self._gate(passed=True)
        self.assertEqual(code, 2)
        self.assertEqual(receipt["disposition"], "coordinator_review_required")
        self.assertIsNone(receipt["independent_review"])
        code, receipt = self._gate(passed=True, review_record=True)
        self.assertEqual(code, 0)
        self.assertEqual(receipt["disposition"], "candidate")
        self.assertEqual(receipt["independent_review"]["reviewer"], "reviewer/codex")

    def test_a_packet_cannot_claim_self_candidate_for_an_unflipped_class(self) -> None:
        self.manifest["routing"]["action_classes"] = {"build": {"enabled": True, "self_candidate": True}}
        self.assertIsNone(dispatch.self_candidate_class(self.packet, self.manifest))
        self.manifest.pop("routing")
        self.assertIsNone(dispatch.self_candidate_class(self.packet, self.manifest))

    def test_agentops_manifest_flips_mechanical_bulk_with_a_ruling(self) -> None:
        manifest = _json(ROOT / "agentops.dispatch.json")
        entry = manifest["routing"]["action_classes"]["mechanical_bulk"]
        self.assertIs(entry["self_candidate"], True)
        # The 2026-08-26 reissue (agentops#2100, Option C) keys the grant to the
        # action class and names the routes it covers. It must still carry the
        # 2026-08-23 ruling it descends from: reissuing is not discarding.
        self.assertIn("2026-08-26", entry["self_candidate_ruling"])
        self.assertIn("2026-08-23", entry["self_candidate_ruling"])
        self.assertEqual(entry["permitted_routes"], ["mechanical_bulk"])
        policy = _json(HYBRID / "hybrid-dispatch.v1.json")
        self.assertTrue(validator.validate_manifest_hybrid(manifest, policy, Path("agentops.dispatch.json")))

    def test_validator_rejects_a_flip_without_a_ruling(self) -> None:
        policy = _json(HYBRID / "hybrid-dispatch.v1.json")
        manifest = _json(ROOT / "agentops.dispatch.json")
        manifest["routing"]["action_classes"]["mechanical_bulk"].pop("self_candidate_ruling")
        with self.assertRaisesRegex(ValueError, "without a self_candidate_ruling"):
            validator.validate_manifest_hybrid(manifest, policy, Path("m"))

    def test_validator_rejects_a_grant_that_names_no_routes(self) -> None:
        # Replaces the old "the class must BE a worker route" rule. A grant that
        # does not say which routes it covers is the inheritance-by-name defect
        # in a new spelling, so it is refused rather than defaulted.
        policy = _json(HYBRID / "hybrid-dispatch.v1.json")
        manifest = _json(ROOT / "agentops.dispatch.json")
        manifest["routing"]["action_classes"]["build"]["self_candidate"] = True
        with self.assertRaisesRegex(ValueError, "declares no permitted_routes"):
            validator.validate_manifest_hybrid(manifest, policy, Path("m"))

    def test_validator_rejects_a_grant_over_a_route_this_repo_does_not_run(self) -> None:
        policy = _json(HYBRID / "hybrid-dispatch.v1.json")
        manifest = _json(ROOT / "agentops.dispatch.json")
        manifest["routing"]["action_classes"]["build"].update(
            {"self_candidate": True, "self_candidate_ruling": "owner",
             "permitted_routes": ["bindery_external_runtime_w0"]})
        with self.assertRaisesRegex(ValueError, "not an enabled hybrid worker route"):
            validator.validate_manifest_hybrid(manifest, policy, Path("m"))

    def test_a_grant_does_not_cover_a_route_it_does_not_name(self) -> None:
        # The decoupling's whole point: authority is granted for named routes.
        # Same class, a route the ruling was not written about -> no authority.
        self.manifest["routing"]["action_classes"]["mechanical_bulk"][
            "permitted_routes"] = ["bindery_external_runtime_w0"]
        self.assertIsNone(dispatch.self_candidate_class(self.packet, self.manifest))


class RouteAndActionClassAreIndependentTests(unittest.TestCase):
    """agentops#2100 Option C: route selects execution, action_class carries
    authority, and neither implies the other.

    Both directions are pinned, because a decoupling that only works one way is
    still a welding. These operate on ``self_candidate_class`` directly: it is
    the single function in which the two concepts used to be the same string.
    """

    def setUp(self) -> None:
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
        packet_tests.setUp()
        self.packet = packet_tests.packet
        self.manifest = packet_tests.manifest

    def _classes(self, **classes) -> None:
        self.manifest["routing"] = {
            "default_harness": "opencode", "default_model_alias": "fast-build",
            "action_classes": classes,
        }

    def test_one_route_can_carry_different_action_classes(self) -> None:
        # Same execution binding, two packets, different authority.
        self._classes(
            trusted={"enabled": True, "self_candidate": True,
                     "self_candidate_ruling": "owner", "permitted_routes": ["mechanical_bulk"]},
            probationary={"enabled": True, "self_candidate": False,
                          "permitted_routes": ["mechanical_bulk"]},
        )
        trusted = dict(self.packet, schema_version="agentops-task/v3", action_class="trusted")
        probationary = dict(self.packet, schema_version="agentops-task/v3", action_class="probationary")
        self.assertEqual(trusted["route"], probationary["route"])
        self.assertEqual(dispatch.self_candidate_class(trusted, self.manifest), "trusted")
        self.assertIsNone(dispatch.self_candidate_class(probationary, self.manifest))

    def test_one_action_class_can_span_different_routes(self) -> None:
        # Same authority, two execution bindings. The grant names both.
        self._classes(
            mechanical={"enabled": True, "self_candidate": True,
                        "self_candidate_ruling": "owner",
                        "permitted_routes": ["mechanical_bulk", "bindery_external_runtime_w0"]},
        )
        here = dict(self.packet, schema_version="agentops-task/v3",
                    action_class="mechanical", route="mechanical_bulk")
        elsewhere = dict(self.packet, schema_version="agentops-task/v3",
                         action_class="mechanical", route="bindery_external_runtime_w0")
        self.assertNotEqual(here["route"], elsewhere["route"])
        self.assertEqual(dispatch.self_candidate_class(here, self.manifest), "mechanical")
        self.assertEqual(dispatch.self_candidate_class(elsewhere, self.manifest), "mechanical")

    def test_a_frozen_packet_falls_back_to_its_route_and_keeps_its_hash(self) -> None:
        # The compatibility half. A v2 packet has no action_class and must be
        # judged exactly as it was when frozen -- and its bytes must not move,
        # because packet_hash is what links it to its receipt.
        self._classes(mechanical_bulk={
            "enabled": True, "self_candidate": True, "self_candidate_ruling": "owner",
            "permitted_routes": ["mechanical_bulk"]})
        frozen = dict(self.packet, schema_version="agentops-task/v2")
        frozen.pop("action_class", None)
        before = json.dumps(frozen, sort_keys=True, separators=(",", ":"))
        self.assertEqual(dispatch.self_candidate_class(frozen, self.manifest), "mechanical_bulk")
        self.assertEqual(
            json.dumps(frozen, sort_keys=True, separators=(",", ":")), before,
            "resolving the class must not mutate the packet")

    def test_the_route_fallback_is_closed_at_v3(self) -> None:
        # Not an indefinite optional convention: a new packet must say which
        # class it is claiming, and omitting it is an error rather than a
        # silent inheritance.
        newer = dict(self.packet, schema_version="agentops-task/v3")
        newer.pop("action_class", None)
        with self.assertRaisesRegex(dispatch.PacketError, "must declare action_class"):
            dispatch.resolve_action_class(newer)
        for version in ("agentops-task/v1", "agentops-task/v2"):
            with self.subTest(version=version):
                older = dict(self.packet, schema_version=version)
                older.pop("action_class", None)
                self.assertEqual(dispatch.resolve_action_class(older), older["route"])

    def test_a_class_this_repository_does_not_declare_grants_nothing(self) -> None:
        # Six repositories opt into the mechanical_bulk ROUTE without declaring
        # a class of that name, and release_unit_packet stamps action_class
        # unconditionally. An undeclared class must therefore be "no grant" and
        # never an error, or release-unit dispatch breaks in all of them.
        self._classes(something_else={"enabled": True, "self_candidate": True,
                                      "self_candidate_ruling": "owner",
                                      "permitted_routes": ["mechanical_bulk"]})
        packet = dict(self.packet, schema_version="agentops-task/v3",
                      action_class="mechanical_bulk")
        self.assertIsNone(dispatch.self_candidate_class(packet, self.manifest))

    def test_a_repository_with_no_action_classes_at_all_still_dispatches(self) -> None:
        manifest = dict(self.manifest)
        manifest.pop("routing", None)
        packet = dict(self.packet, schema_version="agentops-task/v3",
                      action_class="mechanical_bulk")
        self.assertIsNone(dispatch.self_candidate_class(packet, manifest))

    def test_a_stated_class_beats_the_route_even_at_a_fallback_version(self) -> None:
        older = dict(self.packet, schema_version="agentops-task/v2", action_class="stated")
        self.assertEqual(dispatch.resolve_action_class(older), "stated")


class LiveClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
        packet_tests.setUp()
        self.packet = packet_tests.packet

    @staticmethod
    def _reservation(**overrides: object) -> dict:
        row = {
            "id": 7,
            "work_item_id": 42,
            "actor": "coordinator/claude-code",
            "state": "active",
            "last_activity_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        row.update(overrides)
        return row

    def _run(self, rows: list[dict], command: list[str] | None = None):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(rows), stderr="",
        )
        original = dispatch.subprocess.run

        def fake_run(args, *rest, **kwargs):
            if command is not None:
                command[:] = list(args)
            return completed

        dispatch.subprocess.run = fake_run
        try:
            return dispatch.verify_live_coordinator_claim(Path("."), self.packet, "sprintctl")
        finally:
            dispatch.subprocess.run = original

    def test_live_reservation_requires_exact_item_actor_and_recent_activity(self) -> None:
        evidence = self._run([self._reservation()])
        self.assertEqual(evidence["claim_id"], 7)
        self.assertEqual(evidence["work_item_id"], 42)
        self.assertLess(evidence["idle_seconds"], 60)

    def test_it_reads_reservations_because_sprintctl_has_no_claim_command(self) -> None:
        """sprintctl removed credential-bearing claims; calling `claim` fails on
        every host, and the old tests missed it by mocking the payload shape."""
        command: list[str] = []
        self._run([self._reservation()], command)
        self.assertEqual(command[1], "reservation")
        self.assertIn("--active-only", command)
        self.assertNotIn("claim", command)

    def test_live_reservation_rejects_a_different_actor(self) -> None:
        with self.assertRaisesRegex(dispatch.PacketError, "not held"):
            self._run([self._reservation(actor="someone-else")])

    def test_live_reservation_rejects_a_released_one(self) -> None:
        with self.assertRaisesRegex(dispatch.PacketError, "not active"):
            self._run([self._reservation(state="released")])

    def test_live_reservation_rejects_a_stale_one(self) -> None:
        """A reservation is a coordination signal, not a lease, so it has no
        expiry -- staleness is the only honest substitute for one."""
        stale = datetime.now(timezone.utc) - dispatch.reservation_stale_after() - timedelta(minutes=1)
        with self.assertRaisesRegex(dispatch.PacketError, "idle for"):
            self._run([self._reservation(last_activity_at=stale.strftime("%Y-%m-%dT%H:%M:%SZ"))])

    def test_a_fresh_reservation_just_inside_the_horizon_is_accepted(self) -> None:
        fresh = datetime.now(timezone.utc) - dispatch.reservation_stale_after() + timedelta(minutes=5)
        evidence = self._run([self._reservation(last_activity_at=fresh.strftime("%Y-%m-%dT%H:%M:%SZ"))])
        self.assertEqual(evidence["claim_id"], 7)

class ColdRunAssessmentTests(unittest.TestCase):
    """A packet whose oracle is a test written before the code was
    undispatchable: prepare demanded every gate green, and the packet existed
    precisely because one is red."""

    def setUp(self) -> None:
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
        packet_tests.setUp()
        self.packet = packet_tests.packet
        self.manifest = packet_tests.manifest
        self.policy = packet_tests.policy

    @staticmethod
    def _results(**exits: int) -> list[dict]:
        return [{"command_id": cid, "exit_code": code} for cid, code in exits.items()]

    def test_all_green_is_fit_when_nothing_is_declared_red(self) -> None:
        results, green, faults = dispatch.assess_cold_run(
            self._results(a=0, b=0), self.packet
        )
        self.assertTrue(green)
        self.assertEqual(faults, [])
        self.assertEqual([r["expectation"] for r in results], ["green", "green"])

    def test_an_unrelated_red_command_still_blocks_dispatch(self) -> None:
        _, green, faults = dispatch.assess_cold_run(self._results(a=0, b=1), self.packet)
        self.assertFalse(green)
        self.assertIn("b failed at the starting commit", faults[0])

    def test_a_declared_red_oracle_is_fit(self) -> None:
        self.packet["oracle"]["starts_red"] = ["b"]
        self.packet["allowed_command_ids"] = ["a", "b"]
        results, green, faults = dispatch.assess_cold_run(
            self._results(a=0, b=1), self.packet
        )
        self.assertTrue(green)
        self.assertEqual(faults, [])
        self.assertEqual(results[1]["expectation"], "red")

    def test_a_declared_red_oracle_that_passes_is_a_fault(self) -> None:
        """The resolution is stricter than the rule it replaces: a gate that
        cannot fail at the starting commit is not evidence of anything."""
        self.packet["oracle"]["starts_red"] = ["b"]
        self.packet["allowed_command_ids"] = ["a", "b"]
        _, green, faults = dispatch.assess_cold_run(self._results(a=0, b=0), self.packet)
        self.assertFalse(green)
        self.assertIn("cannot fail proves nothing", faults[0])

    def test_a_missing_command_is_a_fault_even_when_declared_red(self) -> None:
        """127 is "command not found", not a gate failing. Accepting it let a
        packet dispatch against an oracle its workspace did not contain, and the
        worker was judged by a test that never ran."""
        self.packet["oracle"]["starts_red"] = ["b"]
        self.packet["allowed_command_ids"] = ["a", "b"]
        _, green, faults = dispatch.assess_cold_run(self._results(a=0, b=127), self.packet)
        self.assertFalse(green)
        self.assertIn("does not exist there", faults[0])

    def test_starts_red_must_name_a_command_the_packet_may_run(self) -> None:
        self.packet["oracle"]["starts_red"] = ["not-granted"]
        with self.assertRaisesRegex(dispatch.PacketError, "cannot run"):
            dispatch.validate_packet(self.packet, self.manifest, self.policy)


class WorkspaceWritabilityTests(unittest.TestCase):
    """The check whose absence cost a whole run: a worker went straight for the
    right three files, was denied on every one, spent 1.07M tokens probing why,
    and hit its ceiling -- while prepare reported green and run exited 0."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name) / "ws"
        self.ws.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_worker_user_means_the_coordinator_writes(self) -> None:
        ok, detail = dispatch.worker_can_write_workspace(self.ws, None)
        self.assertTrue(ok)
        self.assertIn("coordinator", detail)

    def test_a_group_the_worker_is_not_in_is_reported_as_inert(self) -> None:
        """The exact failure: mode 775 looks correct and means nothing when the
        group is the coordinator's own."""
        original = dispatch.worker_shared_gid
        dispatch.worker_shared_gid = lambda user: 993
        try:
            os.chmod(self.ws, 0o775)
            ok, detail = dispatch.worker_can_write_workspace(self.ws, "agentworker")
        finally:
            dispatch.worker_shared_gid = original
        self.assertFalse(ok)
        self.assertIn("inert", detail)

    def test_a_workspace_without_group_write_is_refused(self) -> None:
        original = dispatch.worker_shared_gid
        dispatch.worker_shared_gid = lambda user: self.ws.lstat().st_gid
        try:
            os.chmod(self.ws, 0o755)
            ok, detail = dispatch.worker_can_write_workspace(self.ws, "agentworker")
        finally:
            dispatch.worker_shared_gid = original
        self.assertFalse(ok)
        self.assertIn("not group-writable", detail)

    def test_no_shared_group_at_all_is_refused(self) -> None:
        original = dispatch.worker_shared_gid
        dispatch.worker_shared_gid = lambda user: None
        try:
            ok, detail = dispatch.worker_can_write_workspace(self.ws, "agentworker")
        finally:
            dispatch.worker_shared_gid = original
        self.assertFalse(ok)
        self.assertIn("shares no group", detail)

    def test_a_probe_we_are_not_allowed_to_run_is_skipped_not_failed(self) -> None:
        """Lacking sudo rights to ask is not evidence that the answer is no;
        failing there would stop the run for a reason unrelated to the workspace."""
        original_gid, original_run = dispatch.worker_shared_gid, dispatch.subprocess.run
        dispatch.worker_shared_gid = lambda user: self.ws.lstat().st_gid
        dispatch.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="sudo: a password is required")
        try:
            os.chmod(self.ws, 0o775)
            ok, detail = dispatch.worker_can_write_workspace(self.ws, "agentworker")
        finally:
            dispatch.worker_shared_gid, dispatch.subprocess.run = original_gid, original_run
        self.assertTrue(ok)
        self.assertIn("not permitted", detail)

    def test_a_probe_that_ran_and_said_no_is_a_failure(self) -> None:
        original_gid, original_run = dispatch.worker_shared_gid, dispatch.subprocess.run
        dispatch.worker_shared_gid = lambda user: self.ws.lstat().st_gid
        dispatch.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="")
        try:
            os.chmod(self.ws, 0o775)
            ok, detail = dispatch.worker_can_write_workspace(self.ws, "agentworker")
        finally:
            dispatch.worker_shared_gid, dispatch.subprocess.run = original_gid, original_run
        self.assertFalse(ok)
        self.assertIn("despite correct group and mode", detail)

    def test_shared_gid_needs_a_real_user(self) -> None:
        self.assertIsNone(dispatch.worker_shared_gid(None))
        self.assertIsNone(dispatch.worker_shared_gid("no-such-user-here"))


class OracleAttainabilityTests(unittest.TestCase):
    """validate asked whether acceptance properties discriminate and never
    whether they can be met. Three of the five defects behind a seven-run packet
    were that gap."""

    def setUp(self) -> None:
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
        packet_tests.setUp()
        self.packet = packet_tests.packet
        self.manifest = packet_tests.manifest
        self.packet["oracle"]["starts_red"] = ["a"]
        self.packet["allowed_command_ids"] = ["a"]
        self.manifest["hybrid"]["commands"] = {"a": "true"}

    def _faults(self, returncode: int) -> list[str]:
        original_run, original_git = dispatch.subprocess.run, dispatch._git
        dispatch._git = lambda *a, **k: ""
        dispatch.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr="")
        try:
            return dispatch.check_oracle_attainable(Path("."), self.packet, self.manifest)
        finally:
            dispatch.subprocess.run, dispatch._git = original_run, original_git

    def test_a_red_oracle_is_attainable(self) -> None:
        self.assertEqual(self._faults(1), [])

    def test_an_absent_oracle_is_a_fault(self) -> None:
        """Defect 5: the test only existed on the branch tip, so the worker was
        judged by a gate that never ran."""
        faults = self._faults(127)
        self.assertTrue(faults)
        self.assertIn("does not exist in the workspace", faults[0])

    def test_an_already_passing_oracle_is_a_fault(self) -> None:
        faults = self._faults(0)
        self.assertTrue(faults)
        self.assertIn("cannot fail", faults[0])

    def test_an_unregistered_command_is_a_fault(self) -> None:
        self.manifest["hybrid"]["commands"] = {}
        self.assertIn("not a registered command", self._faults(1)[0])

    def test_a_packet_without_starts_red_is_not_checked(self) -> None:
        self.packet["oracle"].pop("starts_red")
        self.assertEqual(dispatch.check_oracle_attainable(Path("."), self.packet, self.manifest), [])


class OracleReadTraceTests(unittest.TestCase):
    """L-2(b), read-trace half: an oracle that reads a file the packet never
    declared demands an unstated seam, or covers work the packet does not hold."""

    FAKE_STRACE = """#!/bin/sh
# Fake strace: writes the canned trace named by FAKE_TRACE_SRC to the -o file.
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    --) shift; break ;;
    -f|-qq) shift ;;
    -e) shift 2 ;;
    *) break ;;
  esac
done
cp "$FAKE_TRACE_SRC" "$out"
exit 1
"""

    def setUp(self) -> None:
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
        packet_tests.setUp()
        self.packet = packet_tests.packet
        self.packet["oracle"]["starts_red"] = ["a"]
        self.packet["allowed_command_ids"] = ["a"]
        self.packet["readable_context_paths"] = ["src/**"]
        self.packet["writable_patch_paths"] = ["tests/**"]
        self.commands = {"a": "pytest -q tests/test_a.py"}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.checkout = Path(os.path.realpath(self.tmp.name)) / "checkout"
        for rel in ("tests/test_a.py", "src/a.py", "docs/secret.md", "pyproject.toml",
                    ".git/HEAD", "src/__pycache__/a.pyc"):
            (self.checkout / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.checkout / rel).write_text("x", encoding="utf-8")
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        self.strace = bin_dir / "strace"
        self.strace.write_text(self.FAKE_STRACE, encoding="utf-8")
        self.strace.chmod(0o755)

    def _trace(self, *paths: str, strace: str | None = "fake", allow_untraced: bool = False):
        lines = [f'123   openat(AT_FDCWD, "{self.checkout}/{p}", O_RDONLY|O_CLOEXEC) = 3' for p in paths]
        lines.append(f'123   openat(AT_FDCWD, "{self.checkout}/src", O_RDONLY|O_DIRECTORY) = 4')
        lines.append(f'123   openat(AT_FDCWD, "{self.checkout}/docs/missing.md", O_RDONLY) = -1 ENOENT (No such file)')
        lines.append(f'123   openat(AT_FDCWD, "{self.checkout}/docs/out.log", O_WRONLY|O_CREAT, 0666) = 5')
        lines.append('123   openat(AT_FDCWD, "/usr/lib/python3/os.py", O_RDONLY|O_CLOEXEC) = 6')
        src = Path(self.tmp.name) / "trace.src"
        src.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.environ["FAKE_TRACE_SRC"] = str(src)
        self.addCleanup(os.environ.pop, "FAKE_TRACE_SRC", None)
        strace_bin = str(self.strace) if strace == "fake" else strace
        return dispatch.trace_oracle_reads(
            self.checkout, self.packet, self.commands, strace_bin, allow_untraced,
        )

    def test_a_read_outside_declared_paths_is_rejected(self) -> None:
        faults, report = self._trace("docs/secret.md", "src/a.py")
        self.assertEqual(len(faults), 1)
        self.assertIn("oracle reads outside declared paths", faults[0])
        self.assertIn("docs/secret.md", faults[0])
        self.assertIs(report["oracle_reads_within_paths"], False)
        self.assertEqual(report["reads_outside_declared_paths"], {"a": ["docs/secret.md"]})

    def test_reads_inside_declared_paths_pass(self) -> None:
        faults, report = self._trace("src/a.py", "tests/test_a.py")
        self.assertEqual(faults, [])
        self.assertIs(report["oracle_reads_within_paths"], True)
        self.assertIs(report["read_trace"], True)

    def test_exempt_paths_and_non_reads_are_ignored(self) -> None:
        # The oracle's own file, VCS, bytecode, runner config, directories,
        # failed opens, write-only opens and paths outside the checkout.
        faults, report = self._trace(
            "tests/test_a.py", ".git/HEAD", "src/__pycache__/a.pyc", "pyproject.toml",
        )
        self.assertEqual(faults, [])
        self.assertIs(report["oracle_reads_within_paths"], True)

    def test_no_strace_and_no_flag_fails_closed(self) -> None:
        faults, report = self._trace("src/a.py", strace=None)
        self.assertEqual(len(faults), 1)
        self.assertIn("strace is not on PATH", faults[0])
        self.assertIn("--allow-untraced-oracle", faults[0])
        self.assertIsNone(report["oracle_reads_within_paths"])

    def test_no_strace_with_flag_is_skipped_never_true(self) -> None:
        faults, report = self._trace("docs/secret.md", strace=None, allow_untraced=True)
        self.assertEqual(faults, [])
        self.assertEqual(report["oracle_reads_within_paths"], "skipped:untraced")
        self.assertEqual(report["read_trace"], "skipped:untraced")
        self.assertIsNot(report["oracle_reads_within_paths"], True)

    def test_a_packet_without_starts_red_is_not_traced(self) -> None:
        self.packet["oracle"].pop("starts_red")
        faults, report = dispatch.trace_oracle_reads(self.checkout, self.packet, self.commands, None)
        self.assertEqual(faults, [])
        self.assertIsNone(report["oracle_reads_within_paths"])

    def test_exemptions_are_one_stated_constant(self) -> None:
        self.assertEqual(dispatch.ORACLE_READ_TRACE_EXEMPT_PREFIXES, (".git/", "__pycache__/", ".venv/"))

    def test_validate_passes_the_flag_through(self) -> None:
        original = (dispatch.check_oracle_reads, dispatch.check_oracle_attainable)
        seen: dict = {}

        def fake(repo_root, packet, manifest, allow_untraced=False):
            seen["allow"] = allow_untraced
            return [], {"oracle_reads_within_paths": "skipped:untraced", "read_trace": "skipped:untraced"}

        dispatch.check_oracle_reads = fake
        dispatch.check_oracle_attainable = lambda *a, **k: []
        try:
            with tempfile.TemporaryDirectory() as tmp:
                packet_path = Path(tmp) / "p.json"
                self.packet["oracle"]["starts_red"] = ["example.tests"]
                self.packet["allowed_command_ids"] = ["example.tests"]
                packet_path.write_text(json.dumps(self.packet), encoding="utf-8")
                manifest_path = Path(tmp) / "example.dispatch.json"
                manifest = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
                manifest.setUp()
                manifest_path.write_text(json.dumps(manifest.manifest), encoding="utf-8")
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = dispatch.main([
                        "--repo-root", tmp, "--packet", str(packet_path),
                        "--agentops-root", str(ROOT), "--allow-untraced-oracle", "validate",
                    ])
                self.assertEqual(code, 0, out.getvalue())
                self.assertTrue(seen["allow"])
                self.assertEqual(json.loads(out.getvalue())["oracle_reads_within_paths"], "skipped:untraced")
        finally:
            dispatch.check_oracle_reads, dispatch.check_oracle_attainable = original


class OracleReferenceOverlayTests(unittest.TestCase):
    """L-2(b), reference-overlay half: a change confined to writable_patch_paths
    must turn the starts_red oracle green, else the oracle demands an unstated
    seam (defect 3) or covers more than the packet holds (defect 4)."""

    def setUp(self) -> None:
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
        packet_tests.setUp()
        self.packet = packet_tests.packet
        self.packet["oracle"]["starts_red"] = ["a"]
        self.packet["allowed_command_ids"] = ["a"]
        self.packet["writable_patch_paths"] = ["src/**"]
        # Oracle: green only when src/a.txt says "solved" AND (for the over-broad
        # case) src/b.txt says "solved" too.
        self.commands = {"a": "grep -qx solved src/a.txt"}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(os.path.realpath(self.tmp.name)) / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "docs").mkdir()
        (self.repo / "src/a.txt").write_text("unsolved\n", encoding="utf-8")
        (self.repo / "docs/seam.txt").write_text("unsolved\n", encoding="utf-8")
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
        for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "start"]):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, env=env, capture_output=True)
        self.packet["starting_commit"] = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
        ).stdout.strip()

    def _patch(self, rel: str, new_text: str, name: str = "ref.patch") -> Path:
        old = (self.repo / rel).read_text(encoding="utf-8")
        text = (
            f"--- a/{rel}\n+++ b/{rel}\n@@ -1 +1 @@\n-{old.rstrip()}\n+{new_text}\n"
        )
        path = self.repo / "docs" / name
        path.write_text(text, encoding="utf-8")
        return path

    def _run(self, patch: Path | None):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "co"
            subprocess.run(["git", "clone", "-q", str(self.repo), str(checkout)], check=True, capture_output=True)
            return dispatch.overlay_reference_patch(checkout, self.packet, self.commands, patch)

    def test_a_reference_inside_writable_paths_that_goes_green_is_satisfiable(self) -> None:
        faults, report = self._run(self._patch("src/a.txt", "solved"))
        self.assertEqual(faults, [])
        self.assertIs(report["oracle_satisfiable_within_paths"], True)
        self.assertEqual(report["red_after_reference"], [])

    def test_a_reference_touching_outside_writable_paths_is_rejected(self) -> None:
        faults, report = self._run(self._patch("docs/seam.txt", "solved"))
        self.assertEqual(len(faults), 1)
        self.assertIn("outside writable_patch_paths", faults[0])
        self.assertIn("docs/seam.txt", faults[0])
        self.assertIs(report["oracle_satisfiable_within_paths"], False)

    def test_a_reference_that_applies_but_leaves_the_oracle_red_is_rejected_with_the_id(self) -> None:
        self.commands = {"a": "grep -qx solved src/a.txt && grep -qx solved docs/seam.txt"}
        faults, report = self._run(self._patch("src/a.txt", "solved"))
        self.assertEqual(len(faults), 1)
        self.assertIn("a is still red", faults[0])
        self.assertIs(report["oracle_satisfiable_within_paths"], False)
        self.assertEqual(report["red_after_reference"], ["a"])

    def test_no_reference_is_skipped_never_true(self) -> None:
        faults, report = self._run(None)
        self.assertEqual(faults, [])
        self.assertEqual(report["oracle_satisfiable_within_paths"], "skipped:no-reference")

    def test_a_reference_that_does_not_apply_is_rejected(self) -> None:
        (self.repo / "docs/bad.patch").write_text(
            "--- a/src/a.txt\n+++ b/src/a.txt\n@@ -1 +1 @@\n-nonsense\n+solved\n", encoding="utf-8")
        faults, report = self._run(self.repo / "docs/bad.patch")
        self.assertIn("does not apply", faults[0])
        self.assertIs(report["oracle_satisfiable_within_paths"], False)

    def test_validate_reports_skipped_and_warns_without_a_reference(self) -> None:
        original = (dispatch.check_oracle_reads, dispatch.check_oracle_attainable)
        dispatch.check_oracle_reads = lambda *a, **k: ([], {"oracle_reads_within_paths": "skipped:untraced", "read_trace": "skipped:untraced"})
        dispatch.check_oracle_attainable = lambda *a, **k: []
        try:
            with tempfile.TemporaryDirectory() as tmp:
                packet_path = Path(tmp) / "p.json"
                self.packet["oracle"]["starts_red"] = ["example.tests"]
                self.packet["allowed_command_ids"] = ["example.tests"]
                packet_path.write_text(json.dumps(self.packet), encoding="utf-8")
                manifest = PacketValidationTests("test_a_fit_packet_reports_only_the_gates_actually_observed")
                manifest.setUp()
                (Path(tmp) / "example.dispatch.json").write_text(json.dumps(manifest.manifest), encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = dispatch.main([
                        "--repo-root", tmp, "--packet", str(packet_path),
                        "--agentops-root", str(ROOT), "--allow-untraced-oracle", "validate",
                    ])
                self.assertEqual(code, 0, out.getvalue())
                self.assertEqual(json.loads(out.getvalue())["oracle_satisfiable_within_paths"], "skipped:no-reference")
                self.assertIn("no oracle.reference_patch", err.getvalue())
        finally:
            dispatch.check_oracle_reads, dispatch.check_oracle_attainable = original

    def test_reference_patch_must_stay_inside_the_repository(self) -> None:
        self.packet["oracle"]["reference_patch"] = "../outside.patch"
        with self.assertRaisesRegex(dispatch.PacketError, "inside the repository"):
            dispatch.resolve_reference_patch(self.repo, self.packet)

    def test_schema_admits_reference_patch(self) -> None:
        schema = _json(HYBRID / "task-packet.schema.json")
        self.assertIn("reference_patch", schema["properties"]["oracle"]["properties"])


# The `opencode export` worker-session path was removed deliberately (hand-pass
# item C, 2026-08-23): it produced truncated JSON on every session it ever ran
# on, and the transcript already survives in the run receipt under
# `worker.stdout`. Its replacement contract is pinned in
# test_hybrid_dispatch_handpass.py -- do not restore fixtures for the export.


class ChurnVerdictTests(unittest.TestCase):
    """context_churn was declared in every packet and enforced nowhere. A worker
    read 1.07M tokens without one completed write while its own limit of 8 sat
    unread."""

    LIMITS = {"max_reasoning_steps_without_mutation": 3, "max_repeated_reads_per_path": 2}

    @staticmethod
    def _tool(tool: str, status: str = "completed", path: str | None = None) -> dict:
        state: dict = {"status": status}
        if path:
            state["input"] = {"filePath": path}
        return {"type": "tool_use", "part": {"tool": tool, "state": state}}

    def test_progress_resets_the_counter(self) -> None:
        events = [self._tool("read", path="a"), self._tool("write"), self._tool("read", path="b")]
        self.assertIsNone(dispatch.churn_verdict(events, self.LIMITS))

    def test_mutation_free_churn_is_stopped(self) -> None:
        events = [self._tool("glob") for _ in range(4)]
        verdict = dispatch.churn_verdict(events, self.LIMITS)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict[0], "churn_no_mutation")

    def test_rereading_one_path_is_stopped(self) -> None:
        events = [self._tool("write")] + [self._tool("read", path="same") for _ in range(3)]
        verdict = dispatch.churn_verdict(events, self.LIMITS)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict[0], "churn_repeated_reads")

    def test_denied_writes_do_not_count_as_progress(self) -> None:
        """The exact 2026-08-23 failure: three denied edits look like work and
        are not, so they must not reset the no-progress counter."""
        events = [self._tool("write", status="error") for _ in range(3)]
        verdict = dispatch.churn_verdict(events, self.LIMITS)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict[0], "worker_cannot_write")

    def test_a_denied_write_run_is_named_separately_from_circling(self) -> None:
        """"The worker cannot write here" and "the worker is going in circles"
        are different facts and the operator needs to be told which."""
        denied = dispatch.churn_verdict([self._tool("edit", status="error")] * 3, self.LIMITS)
        circling = dispatch.churn_verdict([self._tool("glob")] * 4, self.LIMITS)
        self.assertNotEqual(denied[0], circling[0])

    def test_no_limits_means_no_verdict(self) -> None:
        self.assertIsNone(dispatch.churn_verdict([self._tool("glob")] * 20, {}))


class WorkerSpendTests(unittest.TestCase):
    """`limits.max_cost_usd` was declared everywhere and read by nothing.

    It becomes load-bearing when the worker's credential shares the
    coordinator's usage plan, which is the case on devbox: there is no
    provider-side cap separating them, so this is the only spend control.
    """

    def _stream(self, *steps: dict) -> str:
        return "\n".join(
            json.dumps({"type": "step_finish", "part": {"type": "step-finish", **s}})
            for s in steps
        )

    def test_costs_and_tokens_are_summed_across_steps(self) -> None:
        stream = self._stream(
            {"cost": 0.001, "tokens": {"total": 100}},
            {"cost": 0.002, "tokens": {"total": 250}},
        )
        spend = dispatch.worker_spend(stream, 2.0)
        self.assertAlmostEqual(spend["cost_usd"], 0.003)
        self.assertEqual(spend["tokens"], 350)
        self.assertTrue(spend["within_cap"])
        self.assertTrue(spend["cost_reported"])

    def test_exceeding_the_cap_is_reported(self) -> None:
        spend = dispatch.worker_spend(
            self._stream({"cost": 3.5, "tokens": {"total": 10}}), 2.0
        )
        self.assertFalse(spend["within_cap"])

    def test_token_process_ceilings_are_reported(self) -> None:
        spend = dispatch.worker_spend(
            self._stream({"cost": 0.01, "tokens": {"total": 750000}}),
            2.0,
            500000,
            1000000,
        )
        self.assertTrue(spend["soft_token_ceiling_exceeded"])
        self.assertTrue(spend["within_hard_token_ceiling"])
        hard = dispatch.worker_spend(
            self._stream({"cost": 0.01, "tokens": {"total": 1000001}}),
            2.0,
            500000,
            1000000,
        )
        self.assertFalse(hard["within_hard_token_ceiling"])

    def test_a_provider_reporting_no_cost_is_distinguished_from_free(self) -> None:
        # 0.0 alone would read as "this route is free" in a corpus, when it may
        # mean "this route did not say".
        spend = dispatch.worker_spend(self._stream({"tokens": {"total": 10}}), 2.0)
        self.assertEqual(spend["cost_usd"], 0.0)
        self.assertFalse(spend["cost_reported"])
        self.assertTrue(spend["within_cap"])

    def test_non_json_and_non_step_lines_are_ignored(self) -> None:
        stream = "\n".join(
            [
                "not json at all",
                json.dumps({"type": "text", "part": {"type": "text", "text": "hi"}}),
                self._stream({"cost": 0.5, "tokens": {"total": 7}}),
                "",
            ]
        )
        spend = dispatch.worker_spend(stream, 1.0)
        self.assertAlmostEqual(spend["cost_usd"], 0.5)
        self.assertEqual(spend["tokens"], 7)

    def test_no_cap_never_reports_an_overspend(self) -> None:
        spend = dispatch.worker_spend(
            self._stream({"cost": 99.0, "tokens": {"total": 1}}), None
        )
        self.assertTrue(spend["within_cap"])
        self.assertIsNone(spend["cap_usd"])


class ModelOverrideTests(unittest.TestCase):
    """A diagnostic model override must reach the agent, not just the root.

    Provider access follows the identity: a contained worker has its own auth
    store, so the route's model can be unreachable as the worker while being
    reachable as the coordinator. Measured on devbox 2026-07-28 -- the whole
    `opencode-go` provider was absent for `agentworker`.
    """

    def setUp(self) -> None:
        self.policy = _json(HYBRID / "hybrid-dispatch.v1.json")
        self.base = _json(HYBRID / "opencode.hybrid.json")
        self.manifest = _json(ROOT / "agentops.dispatch.json")
        self.packet = _json(HYBRID / "example-task-packet.json")
        self.packet["allowed_command_ids"] = []
        self.agent = self.policy["routes"][self.packet["route"]]["agent"]

    def test_override_applies_to_both_the_root_and_the_agent(self) -> None:
        overlay = dispatch.build_overlay(
            self.packet, self.manifest, self.policy, self.base, "opencode/some-free-model"
        )
        self.assertEqual(overlay["model"], "opencode/some-free-model")
        # The agent entry is what `--agent` selects, so a root-only override
        # would be silently ignored for the run that matters.
        self.assertEqual(
            overlay["agent"][self.agent]["model"], "opencode/some-free-model"
        )

    def test_without_an_override_the_route_model_is_unchanged(self) -> None:
        overlay = dispatch.build_overlay(
            self.packet, self.manifest, self.policy, self.base
        )
        expected = self.base["agent"][self.agent]["model"]
        self.assertEqual(overlay["model"], expected)
        self.assertEqual(overlay["agent"][self.agent]["model"], expected)

    def test_an_override_changes_the_overlay_hash(self) -> None:
        # The hash is what ties a receipt to the configuration that produced
        # it; an override that did not move it would let a diagnostic run and a
        # qualifying one be mistaken for each other.
        plain = dispatch.build_overlay(self.packet, self.manifest, self.policy, self.base)
        overridden = dispatch.build_overlay(
            self.packet, self.manifest, self.policy, self.base, "opencode/some-free-model"
        )
        self.assertNotEqual(
            dispatch.overlay_hash(plain), dispatch.overlay_hash(overridden)
        )


class WorkspaceSharingTests(unittest.TestCase):
    """The workspace must be writable by the worker, not only by its creator.

    A contained worker is in the workspace's group but never owns the clone the
    coordinator made for it. Without the group-write pass its first edit fails
    with EACCES inside its own workspace -- which is indistinguishable from
    containment working correctly, and was measured on devbox 2026-07-28.
    """

    def test_group_write_is_added_to_every_file_and_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            (workspace / "nested").mkdir(parents=True)
            clone_file = workspace / "nested" / "AGENTS.md"
            clone_file.write_text("x", encoding="utf-8")
            # What `git clone` leaves behind at the coordinator's 0022 umask.
            clone_file.chmod(0o644)
            (workspace / "nested").chmod(0o755)

            dispatch.share_workspace_with_group(workspace)

            for path in (workspace, workspace / "nested", clone_file):
                with self.subTest(path=path.name):
                    self.assertTrue(
                        stat.S_IMODE(path.stat().st_mode) & stat.S_IWGRP,
                        f"{path} is not group-writable; a contained worker could not edit it",
                    )

    def test_existing_permissions_are_widened_not_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            script = workspace / "run.sh"
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            script.chmod(0o755)

            dispatch.share_workspace_with_group(workspace)

            mode = stat.S_IMODE(script.stat().st_mode)
            self.assertTrue(mode & stat.S_IWGRP)
            # Nothing is granted to "other": the group is the boundary.
            self.assertFalse(mode & stat.S_IWOTH)
            self.assertTrue(mode & stat.S_IXUSR, "executable bits must survive")

    def test_symlinks_are_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            (workspace / "real").write_text("x", encoding="utf-8")
            (workspace / "link").symlink_to(workspace / "real")
            outside = Path(tmp) / "outside"
            outside.write_text("x", encoding="utf-8")
            outside.chmod(0o600)
            (workspace / "escape").symlink_to(outside)

            dispatch.share_workspace_with_group(workspace)

            # Following a symlink out of the workspace would widen a path the
            # workspace does not own.
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o600)


class ExamplePacketTests(unittest.TestCase):
    def test_example_packet_matches_the_frozen_field_set(self) -> None:
        example = _json(HYBRID / "example-task-packet.json")
        schema = _json(HYBRID / "task-packet.schema.json")
        for field in schema["required"]:
            with self.subTest(field=field):
                self.assertIn(field, example)
        self.assertEqual(example["schema_version"], "agentops-task/v2")
        self.assertEqual(
            [property_["id"] for property_ in example["acceptance_properties"]],
            ["REQ-001", "REQ-002"],
        )
        self.assertEqual(
            schema["properties"]["schema_version"]["enum"],
            ["agentops-task/v1", "agentops-task/v2", "agentops-task/v3"],
        )
        self.assertEqual(example["network_policy"], "disabled")


if __name__ == "__main__":
    unittest.main()
