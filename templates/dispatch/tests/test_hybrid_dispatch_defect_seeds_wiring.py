"""Coordinator hand-pass oracle: defect seeds are wired into validate.

`defect_seeds.py` (#121) decides what a seed declaration means. This file pins
that `validate` actually runs seeds, and that the two failure directions are
distinguishable:

* a seed that turns the oracle red is doing its job;
* a seed that leaves the oracle green makes the packet UNFIT, because the
  oracle does not detect the defect the packet claims it detects.

The schema seam matters as much as the code: `oracle` is
`additionalProperties: false`, so an unaccepted `defect_seeds` field is not a
lenient packet -- it is a packet that cannot be frozen at all.

Rule 11: the subject is `hybrid_dispatch.py` and the protected schema it reads.
The git in here is the function under test's own -- `check_defect_seeds` clones
a throwaway checkout by definition -- run against a repository this test builds
in a temporary directory, never the real one.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"
HYBRID = ROOT / "templates/dispatch/hybrid"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dispatch = _load_module("hybrid_dispatch_seed_wiring_subject", SCRIPTS / "hybrid_dispatch.py")

GATE = "subject.tests"


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.oracle = json.loads((HYBRID / "task-packet.schema.json").read_text())[
            "properties"
        ]["oracle"]

    def test_the_schema_accepts_defect_seeds(self):
        # additionalProperties is false on oracle, so without this a packet
        # declaring a seed could not be frozen at all.
        self.assertIn("defect_seeds", self.oracle["properties"])

    def test_seeds_are_optional(self):
        self.assertNotIn("defect_seeds", self.oracle["required"])

    def test_a_seed_must_declare_id_patch_and_expect_red(self):
        item = self.oracle["properties"]["defect_seeds"]["items"]
        self.assertEqual(set(item["required"]), {"id", "patch", "expect_red"})
        self.assertFalse(item["additionalProperties"])

    def test_expect_red_must_not_be_empty(self):
        item = self.oracle["properties"]["defect_seeds"]["items"]
        self.assertEqual(item["properties"]["expect_red"]["minItems"], 1)


class CheckDefectSeedsTests(unittest.TestCase):
    """End to end over a repository built here: reference green, seed red."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        (self.repo / "docs").mkdir(parents=True)
        self._git("init", "--quiet", ".")
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")

        # A subject that does not exist yet, and a test that requires it to
        # double. This is the shape of every freeze: red for absence.
        (self.repo / "subject_test.py").write_text(
            textwrap.dedent(
                """
                import subject
                assert subject.double(2) == 4, "double is wrong"
                """
            ).lstrip()
        )
        self._git("add", "-A")
        self._git("commit", "--quiet", "-m", "freeze")
        self.starting_commit = self._git("rev-parse", "HEAD").strip()

        (self.repo / "docs" / "reference.patch").write_text(
            self._patch("subject.py", "def double(n):\n    return n * 2\n")
        )
        # A seed MODIFIES what the reference produced -- it is applied on top
        # of it, not instead of it.
        (self.repo / "docs" / "seed.patch").write_text(
            textwrap.dedent(
                """
                diff --git a/subject.py b/subject.py
                --- a/subject.py
                +++ b/subject.py
                @@ -1,2 +1,2 @@
                 def double(n):
                -    return n * 2
                +    return n * 3
                """
            ).lstrip()
        )
        # A cosmetic change the oracle cannot notice: the control that proves
        # "did not falsify" is reachable.
        (self.repo / "docs" / "noop.patch").write_text(
            textwrap.dedent(
                """
                diff --git a/subject.py b/subject.py
                --- a/subject.py
                +++ b/subject.py
                @@ -1,2 +1,3 @@
                +# cosmetic
                 def double(n):
                     return n * 2
                """
            ).lstrip()
        )
        self._git("add", "-A")
        self._git("commit", "--quiet", "-m", "patches")

        self.manifest = {"hybrid": {"commands": {GATE: f"{sys.executable} subject_test.py"}}}

    def _git(self, *args) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.repo, capture_output=True, text=True, check=True
        ).stdout

    @staticmethod
    def _patch(path: str, body: str) -> str:
        lines = body.splitlines()
        return (
            f"diff --git a/{path} b/{path}\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            f"+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n"
            + "".join(f"+{line}\n" for line in lines)
        )

    def _packet(self, seeds, reference="docs/reference.patch"):
        oracle = {
            "ownership": "externally_defined",
            "worker_may_modify": False,
            "description": "d",
            "starts_red": [GATE],
        }
        if reference is not None:
            oracle["reference_patch"] = reference
        if seeds is not None:
            oracle["defect_seeds"] = seeds
        return {
            "task_id": "T",
            "oracle": oracle,
            "starting_commit": self.starting_commit,
            "limits": {"timeout_seconds": 120},
        }

    def _seed(self, seed_id="wrong-factor", patch="docs/seed.patch"):
        return {"id": seed_id, "patch": patch, "expect_red": [GATE]}

    def test_a_packet_with_no_seeds_is_skipped_not_failed(self):
        faults, report = dispatch.check_defect_seeds(self.repo, self._packet(None), self.manifest)
        self.assertEqual(faults, [])
        self.assertEqual(report["defect_seeds_falsified"], "skipped:none")

    def test_a_seed_that_breaks_the_oracle_falsifies(self):
        faults, report = dispatch.check_defect_seeds(
            self.repo, self._packet([self._seed()]), self.manifest
        )
        self.assertEqual(faults, [])
        self.assertIs(report["defect_seeds_falsified"], True)
        self.assertEqual(report["unfalsified_seeds"], [])

    def test_a_seed_that_leaves_the_oracle_green_is_a_fault(self):
        # THE case: the seed is the reference itself, so the oracle passes and
        # the seed has proven nothing.
        faults, report = dispatch.check_defect_seeds(
            self.repo,
            self._packet([self._seed(patch="docs/noop.patch")]),
            self.manifest,
        )
        self.assertIs(report["defect_seeds_falsified"], False)
        self.assertEqual(report["unfalsified_seeds"], ["wrong-factor"])
        self.assertTrue(any("did not falsify" in f for f in faults))

    def test_seeds_require_a_reference_patch(self):
        # Applied to the bare starting commit a seed would be red for the
        # absence starts_red already proves, so it would prove nothing.
        faults, report = dispatch.check_defect_seeds(
            self.repo, self._packet([self._seed()], reference=None), self.manifest
        )
        self.assertIs(report["defect_seeds_falsified"], False)
        self.assertTrue(any("requires oracle.reference_patch" in f for f in faults))

    def test_a_missing_seed_patch_is_a_fault_naming_the_seed(self):
        faults, _ = dispatch.check_defect_seeds(
            self.repo, self._packet([self._seed(patch="docs/absent.patch")]), self.manifest
        )
        self.assertTrue(any("wrong-factor" in f for f in faults))

    def test_an_unusable_declaration_is_reported_not_raised(self):
        seed = self._seed()
        del seed["expect_red"]
        faults, report = dispatch.check_defect_seeds(
            self.repo, self._packet([seed]), self.manifest
        )
        self.assertIs(report["defect_seeds_falsified"], False)
        self.assertTrue(any("unusable" in f for f in faults))

    def test_the_real_repository_is_never_touched(self):
        before = (self.repo / "subject_test.py").read_text()
        dispatch.check_defect_seeds(self.repo, self._packet([self._seed()]), self.manifest)
        self.assertFalse((self.repo / "subject.py").exists())
        self.assertEqual((self.repo / "subject_test.py").read_text(), before)


if __name__ == "__main__":
    unittest.main()
