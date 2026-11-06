"""skill_boundary: deterministic inventory; changed or unverified content never inherits a grant."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "skill_boundary.py"
_spec = importlib.util.spec_from_file_location("skill_boundary", SCRIPT)
sb = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["skill_boundary"] = sb
_spec.loader.exec_module(sb)

EVIDENCE = (HERE.parents[1] / "docs" / "plans" / "agentops" / "evidence"
            / "2026-11-06-ao-k04-workflow-artifact-capture-inventory.json")

SKILL_MD = """---
name: demo
description: Demo skill for boundary tests.
---

Run `scripts/demo_tool.py` and read docs/demo-guide.md before writing to
`_artifacts/<repo>/out.json`. See [notes](references/notes.md).
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


class Repo:
    """A throwaway git repository holding one skill and its referenced files."""

    def __init__(self, tmp: Path, *, git: bool = True, origin: str | None = "https://example.invalid/demo.git"):
        self.root = tmp / "repo"
        self.skill = self.root / "skills" / "demo"
        (self.skill / "references").mkdir(parents=True)
        (self.skill / "agents").mkdir()
        (self.root / "scripts").mkdir()
        (self.root / "docs").mkdir()
        (self.root / ".claude" / "skills").mkdir(parents=True)
        self.write("skills/demo/SKILL.md", SKILL_MD)
        self.write("skills/demo/references/notes.md", "notes\n")
        self.write("skills/demo/agents/openai.yaml", "interface:\n  display_name: Demo\n")
        self.write("scripts/demo_tool.py", "print('demo')\n")
        self.write("docs/demo-guide.md", "guide\n")
        os.symlink("../../skills/demo", self.root / ".claude" / "skills" / "demo")
        self.git = git
        if git:
            _git(self.root, "init", "-q")
            if origin:
                _git(self.root, "remote", "add", "origin", origin)
            self.commit()

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self) -> None:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--allow-empty", "-m", "snapshot")

    def inventory(self) -> dict:
        return sb.inventory(self.skill, repo_root=self.root)


def _grant(inventory: dict, **extra) -> dict:
    return {"schema_version": sb.GRANT_SCHEMA, "host_policy_ref": "host-policy:demo",
            "host_policy_revision": "r1", "granted_by": "owner:test",
            "accepted_dynamic_references": ["_artifacts/<repo>/out.json"],
            "inventory": copy.deepcopy(inventory), **extra}


class SkillBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = Repo(self.tmp)
        self.base = self.repo.inventory()
        self.grant = _grant(self.base)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def codes(self, current: dict, grant: dict | None = None, *, keep_revision: bool = False) -> set[str]:
        """Denial codes; by default omits the revision code that every new test commit adds."""
        result = sb.compare(grant or self.grant, current)
        self.assertEqual(result["inherit"], not result["reasons"])
        codes = {r["code"] for r in result["reasons"]}
        return codes if keep_revision else codes - {"revision-changed-with-external-dependencies"}

    # -- inventory content and stability ------------------------------------------------

    def test_inventory_records_source_digests_dependencies_and_load_path(self):
        inv = self.base
        self.assertEqual(inv["qualification_status"], "source-observed-not-qualified")
        self.assertEqual(inv["skill"], {"name": "demo", "directory": "skills/demo"})
        self.assertEqual(inv["source"]["origin"], "https://example.invalid/demo.git")
        self.assertEqual(inv["source"]["tree_state"], "clean")
        self.assertEqual(len(inv["source"]["revision"]), 40)
        self.assertEqual([f["path"] for f in inv["files"]],
                         ["SKILL.md", "agents/openai.yaml", "references/notes.md"])
        self.assertEqual(inv["adapter_files"], ["agents/openai.yaml"])
        deps = {d["reference"]: d["status"] for d in inv["dependencies"]}
        self.assertEqual(deps, {
            "scripts/demo_tool.py": "observed", "docs/demo-guide.md": "observed",
            "_artifacts/<repo>/out.json": "dynamic", "references/notes.md": "within-skill-tree",
        })
        self.assertEqual(inv["load_paths"], [{
            "path": ".claude/skills/demo", "kind": "symlink", "target": "../../skills/demo",
            "resolves_to_skill": True, "observation": "source-link-only"}])
        self.assertEqual(set(inv["provider_load_coverage"].values()), {"unknown"})
        self.assertEqual(inv["provenance"]["trust_class"], "unknown")

    def test_digest_stability_across_runs_and_mtimes(self):
        os.utime(self.repo.skill / "SKILL.md", (1, 1))
        again = self.repo.inventory()
        self.assertEqual(again, self.base)
        out1, out2 = io.StringIO(), io.StringIO()
        with redirect_stdout(out1):
            self.assertEqual(sb.main(["inventory", str(self.repo.skill), "--repo-root", str(self.repo.root)]), 0)
        with redirect_stdout(out2):
            self.assertEqual(sb.main(["inventory", str(self.repo.skill), "--repo-root", str(self.repo.root)]), 0)
        self.assertEqual(out1.getvalue(), out2.getvalue())
        self.assertEqual(json.loads(out1.getvalue())["tree_sha256"], self.base["tree_sha256"])

    def test_deterministic_ordering_independent_of_creation_order(self):
        other = Repo(self.tmp / "other")
        for name in ("zeta.md", "alpha.md", "mid.md"):
            other.write(f"skills/demo/references/{name}", name)
        for name in ("mid.md", "zeta.md", "alpha.md"):
            self.repo.write(f"skills/demo/references/{name}", name)
        a, b = self.repo.inventory(), other.inventory()
        self.assertEqual([f["path"] for f in a["files"]], sorted(f["path"] for f in a["files"]))
        self.assertEqual(a["files"], b["files"])
        self.assertEqual(a["tree_sha256"], b["tree_sha256"])
        self.assertEqual(a["dependencies"], sorted(a["dependencies"],
                                                   key=lambda d: (d["reference"], d["resolved_from"])))
        self.repo.commit()
        result = sb.compare(self.grant, self.repo.inventory())
        self.assertEqual(result["reasons"], sorted(result["reasons"], key=lambda r: (r["code"], r["detail"])))

    # -- inheritance -------------------------------------------------------------------

    def test_unchanged_clean_skill_inherits_only_the_grant_policy(self):
        result = sb.compare(self.grant, self.repo.inventory())
        self.assertTrue(result["inherit"], result["reasons"])
        self.assertEqual(result["inherited_host_policy_ref"], "host-policy:demo")
        self.assertEqual(result["qualification_status"], "source-comparison-not-qualified")
        self.assertEqual(set(result["provider_load_coverage"].values()), {"unknown"})

    def test_new_revision_denies_when_external_dependencies_exist(self):
        # Bytes are identical, but referenced scripts' transitive closure is not digested.
        self.repo.write("unrelated.txt", "x")
        self.repo.commit()
        self.assertEqual(self.codes(self.repo.inventory(), keep_revision=True),
                         {"revision-changed-with-external-dependencies"})

    def test_new_revision_with_identical_self_contained_skill_inherits(self):
        self.repo.write("skills/demo/SKILL.md", "---\nname: demo\ndescription: d\n---\nSelf-contained.\n")
        self.repo.commit()
        grant = _grant(self.repo.inventory())
        self.repo.write("unrelated.txt", "x")
        self.repo.commit()
        result = sb.compare(grant, self.repo.inventory())
        self.assertTrue(result["inherit"], result["reasons"])

    def test_dirty_repository_denies_when_external_dependencies_exist(self):
        self.repo.write("scripts/helper.py", "x = 1\n")  # untracked file a referenced script could import
        self.assertEqual(self.codes(self.repo.inventory(), keep_revision=True),
                         {"repository-not-clean-with-external-dependencies"})

    def test_changed_skill_bytes_invalidate_prior_grant(self):
        self.repo.write("skills/demo/references/notes.md", "notes changed\n")
        self.repo.commit()
        # notes.md is both a skill file and a linked reference, so both checks fire.
        self.assertEqual(self.codes(self.repo.inventory()), {"file-bytes-changed", "dependency-bytes-changed"})

    def test_changed_dependency_bytes_invalidate_prior_grant(self):
        self.repo.write("scripts/demo_tool.py", "print('other')\n")
        self.repo.commit()
        self.assertEqual(self.codes(self.repo.inventory()), {"dependency-bytes-changed"})

    def test_changed_adapter_metadata_invalidates(self):
        self.repo.write("skills/demo/agents/openai.yaml", "interface:\n  display_name: Demo\n  allow: all\n")
        self.repo.commit()
        self.assertIn("file-bytes-changed", self.codes(self.repo.inventory()))

    def test_added_file_and_mode_change_invalidate(self):
        self.repo.write("skills/demo/extra.sh", "echo hi\n")
        os.chmod(self.repo.skill / "references" / "notes.md", 0o755)
        self.repo.commit()
        self.assertEqual(self.codes(self.repo.inventory()), {"file-added", "file-mode-changed"})

    def test_widened_permission_metadata_invalidates(self):
        self.repo.write("skills/demo/SKILL.md", SKILL_MD.replace(
            "description:", "allowed-tools:\n  - Bash\n  - Write\ndescription:"))
        self.repo.commit()
        current = self.repo.inventory()
        self.assertEqual(current["frontmatter"]["permission_metadata"], {"allowed-tools": ["Bash", "Write"]})
        self.assertEqual(self.codes(current), {"file-bytes-changed", "permission-metadata-added"})

    def test_metadata_only_tampering_is_caught_even_with_matching_bytes(self):
        current = self.repo.inventory()
        current["frontmatter"]["permission_metadata"] = {"allowed-tools": "Bash(*)"}
        self.assertEqual(self.codes(current), {"permission-metadata-added"})

    def test_unknown_frontmatter_key_is_permission_relevant(self):
        self.repo.write("skills/demo/SKILL.md", SKILL_MD.replace("description:", "context: fork\ndescription:"))
        self.repo.commit()
        self.assertIn("permission-metadata-added", self.codes(self.repo.inventory()))

    def test_unparsed_frontmatter_is_unverified(self):
        self.repo.write("skills/demo/SKILL.md", "---\nname: demo\n[not, a, key]\n---\nbody\n")
        self.repo.commit()
        current = self.repo.inventory()
        self.assertEqual(current["frontmatter"]["status"], "unparsed")
        self.assertIn("frontmatter-unverified", self.codes(current))

    def test_removed_dependency_stays_unknown_and_denies(self):
        (self.repo.root / "scripts" / "demo_tool.py").unlink()
        self.repo.commit()
        current = self.repo.inventory()
        dep = next(d for d in current["dependencies"] if d["reference"] == "scripts/demo_tool.py")
        self.assertEqual((dep["status"], dep["sha256"]), ("missing", None))
        self.assertEqual(current["dependency_coverage"]["declared_path_references"], "incomplete")
        self.assertEqual(set(current["dependency_coverage"]["undiscovered_classes"].values()), {"unknown"})
        result = sb.compare(self.grant, current)
        self.assertFalse(result["inherit"])
        self.assertEqual(self.codes(current), {"dependency-missing"})
        self.assertEqual(set(result["provider_load_coverage"].values()), {"unknown"})

    def test_removed_dependency_reference_denies(self):
        self.repo.write("skills/demo/SKILL.md", SKILL_MD.replace("Run `scripts/demo_tool.py` and r", "R"))
        self.repo.commit()
        self.assertEqual(self.codes(self.repo.inventory()),
                         {"file-bytes-changed", "dependency-reference-removed"})

    def test_dynamic_reference_needs_explicit_grant_acceptance(self):
        grant = _grant(self.base, accepted_dynamic_references=[])
        self.assertEqual(self.codes(self.repo.inventory(), grant), {"dependency-dynamic"})

    def test_missing_origin_unknown_vcs_and_dirty_tree_deny(self):
        self.repo.write("skills/demo/references/notes.md", "dirty\n")
        self.assertIn("tree-not-clean", self.codes(self.repo.inventory()))
        no_origin = Repo(self.tmp / "no-origin", origin=None)
        self.assertIn("origin-unknown", self.codes(no_origin.inventory()))
        no_git = Repo(self.tmp / "no-git", git=False)
        inv = no_git.inventory()
        self.assertEqual(inv["source"], {"origin": "unknown", "revision": "unknown", "repository_tree_state": "unknown",
                                         "tree_state": "unknown", "vcs": "none-observed"})
        self.assertTrue({"origin-unknown", "revision-unknown", "tree-not-clean"} <= self.codes(inv))

    # -- refusal -----------------------------------------------------------------------

    def test_symlink_inside_skill_tree_is_refused(self):
        os.symlink("../../../scripts/demo_tool.py", self.repo.skill / "linked.py")
        with self.assertRaisesRegex(sb.SkillBoundaryError, "symlink refused"):
            self.repo.inventory()
        os.unlink(self.repo.skill / "linked.py")
        os.symlink("../../docs", self.repo.skill / "linkdir")
        with self.assertRaisesRegex(sb.SkillBoundaryError, "symlink refused"):
            self.repo.inventory()

    def test_symlinked_skill_directory_is_refused(self):
        with self.assertRaisesRegex(sb.SkillBoundaryError, "is a symlink"):
            sb.inventory(self.repo.root / ".claude" / "skills" / "demo", repo_root=self.repo.root)

    def test_skill_outside_repo_root_is_refused(self):
        with self.assertRaisesRegex(sb.SkillBoundaryError, "escapes the repository root"):
            sb.inventory(self.repo.skill, repo_root=self.repo.root / "docs")

    def test_dependency_path_escape_and_symlink_are_refused(self):
        outside = self.tmp / "secret.txt"
        outside.write_text("secret")
        os.symlink(str(outside), self.repo.root / "docs" / "linked.md")
        self.repo.write("skills/demo/SKILL.md", SKILL_MD + "\nAlso scripts/../../secret.txt, docs/linked.md"
                        " and [x](../../../secret.txt).\n")
        self.repo.commit()
        current = self.repo.inventory()
        statuses = {d["reference"]: d for d in current["dependencies"]}
        self.assertEqual(statuses["scripts/../../secret.txt"]["status"], "refused-path-escape")
        self.assertEqual(statuses["../../../secret.txt"]["status"], "refused-path-escape")
        self.assertEqual(statuses["docs/linked.md"]["status"], "refused-symlink")
        self.assertTrue(all(d["sha256"] is None for d in statuses.values() if d["status"].startswith("refused")))
        self.assertTrue({"dependency-refused-path-escape", "dependency-refused-symlink"} <= self.codes(current))

    def test_load_path_symlink_escaping_repo_is_refused(self):
        os.symlink(str(self.tmp), self.repo.root / ".claude" / "skills" / "evil")
        entry = sb._load_path(".claude/skills/evil", self.repo.root.resolve(), self.repo.skill.resolve())
        self.assertEqual((entry["kind"], entry["resolves_to_skill"]), ("refused-symlink-escape", False))
        entry = sb._load_path("../outside", self.repo.root.resolve(), self.repo.skill.resolve())
        self.assertEqual(entry["kind"], "refused-path-escape")

    def test_malformed_or_tampered_grant_is_an_error(self):
        tampered = copy.deepcopy(self.grant)
        tampered["inventory"]["files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(sb.SkillBoundaryError, "tree_sha256 does not match"):
            sb.compare(tampered, self.base)
        upgraded = copy.deepcopy(self.grant)
        upgraded["inventory"]["qualification_status"] = "qualified"
        with self.assertRaisesRegex(sb.SkillBoundaryError, "must remain"):
            sb.compare(upgraded, self.base)
        with self.assertRaisesRegex(sb.SkillBoundaryError, "host_policy_ref"):
            sb.compare({**self.grant, "host_policy_ref": ""}, self.base)

    def test_cli_exit_codes(self):
        grant_path = self.tmp / "grant.json"
        grant_path.write_text(json.dumps(self.grant))
        args = ["compare", "--grant", str(grant_path), "--skill-dir", str(self.repo.skill),
                "--repo-root", str(self.repo.root)]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sb.main(args), 0)
            self.repo.write("scripts/demo_tool.py", "changed\n")
            self.repo.commit()
            self.assertEqual(sb.main(args), 2)
        grant_path.write_text("{}")
        self.assertEqual(sb.main(args), 1)

    # -- recorded evidence -------------------------------------------------------------

    def test_recorded_real_skill_evidence_is_source_only(self):
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(evidence["evidence_kind"], "source-only-observation")
        self.assertFalse(evidence["live_provider_load_observed"])
        report = sb._validate_inventory(evidence["inventory"], "evidence.inventory")
        self.assertEqual(report["skill"]["name"], "workflow-artifact-capture")
        self.assertEqual(set(report["provider_load_coverage"].values()), {"unknown"})


if __name__ == "__main__":
    unittest.main()
