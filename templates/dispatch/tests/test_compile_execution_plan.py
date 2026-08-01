from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compile_execution_plan.py"
FIXTURES = ROOT / "execution-plan" / "fixtures"
SPEC = importlib.util.spec_from_file_location("compile_execution_plan", SCRIPT)
assert SPEC and SPEC.loader
compiler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compiler)


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


class CompileExecutionPlanTests(unittest.TestCase):
    def source(self):
        return fixture("source.json")

    def assert_invalid(self, value, pattern: str):
        with self.assertRaisesRegex(compiler.PlanError, pattern):
            compiler.compile_plan(value)

    def test_golden_compile_and_plan_ref(self):
        compiled = compiler.compile_plan(self.source())
        self.assertEqual(compiled, (FIXTURES / "compiled-plan.json").read_bytes().removesuffix(b"\n"))
        self.assertEqual(
            compiler.artifact_ref(compiled),
            "artifact:sha256:ba5d5547c1a8e71fe36c536eacb283298db825d97b996048a4b5be6153129862",
        )

    def test_input_key_order_and_whitespace_do_not_change_bytes(self):
        value = self.source()
        reordered = {key: value[key] for key in reversed(value)}
        self.assertEqual(compiler.compile_plan(value), compiler.compile_plan(reordered))

    def test_revision_and_commit_changes_change_digest_and_preserve_provenance(self):
        original = self.source()
        revision = copy.deepcopy(original)
        revision["entries"][2]["work"]["selected_revision"] = "item-edit:5:new"
        revision["entries"][2]["work"]["observed_revision"] = "item-edit:5:new"
        commit = copy.deepcopy(original)
        commit["repositories"][1]["commit"] = "3" * 40
        self.assertNotEqual(compiler.artifact_ref(compiler.compile_plan(original)), compiler.artifact_ref(compiler.compile_plan(revision)))
        self.assertNotEqual(compiler.artifact_ref(compiler.compile_plan(original)), compiler.artifact_ref(compiler.compile_plan(commit)))
        plan = json.loads(compiler.compile_plan(original))
        self.assertEqual(plan["entries"][2]["repository_id"], "actionq")
        self.assertEqual(plan["entries"][2]["work"], {"item_id": 2035, "revision": "item-edit:4:ccc"})
        self.assertEqual(plan["repositories"][1]["commit"], "2" * 40)

    def test_sprintctl_revision_drift_fails_before_output(self):
        value = self.source()
        value["entries"][0]["work"]["observed_revision"] = "item-edit:8:changed"
        self.assert_invalid(value, "revision drift")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            output = root / "plan.json"
            source.write_text(json.dumps(value))
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "compile", "--source", str(source), "--output", str(output)],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())

    def test_exact_actionq_group_and_envelope_keys(self):
        plan_bytes = compiler.compile_plan(self.source())
        plan = json.loads(plan_bytes)
        group = compiler.realize_group(plan, plan_bytes, fixture("bindings.json"))
        self.assertEqual(compiler.canonical_bytes(group), (FIXTURES / "execution-group.json").read_bytes().removesuffix(b"\n"))
        self.assertEqual(set(group), {"contract_id", "plan_ref", "max_parallel", "failure_policy", "members"})
        for member in group["members"]:
            self.assertEqual(set(member), {"action_id", "envelope"})
            self.assertEqual(set(member["envelope"]), {"contract_id", "action_id", "attempt_id", "source_commit", "command_id", "allowed_paths"})
            self.assertEqual(member["action_id"], member["envelope"]["action_id"])

    def test_realization_is_deterministic_and_binding_changes_do_not_change_plan_ref(self):
        plan_bytes = compiler.compile_plan(self.source())
        plan = json.loads(plan_bytes)
        bindings = fixture("bindings.json")
        first = compiler.canonical_bytes(compiler.realize_group(plan, plan_bytes, bindings))
        self.assertEqual(first, compiler.canonical_bytes(compiler.realize_group(plan, plan_bytes, bindings)))
        changed = copy.deepcopy(bindings)
        changed["bindings"][0]["action_id"] = 999
        second = compiler.realize_group(plan, plan_bytes, changed)
        self.assertNotEqual(first, compiler.canonical_bytes(second))
        self.assertEqual(second["plan_ref"], compiler.artifact_ref(plan_bytes))

    def test_stacked_plan_refuses_generic_group_without_output(self):
        source = self.source()
        source["entries"][2]["repository_id"] = "agentops"
        source["entries"][2]["topology"] = "stacked"
        source["entries"][2]["base_entry_id"] = "compiler-docs"
        plan_bytes = compiler.compile_plan(source)
        with self.assertRaisesRegex(compiler.PlanError, "predecessor candidate commit"):
            compiler.realize_group(json.loads(plan_bytes), plan_bytes, fixture("bindings.json"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); plan_path = root / "plan.json"; output = root / "group.json"
            plan_path.write_bytes(plan_bytes)
            result = subprocess.run([sys.executable, str(SCRIPT), "realize", "--plan", str(plan_path), "--bindings", str(FIXTURES / "bindings.json"), "--output", str(output)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())

    def test_integration_realization_exact_bindings_and_digests(self):
        plan_bytes = compiler.compile_plan(self.source()); plan = json.loads(plan_bytes)
        product = compiler.realize_integration(plan, plan_bytes, fixture("integration-results.json"))
        self.assertEqual(compiler.canonical_bytes(product), (FIXTURES / "integration-realization.json").read_bytes().removesuffix(b"\n"))
        self.assertEqual(set(product), {"contract_id", "input_refs", "integration_spec", "action_creation_request"})
        spec = product["integration_spec"]; request = product["action_creation_request"]
        self.assertEqual(set(spec), {"contract_id", "topology", "base_commit", "member_result_refs", "input_set_digest"})
        self.assertEqual(set(request), {"contract_id", "plan_ref", "topology", "role", "subject", "spec_ref", "spec_digest", "input_set_digest"})
        expected_input = {"contract_id": "immutable-input-set/v1", "inputs": product["input_refs"]}
        self.assertEqual(spec["input_set_digest"], "sha256:" + __import__("hashlib").sha256(compiler.canonical_bytes(expected_input)).hexdigest())
        self.assertEqual(request["spec_ref"], compiler.artifact_ref(compiler.canonical_bytes(spec)))
        self.assertEqual(request["spec_digest"], "sha256:" + request["spec_ref"].split(":")[-1])
        self.assertEqual(request["plan_ref"], compiler.artifact_ref(plan_bytes))

    def test_integration_results_require_exact_order_count_refs_and_no_leakage(self):
        plan_bytes = compiler.compile_plan(self.source()); plan = json.loads(plan_bytes)
        for mutate, pattern in (
            (lambda r: r["member_results"].reverse(), "exact compiled"),
            (lambda r: r["member_results"].pop(), "exact compiled"),
            (lambda r: r["member_results"][0].update(result_ref="mutable:main"), "artifact:sha256"),
            (lambda r: r.update(credential="x"), "forbidden|unknown fields"),
        ):
            results = fixture("integration-results.json"); mutate(results)
            with self.assertRaisesRegex(compiler.PlanError, pattern):
                compiler.realize_integration(plan, plan_bytes, results)

    def test_bindings_must_be_complete_ordered_and_unique(self):
        plan_bytes = compiler.compile_plan(self.source())
        plan = json.loads(plan_bytes)
        for mutate, pattern in (
            (lambda b: b["bindings"].reverse(), "exact compiled plan entry order"),
            (lambda b: b["bindings"].pop(), "complete"),
            (lambda b: b["bindings"][1].update(action_id=301), "unique"),
            (lambda b: b["bindings"][0].update(extra=True), "unknown fields"),
        ):
            bindings = fixture("bindings.json")
            mutate(bindings)
            with self.assertRaisesRegex(compiler.PlanError, pattern):
                compiler.realize_group(plan, plan_bytes, bindings)

    def test_unknown_fields_floats_and_secret_material_are_rejected(self):
        cases = []
        value = self.source(); value["extra"] = True; cases.append((value, "unknown fields"))
        value = self.source(); value["entries"][0]["work"]["extra"] = 1; cases.append((value, "unknown fields"))
        value = self.source(); value["execution"]["max_parallel"] = 1.5; cases.append((value, "float"))
        value = self.source(); value["claim_token"] = "abc"; cases.append((value, "forbidden"))
        value = self.source(); value["entries"][0]["acceptance_gates"] = ["password=abc"]; cases.append((value, "forbidden"))
        value = self.source(); value["entries"][0]["work"]["revision"] = "/tmp/private"; cases.append((value, "forbidden"))
        for value, pattern in cases:
            self.assert_invalid(value, pattern)

    def test_repository_urls_and_paths_fail_closed(self):
        value = self.source(); value["repositories"][0]["repository_url"] = "ssh://git@github.com/owner/repo.git"
        plan = json.loads(compiler.compile_plan(value))
        self.assertEqual(plan["repositories"][0]["repository_url"], "ssh://git@github.com/owner/repo.git")
        value = self.source(); value["repositories"][0]["repository_url"] = "https://github.com/root/repo.git"
        compiler.compile_plan(value)
        value = self.source(); value["repositories"][0]["repository_url"] = "https://github.com/home/repo.git"
        compiler.compile_plan(value)
        self.assertNotEqual(compiler._url_identity("https://github.com:444/owner/repo.git"), compiler._url_identity("https://github.com/owner/repo.git"))
        for url in (
            "http://github.com/o/r",
            "https://user@github.com/o/r",
            "ssh://git:@github.com/o/r.git",
            "https://github.com:bad/o/r.git",
            "https://github.com:99999/o/r.git",
            "https://[bad/o/r",
            "https://[::1/o/r",
            "ssh://git@[bad/o/r",
            "file:///tmp/r",
            "/tmp/r",
        ):
            value = self.source(); value["repositories"][0]["repository_url"] = url
            self.assert_invalid(value, "forbidden|credential-free|credentials|invalid port|malformed")
        for path in ("/absolute", "a/../b", "a/./b", "a/"):
            value = self.source(); value["entries"][0]["allowed_paths"] = [path]
            self.assert_invalid(value, "normalized, relative")
        value = self.source(); value["repositories"][0]["repository_url"] = "https://[::1]/owner/repo.git"
        self.assert_invalid(value, "IPv6")

    def test_topology_references_and_integrations_are_discriminating(self):
        value = self.source(); value["entries"][0]["id"] = value["entries"][1]["id"]
        self.assert_invalid(value, "duplicate entry")
        value = self.source(); value["entries"][1]["topology"] = "stacked"; value["entries"][1]["base_entry_id"] = "missing"
        self.assert_invalid(value, "earlier same-repository")
        value = self.source(); value["entries"][2]["base_entry_id"] = "compiler"
        self.assert_invalid(value, "only for stacked")
        value = self.source(); value["integrations"][0]["member_ids"] = ["compiler", "runner"]
        self.assert_invalid(value, "same-repository")
        value = self.source(); value["integrations"][0]["base_commit"] = "9" * 40
        self.assert_invalid(value, "must equal")
        value = self.source(); value["integrations"] = []
        self.assert_invalid(value, "exactly once")

    def test_set_like_arrays_must_be_sorted_unique_but_semantic_order_is_preserved(self):
        value = self.source(); value["entries"][0]["required_capabilities"] = ["z", "a"]
        self.assert_invalid(value, "sorted and unique")
        value = self.source(); value["entries"][0]["acceptance_gates"] = ["a", "a"]
        self.assert_invalid(value, "unique")
        value = self.source(); value["integrations"][0]["member_ids"].reverse()
        plan = json.loads(compiler.compile_plan(value))
        self.assertEqual(plan["integrations"][0]["member_ids"], ["compiler-docs", "compiler"])

    def test_failure_policy_and_parallel_bounds_match_actionq(self):
        value = self.source(); value["execution"]["failure_policy"] = "stop-new-claims"
        self.assert_invalid(value, "continue-independent")
        value = self.source(); value["execution"]["max_parallel"] = 33
        self.assert_invalid(value, "<= 32")

    def test_cli_compile_check_drift_missing_and_invalid(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); output = root / "plan.json"
            compile_result = subprocess.run([sys.executable, str(SCRIPT), "compile", "--source", str(FIXTURES / "source.json"), "--output", str(output)], text=True, capture_output=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            self.assertEqual(json.loads(compile_result.stdout)["status"], "written")
            exact = subprocess.run([sys.executable, str(SCRIPT), "check", "--source", str(FIXTURES / "source.json"), "--output", str(output)], text=True, capture_output=True)
            self.assertEqual(exact.returncode, 0)
            output.write_text("{}")
            drift = subprocess.run([sys.executable, str(SCRIPT), "check", "--source", str(FIXTURES / "source.json"), "--output", str(output)], text=True, capture_output=True)
            self.assertEqual(drift.returncode, 1); self.assertEqual(json.loads(drift.stdout)["status"], "drift")
            output.unlink()
            missing = subprocess.run([sys.executable, str(SCRIPT), "check", "--source", str(FIXTURES / "source.json"), "--output", str(output)], text=True, capture_output=True)
            self.assertEqual(missing.returncode, 1); self.assertEqual(json.loads(missing.stdout)["status"], "missing")
            bad = root / "bad.json"; bad.write_text("[]")
            invalid = subprocess.run([sys.executable, str(SCRIPT), "compile", "--source", str(bad), "--output", str(output)], text=True, capture_output=True)
            self.assertEqual(invalid.returncode, 2); self.assertEqual(json.loads(invalid.stdout)["status"], "invalid")

    def test_optional_local_git_check_accepts_exact_source_and_rejects_stale_or_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"; repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
            (repo / "README").write_text("one\n")
            subprocess.run(["git", "-C", str(repo), "add", "README"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "one"], check=True)
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "git@github.com:owner/repo.git"], check=True)
            head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
            source = self.source(); source["repositories"] = [{"repository_id": "repo", "repository_url": "git@github.com:owner/repo.git", "commit": head}]
            source["entries"] = [{**source["entries"][2], "repository_id": "repo"}]; source["integrations"] = []; source["execution"]["max_parallel"] = 1
            plan = json.loads(compiler.compile_plan(source))
            compiler.check_repositories(plan, {"repo": repo})
            stale = copy.deepcopy(plan); stale["repositories"][0]["commit"] = "f" * 40
            with self.assertRaisesRegex(compiler.PlanError, "HEAD mismatch"):
                compiler.check_repositories(stale, {"repo": repo})
            with self.assertRaisesRegex(compiler.PlanError, "Git source check failed"):
                compiler.check_repositories(plan, {"repo": repo / "missing"})

    def test_compiled_plan_must_be_canonical_and_revalidated_before_realization(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(json.loads(compiler.compile_plan(self.source())), indent=2))
            with self.assertRaisesRegex(compiler.PlanError, "not canonical"):
                compiler.load_plan(path)
            bad = json.loads(compiler.compile_plan(self.source())); bad["extra"] = True
            path.write_bytes(compiler.canonical_bytes(bad))
            with self.assertRaisesRegex(compiler.PlanError, "unknown fields"):
                compiler.load_plan(path)
            path.write_bytes(compiler.canonical_bytes({"contract_id": "dispatch-plan/v1", "entries": [None]}))
            with self.assertRaisesRegex(compiler.PlanError, "malformed|unknown fields|missing fields"):
                compiler.load_plan(path)

    def test_cli_malformed_plan_is_invalid_without_traceback_or_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); plan = root / "plan.json"; output = root / "group.json"
            plan.write_bytes(compiler.canonical_bytes({"contract_id": "dispatch-plan/v1", "entries": [None]}))
            result = subprocess.run([sys.executable, str(SCRIPT), "realize", "--plan", str(plan), "--bindings", str(FIXTURES / "bindings.json"), "--output", str(output)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr + result.stdout)
            self.assertFalse(output.exists())

    def test_cli_argument_and_url_errors_use_json_invalid_envelope(self):
        for arguments in (["compile"], ["not-a-command"]):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), *arguments], text=True, capture_output=True
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "invalid")
            self.assertEqual(result.stderr, "")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source()
            source["repositories"][0]["repository_url"] = "https://github.com:bad/o/r.git"
            source_path = root / "source.json"
            source_path.write_text(json.dumps(source))
            output = root / "plan.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "compile", "--source", str(source_path), "--output", str(output)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "invalid")
            self.assertEqual(result.stderr, "")
            self.assertFalse(output.exists())

    def test_dependency_free_schema_and_fixture_key_parity(self):
        for path in (ROOT / "execution-plan").glob("*.schema.json"):
            schema = json.loads(path.read_text())
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        results = fixture("integration-results.json")
        self.assertEqual(set(results), {"contract_id", "integration_id", "member_results"})
        for member in results["member_results"]:
            self.assertEqual(set(member), {"entry_id", "result_ref"})


if __name__ == "__main__":
    unittest.main()
