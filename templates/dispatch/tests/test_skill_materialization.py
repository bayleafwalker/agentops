"""A selected skill must be locked, undrifted, and materialized where a session loads it.

``4d2aade`` added ``escalation-gate`` to the ``allowed`` enum in
``manifest.schema.json`` and stopped there. It was never added to
``skills.selected``, never given a ``skill_lock`` digest, and never materialized,
so the half of that commit carrying the *method* was a file on disk that nothing
loaded. Only its companion check ran.

Measuring that gap turned up two older instances of the same shape:

* ``dispatch-wave`` and ``session-handover`` were selected with no
  ``.claude/skills`` symlink at all -- declared, never materialized;
* the ``dispatch-build`` and ``item-done`` digests had been stale since
  ``5790fc2`` edited their ``SKILL.md``. ``instruction_doctor`` collected
  ``skill_lock`` and reported it and never compared it with anything, and
  reporting a digest is not checking it.

So this suite pins the whole chain -- declared, locked, undrifted, materialized --
and pins it in both directions. A check that cannot fail is decoration.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"
SKILLS = ROOT / "templates/dispatch/skills"
MANIFEST = ROOT / "agentops.dispatch.json"
SCHEMA = ROOT / "templates/dispatch/manifest.schema.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


doctor = _load("instruction_doctor_subject", SCRIPTS / "instruction_doctor.py")


def _digest(name: str) -> str:
    return hashlib.sha256((SKILLS / name / "SKILL.md").read_bytes()).hexdigest()


class TheRepositoryChainIsIntact(unittest.TestCase):
    """declared -> selected -> locked -> undrifted -> materialized."""

    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.selected = self.manifest["skills"]["selected"]
        self.lock = self.manifest["instruction_set"]["skill_lock"]

    def test_every_selected_skill_is_in_the_schema_enum(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        allowed = set(
            schema["properties"]["skills"]["properties"]["selected"]["items"]["enum"]
        )
        self.assertEqual([], sorted(set(self.selected) - allowed))

    def test_every_selected_skill_is_locked(self) -> None:
        self.assertEqual([], sorted(set(self.selected) - set(self.lock)))

    def test_no_lock_entry_is_orphaned(self) -> None:
        self.assertEqual([], sorted(set(self.lock) - set(self.selected)))

    def test_every_locked_digest_matches_its_skill(self) -> None:
        """The direction that was silently false from 5790fc2 until 2026-08-26."""
        stale = {
            name: recorded
            for name, recorded in self.lock.items()
            if _digest(name) != recorded
        }
        self.assertEqual({}, stale)

    def test_every_selected_skill_is_materialized(self) -> None:
        missing = [
            name for name in self.selected
            if not (ROOT / ".claude" / "skills" / name).exists()
        ]
        self.assertEqual([], missing)

    def test_escalation_gate_specifically(self) -> None:
        """The skill 4d2aade landed and never wired. Named, so it stays wired."""
        self.assertIn("escalation-gate", self.selected)
        self.assertIn("escalation-gate", self.lock)
        link = ROOT / ".claude" / "skills" / "escalation-gate"
        self.assertTrue(link.exists(), "escalation-gate is not materialized")
        self.assertEqual(
            (link / "SKILL.md").read_bytes(),
            (SKILLS / "escalation-gate" / "SKILL.md").read_bytes(),
            "the materialized escalation-gate is not the canonical one",
        )

    def test_the_doctor_reports_the_live_repository_clean(self) -> None:
        report = doctor.inspect(ROOT, ROOT)
        self.assertEqual([], [
            f for f in report["findings"] if f["code"].startswith("skill-")
        ])


class TheDoctorCheckCanFail(unittest.TestCase):
    """Each broken link in the chain must produce its own finding."""

    def _root(self, *, lock: dict[str, str], materialize: bool) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        skills = root / "templates" / "dispatch" / "skills"
        (skills / "probe").mkdir(parents=True)
        (skills / "probe" / "SKILL.md").write_text("# probe\n", encoding="utf-8")
        if materialize:
            link = root / ".claude" / "skills"
            link.mkdir(parents=True)
            (link / "probe").symlink_to(skills / "probe")
        (root / "AGENTS.md").write_text("probe\n", encoding="utf-8")
        (root / "probe.dispatch.json").write_text(json.dumps({
            "schema_version": 2,
            "repo_id": "probe",
            "adoption_level": "guidance-only",
            "routing": {
                "default_harness": "codex",
                "default_model_alias": "fast-build",
                "action_classes": {"plan": {"enabled": True}},
            },
            "skills": {"selected": ["probe"]},
            "verification": {"command_families": ["unit"]},
            "hooks": {"level": "none", "publishers": []},
            "instruction_set": {
                "schema_version": 1,
                "discovery": "native",
                "sources": [],
                "skill_lock": lock,
            },
        }), encoding="utf-8")
        return root

    def _codes(self, root: Path) -> list[str]:
        return [f["code"] for f in doctor.inspect(root, root)["findings"]]

    def test_a_stale_digest_is_caught(self) -> None:
        root = self._root(lock={"probe": "00" * 32}, materialize=True)
        self.assertIn("skill-digest-stale", self._codes(root))

    def test_an_unlocked_skill_is_caught(self) -> None:
        root = self._root(lock={}, materialize=True)
        self.assertIn("skill-unlocked", self._codes(root))

    def test_an_unmaterialized_skill_is_caught(self) -> None:
        digest = hashlib.sha256(b"# probe\n").hexdigest()
        root = self._root(lock={"probe": digest}, materialize=False)
        self.assertIn("skill-not-materialized", self._codes(root))

    def test_an_intact_chain_is_left_alone(self) -> None:
        digest = hashlib.sha256(b"# probe\n").hexdigest()
        root = self._root(lock={"probe": digest}, materialize=True)
        self.assertEqual(
            [], [c for c in self._codes(root) if c.startswith("skill-")])

    def test_a_broken_chain_blocks_managed_eligibility(self) -> None:
        """Fail closed: a degraded skill binding is not merely reported."""
        root = self._root(lock={"probe": "00" * 32}, materialize=True)
        self.assertFalse(doctor.inspect(root, root)["managed_eligible"])


if __name__ == "__main__":
    unittest.main()
