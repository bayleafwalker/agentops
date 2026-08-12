from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_release as RELEASE  # noqa: E402
import render_project as RENDER  # noqa: E402
from resolve_environment_record import normalize_hostname  # noqa: E402


class ProjectReleaseTests(unittest.TestCase):
    def _git(self, repo: Path, *args: str, check: bool = True) -> str:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)
        if check:
            return result.stdout.strip()
        return result.stdout.strip()

    def _repo(self, root: Path, name: str) -> Path:
        remote = root / "remotes" / f"{name}.git"
        remote.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
        repo = root / "workspace" / name
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", str(remote), str(repo)], check=True, capture_output=True)
        self._git(repo, "config", "user.email", "release-tests@example.invalid")
        self._git(repo, "config", "user.name", "Release Tests")
        return repo

    def _fixture(self, root: Path) -> tuple[Path, dict[str, Path]]:
        repos = {name: self._repo(root, name) for name in ("home", "child")}
        (repos["home"] / "AGENTS.md").write_text("# home\n", encoding="utf-8")
        (repos["child"] / "AGENTS.md").write_text("# child\n", encoding="utf-8")
        (repos["home"] / ".project" / "sources").mkdir(parents=True)
        (repos["home"] / ".project" / "sources" / "10.md").write_text(
            "---\nrender_levels: [baseline, full]\n---\n# Source\n", encoding="utf-8"
        )
        (repos["home"] / "project.toml").write_text(
            """schema_version = 1
project_id = "f46fc856-7f25-48eb-9e48-cf795c1c8a41"
display_name = "release fixture"
home_repo = "home"

[[members]]
repo_id = "home"
backlog = true
render = "none"
repository = "https://example.invalid/home.git"
default_ref = "refs/heads/main"

[[members]]
repo_id = "child"
backlog = true
render = "full"
repository = "https://example.invalid/child.git"
default_ref = "refs/heads/main"
""",
            encoding="utf-8",
        )
        (repos["child"] / ".agents").mkdir()
        for repo in repos.values():
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-m", "initial")
            self._git(repo, "push", "origin", "main")
        # Seed the fixture with renderer-valid generated guidance/pointers so
        # release verification can fail closed on genuinely stale committed
        # output rather than relying on a placeholder file.
        project = RENDER.load_project(repos["home"] / "project.toml", workspace_root=root / "workspace")
        RENDER.apply_project(project, environment_records_dir=root / "no-environment-record")
        for repo in repos.values():
            if self._git(repo, "status", "--porcelain", "--untracked-files=all"):
                self._git(repo, "add", ".")
                self._git(repo, "commit", "-m", "chore(render): fixture guidance")
                self._git(repo, "push", "origin", "main")
        return repos["home"] / "project.toml", repos

    def test_create_is_deterministic_and_requires_exact_proofs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            def prove(repository: str, ref: str, commit: str) -> dict[str, object]:
                return {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True}
            first = root / "first.json"
            second = root / "second.json"
            one = RELEASE.create_release(project_path, first, remote_verifier=prove)
            two = RELEASE.create_release(project_path, second, remote_verifier=prove)
            self.assertEqual(one, two)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(self._git(repos["child"], "status", "--porcelain"), "")
            def fail(repository: str, ref: str, commit: str) -> dict[str, object]:
                raise RELEASE.ReleaseError("published ref moved")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.create_release(project_path, root / "bad.json", remote_verifier=fail)

    def test_pack_verify_package_and_rebuild_plan_do_not_create_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            descriptor_path = root / "release.json"
            RELEASE.create_release(project_path, descriptor_path, remote_verifier=lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True})
            before = {name: self._git(repo, "rev-parse", "HEAD") for name, repo in repos.items()}
            package_path = root / "package.json"
            RELEASE.pack_release(descriptor_path, package_path, root / "workspace")
            receipt = RELEASE.verify_package(package_path, descriptor_path=descriptor_path, source_host="test-source")
            self.assertEqual(receipt["outcome"], "verified")
            plan_path = root / "plan.json"
            plan = RELEASE.rebuild_plan(
                descriptor_path,
                plan_path,
                package_path,
                remote_verifier=lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True},
            )
            self.assertTrue(plan["ready"])
            self.assertEqual(before, {name: self._git(repo, "rev-parse", "HEAD") for name, repo in repos.items()})
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.pack_release(descriptor_path, package_path, root / "workspace")

    def test_verify_package_resolves_environment_records_from_home_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            records = repos["home"] / "templates" / "dispatch" / "environment-record"
            records.mkdir(parents=True)
            environment_id = normalize_hostname(socket.gethostname())
            (records / f"{environment_id}.json").write_text(
                json.dumps({
                    "schema_version": "environment-record/v1",
                    "id": environment_id,
                    "environment_class": "local",
                    "revision": 1,
                    "roles": ["release-test"],
                    "constraints": [],
                    "capabilities": [],
                    "runbook_refs": [],
                    "identity_bindings": [],
                }),
                encoding="utf-8",
            )
            project = RENDER.load_project(project_path, workspace_root=root / "workspace")
            RENDER.apply_project(project, environment_records_dir=records)
            for repo in repos.values():
                if self._git(repo, "status", "--porcelain", "--untracked-files=all"):
                    self._git(repo, "add", ".")
                    self._git(repo, "commit", "-m", "chore(render): fixture environment")
                    self._git(repo, "push", "origin", "main")

            descriptor_path = root / "release.json"
            RELEASE.create_release(
                project_path,
                descriptor_path,
                remote_verifier=lambda repository, ref, commit: {
                    "kind": "remote-ref", "repository": repository,
                    "ref": ref, "target": commit, "verified": True,
                },
            )
            package_path = root / "package.json"
            RELEASE.pack_release(descriptor_path, package_path, root / "workspace")
            receipt = RELEASE.verify_package(
                package_path,
                descriptor_path=descriptor_path,
                source_host="test-source",
            )
            self.assertEqual(receipt["outcome"], "verified")

    def test_strict_url_and_ref_parsers_reject_credentials_and_noncanonical_values(self) -> None:
        for value in ("http://example.invalid/repo.git", "https://user@example.invalid/repo.git", "https://example.invalid/repo.git?x=1", "https://example.invalid/repo.git/"):
            with self.assertRaises(RENDER.ProjectRenderError):
                RENDER.canonical_repository_url(value)
        for value in ("main", "refs/remotes/origin/main", "refs/heads/../main", "refs/heads/main//x"):
            with self.assertRaises(RENDER.ProjectRenderError):
                RENDER.canonical_default_ref(value)

    def test_verify_package_rejects_hash_traversal_and_symlink_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            descriptor_path = root / "release.json"
            RELEASE.create_release(project_path, descriptor_path, remote_verifier=lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True})
            package_path = root / "package.json"
            RELEASE.pack_release(descriptor_path, package_path, root / "workspace")
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["files"][0]["sha256"] = "0" * 64
            bad_hash = root / "bad-hash.json"
            bad_hash.write_text(json.dumps(package), encoding="utf-8")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.verify_package(bad_hash, descriptor_path=descriptor_path, source_host="test-source")
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["files"][0]["path"] = "../escape.bundle"
            traversal = root / "traversal.json"
            traversal.write_text(json.dumps(package), encoding="utf-8")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.verify_package(traversal, descriptor_path=descriptor_path, source_host="test-source")

    def test_descriptor_is_strict_and_recomputed_before_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            descriptor_path = root / "release.json"
            RELEASE.create_release(project_path, descriptor_path, remote_verifier=lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True})
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
            descriptor["members"][0]["local_repo"] = "/foreign"
            descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.pack_release(descriptor_path, root / "package.json", root / "workspace")

            descriptor = json.loads((root / "release.json").read_text(encoding="utf-8"))
            descriptor["members"][0]["documents"]["files"][0]["sha256"] = "0" * 64
            descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.pack_release(descriptor_path, root / "package2.json", root / "workspace")

    def test_package_rejects_symlink_components_and_bounded_reads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            descriptor_path = root / "release.json"
            RELEASE.create_release(project_path, descriptor_path, remote_verifier=lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True})
            package_path = root / "package.json"
            RELEASE.pack_release(descriptor_path, package_path, root / "workspace")
            package = json.loads(package_path.read_text(encoding="utf-8"))
            original = package["files"][0]["path"]
            link = root / "linked"
            link.symlink_to(root, target_is_directory=True)
            package["files"][0]["path"] = f"linked/{original}"
            package["members"][0]["bundle"] = f"linked/{original}"
            linked_package = root / "linked-package.json"
            linked_package.write_text(json.dumps(package), encoding="utf-8")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.verify_package(linked_package, descriptor_path=descriptor_path, source_host="test-source")

            oversized = root / "oversized"
            with oversized.open("wb") as stream:
                stream.truncate(RELEASE.MAX_PACKAGE_FILE_BYTES + 1)
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE._bounded_regular_bytes(oversized, "oversized")

    def test_staging_rejects_symlinked_descriptor_and_package_parents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            descriptor_path = root / "release.json"
            RELEASE.create_release(
                project_path, descriptor_path,
                remote_verifier=lambda repository, ref, commit: {
                    "kind": "remote-ref", "repository": repository, "ref": ref,
                    "target": commit, "verified": True,
                },
            )
            package_path = root / "package.json"
            RELEASE.pack_release(descriptor_path, package_path, root / "workspace")
            descriptor_link_root = root / "descriptor-link"
            descriptor_link_root.symlink_to(descriptor_path.parent, target_is_directory=True)
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.stage_verified_descriptor(descriptor_link_root / descriptor_path.name)
            package_link_root = root / "package-link"
            package_link_root.symlink_to(package_path.parent, target_is_directory=True)
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.stage_verified_package(
                    package_link_root / package_path.name,
                    descriptor_path,
                    source_host="source",
                )

    def test_output_creation_refuses_symlink_parent_and_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir()
            parent = root / "parent"
            parent.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE._write_new(parent / "result.json", {"ok": True})
            target = root / "target.json"
            target.write_text("existing", encoding="utf-8")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE._write_new(target, {"ok": False})

    def test_output_parent_swap_at_leaf_open_stays_on_held_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "parent"
            parent.mkdir()
            saved = root / "saved-parent"
            outside = root / "outside"
            outside.mkdir()
            original_open = RELEASE.os.open

            def swap_parent(name, *args, **kwargs):
                if name == "result.json" and kwargs.get("dir_fd") is not None and not saved.exists():
                    parent.rename(saved)
                    parent.symlink_to(outside, target_is_directory=True)
                return original_open(name, *args, **kwargs)

            RELEASE.os.open = swap_parent
            try:
                RELEASE._write_new(parent / "result.json", {"safe": True})
            finally:
                RELEASE.os.open = original_open
            self.assertTrue((saved / "result.json").is_file())
            self.assertFalse((outside / "result.json").exists())

    def test_receipt_requires_bounded_source_and_temporal_retention(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            descriptor_path = root / "release.json"
            RELEASE.create_release(project_path, descriptor_path, remote_verifier=lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True})
            package_path = root / "package.json"
            RELEASE.pack_release(descriptor_path, package_path, root / "workspace")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.verify_package(package_path, descriptor_path=descriptor_path, source_host="bad host", verified_at="2026-01-01T00:00:00Z")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.verify_package(package_path, descriptor_path=descriptor_path, source_host="source", verified_at="2026-01-01T00:00:00Z", retention_mode="expires", retain_until="2025-01-01T00:00:00Z")
            receipt = RELEASE.verify_package(package_path, descriptor_path=descriptor_path, source_host="source", verifier_host="verifier", verified_at="2026-01-01T00:00:00Z", retention_mode="expires", retain_until="2027-01-01T00:00:00Z")
            self.assertEqual(receipt["members"][0]["commit"], json.loads(descriptor_path.read_text(encoding="utf-8"))["members"][0]["commit"])

    def test_rebuild_prefers_verified_bundle_when_remote_ref_moved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            descriptor_path = root / "release.json"
            prove = lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True}
            RELEASE.create_release(project_path, descriptor_path, remote_verifier=prove)
            package_path = root / "package.json"
            RELEASE.pack_release(descriptor_path, package_path, root / "workspace")
            def moved(repository: str, ref: str, commit: str) -> dict[str, object]:
                raise RELEASE.ReleaseError("published ref moved")
            plan = RELEASE.rebuild_plan(descriptor_path, root / "ready.json", package_path, remote_verifier=moved)
            self.assertTrue(plan["ready"])

            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["descriptor_sha256"] = "0" * 64
            bad_package = root / "bad-package.json"
            bad_package.write_text(json.dumps(package), encoding="utf-8")
            blocked = RELEASE.rebuild_plan(descriptor_path, root / "blocked.json", bad_package, remote_verifier=moved)
            self.assertFalse(blocked["ready"])

    def test_bundle_objects_reject_self_consistent_descriptor_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            descriptor_path = root / "release.json"
            prove = lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True}
            RELEASE.create_release(project_path, descriptor_path, remote_verifier=prove)
            original = json.loads(descriptor_path.read_text(encoding="utf-8"))
            package_path = root / "package.json"
            RELEASE.pack_release(descriptor_path, package_path, root / "workspace")

            document_tamper = json.loads(json.dumps(original))
            file_entry = document_tamper["members"][1]["documents"]["files"][0]
            file_entry["sha256"] = "f" * 64
            file_entry["bytes"] = 1
            file_entry["commit"] = document_tamper["members"][1]["commit"]
            files = document_tamper["members"][1]["documents"]["files"]
            document_tamper["members"][1]["documents"]["bundle_sha256"] = RELEASE.digest(files)
            document_tamper["topology_digest"] = RELEASE.digest(document_tamper["members"])
            document_descriptor = root / "document-tamper.json"
            document_descriptor.write_bytes(RELEASE.canonical_bytes(document_tamper))
            document_package = root / "document-package.json"
            RELEASE.pack_release(document_descriptor, document_package, root / "workspace")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.verify_package(document_package, descriptor_path=document_descriptor, source_host="source")

            binding_tamper = json.loads(json.dumps(original))
            binding_tamper["project_id"] = "981b2073-d7af-4c28-bff3-3cf807495fba"
            binding_tamper["topology_digest"] = RELEASE.digest(binding_tamper["members"])
            binding_descriptor = root / "binding-tamper.json"
            binding_descriptor.write_bytes(RELEASE.canonical_bytes(binding_tamper))
            binding_package = root / "binding-package.json"
            RELEASE.pack_release(binding_descriptor, binding_package, root / "workspace")
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.verify_package(binding_package, descriptor_path=binding_descriptor, source_host="source")

    def test_pack_refuses_symlinked_parent_before_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            descriptor_path = root / "release.json"
            prove = lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True}
            RELEASE.create_release(project_path, descriptor_path, remote_verifier=prove)
            outside = root / "outside"
            outside.mkdir()
            link = root / "link"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(RELEASE.ReleaseError):
                RELEASE.pack_release(descriptor_path, link / "package.json", root / "workspace")
            self.assertEqual(list(outside.iterdir()), [])

    def test_pack_cleans_sidecars_on_oversized_or_mid_pack_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            descriptor_path = root / "release.json"
            prove = lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True}
            RELEASE.create_release(project_path, descriptor_path, remote_verifier=prove)
            original_git = RELEASE._git
            calls = {"bundle": 0}

            def oversized(repo, *args, **kwargs):
                result = original_git(repo, *args, **kwargs)
                if len(args) >= 3 and args[0:2] == ("bundle", "create"):
                    with Path(args[2]).open("ab") as staged:
                        staged.truncate(RELEASE.MAX_PACKAGE_FILE_BYTES + 1)
                return result

            RELEASE._git = oversized
            try:
                with self.assertRaises(RELEASE.ReleaseError):
                    RELEASE.pack_release(descriptor_path, root / "oversized.json", root / "workspace")
            finally:
                RELEASE._git = original_git
            self.assertEqual(sorted(path.name for path in root.iterdir() if path.name.startswith("oversized")), [])

            def fail_second(repo, *args, **kwargs):
                result = original_git(repo, *args, **kwargs)
                if len(args) >= 3 and args[0:2] == ("bundle", "create"):
                    calls["bundle"] += 1
                    if calls["bundle"] == 2:
                        raise RELEASE.ReleaseError("simulated second member failure")
                return result

            RELEASE._git = fail_second
            try:
                with self.assertRaises(RELEASE.ReleaseError):
                    RELEASE.pack_release(descriptor_path, root / "midfail.json", root / "workspace")
            finally:
                RELEASE._git = original_git
            self.assertEqual(sorted(path.name for path in root.iterdir() if path.name.startswith("midfail")), [])

    def test_pack_does_not_require_cross_filesystem_hard_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            descriptor_path = root / "release.json"
            prove = lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True}
            RELEASE.create_release(project_path, descriptor_path, remote_verifier=prove)
            original_link = RELEASE.os.link

            def cross_device(*args, **kwargs):
                raise OSError(18, "Invalid cross-device link")

            RELEASE.os.link = cross_device
            try:
                package = RELEASE.pack_release(descriptor_path, root / "cross-device.json", root / "workspace")
            finally:
                RELEASE.os.link = original_link
            self.assertTrue((root / "cross-device.json").is_file())
            self.assertEqual(len(package["members"]), 2)


if __name__ == "__main__":
    unittest.main()
