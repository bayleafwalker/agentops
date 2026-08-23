from __future__ import annotations

import importlib.util
import hashlib
import json
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

    def test_a_fit_packet_reports_the_policy_pre_gates(self) -> None:
        self.assertEqual(self._validate(), self.policy["gates"]["pre"])

    def test_only_the_named_scope_is_labelled_as_pilot(self) -> None:
        self.assertEqual(dispatch.qualification_state(self.policy, self.packet), "unqualified")
        pilot = json.loads(json.dumps(self.packet))
        pilot["repo_id"] = "1deb57d0-af6f-479c-811a-b5b7254841f9"
        pilot["sprint_item"]["ref"] = "1deb57d0-af6f-479c-811a-b5b7254841f9#42"
        self.assertEqual(dispatch.qualification_state(self.policy, pilot), "named_pilot:vuoro-tooling-bulk-2026-07-28")

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
            dispatch.validate_packet(legacy, self.manifest, self.policy),
            self.policy["gates"]["pre"],
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
        self.packet["attempt"] = 3
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
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_the_policy_pre_gates")
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
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_the_policy_pre_gates")
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


class LiveClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_the_policy_pre_gates")
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
        packet_tests = PacketValidationTests("test_a_fit_packet_reports_the_policy_pre_gates")
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

    def test_starts_red_must_name_a_command_the_packet_may_run(self) -> None:
        self.packet["oracle"]["starts_red"] = ["not-granted"]
        with self.assertRaisesRegex(dispatch.PacketError, "cannot run"):
            dispatch.validate_packet(self.packet, self.manifest, self.policy)


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
            ["agentops-task/v1", "agentops-task/v2"],
        )
        self.assertEqual(example["network_policy"], "disabled")


if __name__ == "__main__":
    unittest.main()
