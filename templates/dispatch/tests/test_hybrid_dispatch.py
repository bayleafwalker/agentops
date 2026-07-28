from __future__ import annotations

import importlib.util
import json
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

    def test_only_vuoro_bulk_is_a_named_pilot(self) -> None:
        qualification = self.policy["qualification"]
        self.assertEqual(qualification["mode"], "named_pilot")
        self.assertEqual(qualification["repositories"], ["vuoro"])
        self.assertEqual(qualification["routes"], ["bulk"])
        self.assertEqual(qualification["default"], "unqualified")
        self.assertEqual(self.policy["routes"]["bulk"]["status"], "available_named_pilot")
        for name, route in self.policy["routes"].items():
            if name != "bulk" and "status" in route:
                with self.subTest(route=name):
                    self.assertTrue(route["status"].endswith("unqualified"))

    def test_worker_is_denied_state_bearing_authority(self) -> None:
        denied = self.policy["worker"]["denied_authority"]
        for authority in ("git", "sprintctl", "kctl", "actionq", "acceptance or merge"):
            with self.subTest(authority=authority):
                self.assertIn(authority, denied)

    def test_sprint_state_and_acceptance_stay_outside_the_worker(self) -> None:
        self.assertEqual(self.policy["sprintctl_authority"], "coordinator_only")
        self.assertEqual(self.policy["acceptance_authority"], "human")

    def test_read_only_challenger_never_replaces_coordinator_review(self) -> None:
        challenger = self.policy["routes"]["worker_review_challenger"]
        self.assertIn("Never substitutes", challenger["purpose"])
        self.assertIn("coordinator-review-recorded", self.policy["gates"]["post"])

    def test_rejects_a_worker_config_that_pre_authorizes_bash(self) -> None:
        broken = json.loads(json.dumps(self.worker_config))
        broken["agent"]["ao-bulk"]["permission"]["webfetch"] = "allow"
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
                "worker_routes": ["bulk", "escalation"],
                "commands": {"example.tests": "pytest -q"},
                "protected_paths": ["src/authority/**"],
                "max_timeout_seconds": 1200,
                "max_cost_usd": 3.0,
            },
        }
        self.packet = {
            "schema_version": "agentops-task/v1",
            "task_id": "EX-1",
            "repo_id": "example",
            "sprint_item": {"ref": "example#42", "claim_id": 7, "claim_actor": "coordinator/claude-code"},
            "route": "bulk",
            "attempt": 1,
            "starting_commit": "a" * 40,
            "purpose": "p",
            "readable_context_paths": ["src/**"],
            "writable_patch_paths": ["tests/**"],
            "protected_paths": ["src/authority/**"],
            "required_outcomes": ["o"],
            "non_goals": ["n"],
            "allowed_command_ids": ["example.tests"],
            "limits": {"timeout_seconds": 600},
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
        pilot["repo_id"] = "vuoro"
        pilot["sprint_item"]["ref"] = "vuoro#42"
        self.assertEqual(dispatch.qualification_state(self.policy, pilot), "named_pilot:vuoro-bulk-2026-07-28")

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
        self.packet["route"] = "substantial"
        with self.assertRaisesRegex(dispatch.PacketError, "not enabled for this repository"):
            self._validate()

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
        self.assertEqual(bash["pytest -q"], "allow")
        self.assertEqual(bash["*"], "deny")

    def test_overlay_grants_edit_whole_and_defers_scope_to_the_gates(self) -> None:
        # OpenCode 1.18.5 withholds the edit tool outright when an `edit` map
        # denies "*", so per-path scoping here would only ever produce an empty
        # diff. writable_patch_paths stays enforced by the cold post-gates.
        overlay = self._overlay()
        self.assertEqual(overlay["permission"]["edit"], "allow")
        self.assertEqual(overlay["permission"]["external_directory"], "deny")

    def test_review_route_withholds_every_write_surface(self) -> None:
        self.packet["route"] = "worker_review_challenger"
        permission = self._overlay()["permission"]
        for key in ("edit", "write", "patch", "bash"):
            with self.subTest(key=key):
                self.assertEqual(permission[key], "deny")

    def test_overlay_keeps_network_and_subagents_denied(self) -> None:
        agent = self._overlay()["agent"]["ao-bulk"]["permission"]
        for key in ("task", "external_directory", "webfetch", "websearch"):
            with self.subTest(key=key):
                self.assertEqual(agent[key], "deny")

    def test_overlay_hash_is_stable_and_content_addressed(self) -> None:
        first = dispatch.overlay_hash(self._overlay())
        self.assertEqual(first, dispatch.overlay_hash(self._overlay()))
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

    def test_live_claim_requires_exact_item_actor_and_unexpired_lease(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps([{
                "claim_id": 7, "work_item_id": 42,
                "agent": "coordinator/claude-code",
                "expires_at": "2999-01-01T00:00:00Z",
            }]), stderr="",
        )
        original = dispatch.subprocess.run
        dispatch.subprocess.run = lambda *args, **kwargs: completed
        try:
            evidence = dispatch.verify_live_coordinator_claim(Path("."), self.packet, "sprintctl")
        finally:
            dispatch.subprocess.run = original
        self.assertEqual(evidence["claim_id"], 7)

    def test_live_claim_rejects_a_different_actor(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps([{
                "claim_id": 7, "work_item_id": 42,
                "agent": "someone-else", "expires_at": "2999-01-01T00:00:00Z",
            }]), stderr="",
        )
        original = dispatch.subprocess.run
        dispatch.subprocess.run = lambda *args, **kwargs: completed
        try:
            with self.assertRaisesRegex(dispatch.PacketError, "not held"):
                dispatch.verify_live_coordinator_claim(Path("."), self.packet, "sprintctl")
        finally:
            dispatch.subprocess.run = original

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
        self.assertEqual(example["schema_version"], "agentops-task/v1")
        self.assertEqual(example["network_policy"], "disabled")


if __name__ == "__main__":
    unittest.main()
