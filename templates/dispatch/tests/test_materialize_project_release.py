from __future__ import annotations

import json
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).parent))
import materialize_project as MATERIALIZE  # noqa: E402
import project_release as RELEASE  # noqa: E402
import render_project as RENDER  # noqa: E402


class MaterializeReleaseTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, dict[str, Path]]:
        import importlib
        fixture_class = importlib.import_module("test_project_release").ProjectReleaseTests
        project_path, repos = fixture_class()._fixture(root)
        for name, repo in repos.items():
            subprocess.run(
                ["git", "-C", str(repo), "remote", "set-url", "origin", f"https://example.invalid/{name}.git"],
                check=True,
                capture_output=True,
            )
        return project_path, repos

    def _descriptor_package(self, root: Path) -> tuple[Path, Path]:
        project_path, _repos = self._fixture(root)
        descriptor = root / "release.json"
        prove = lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True}
        RELEASE.create_release(project_path, descriptor, remote_verifier=prove)
        package = root / "package.json"
        RELEASE.pack_release(descriptor, package, root / "workspace")
        return descriptor, package

    def test_rebuild_uses_verified_bundle_fallback_and_preserves_exact_heads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            descriptor, package = self._descriptor_package(root)
            folder = root / "instance"
            result = MATERIALIZE.rebuild_release(
                descriptor,
                folder,
                workspace_root=root / "workspace",
                package_path=package,
                source_host="release-source",
                mode="exclusive-write",
            )
            self.assertEqual({state.status for state in result.members}, {"current"})
            self.assertEqual({state.head for state in result.members}, {json.loads(descriptor.read_text())["members"][index]["commit"] for index, state in enumerate(result.members)})
            self.assertIn("Release-pinned view", (folder / "AGENTS.md").read_text())
            marker = json.loads((folder / MATERIALIZE.MARKER_NAME).read_text())
            self.assertEqual(marker["release"]["schema"], "agentops-release-pinned/v1")
            self.assertTrue(all(item["acquisition"] == "bundle" for item in marker["release"]["members"]))
            for repo in (root / "workspace").iterdir():
                refs = subprocess.run(
                    ["git", "-C", str(repo), "for-each-ref", "--format=%(refname)", "refs/agentops/project-rebuild/"],
                    check=True, capture_output=True, text=True,
                ).stdout.strip()
                self.assertEqual(refs, "")

            context_before = (folder / MATERIALIZE.CONTEXT_NAME).stat().st_mtime_ns
            project = RENDER.load_project(root / "workspace" / "home" / "project.toml", workspace_root=root / "workspace")
            status = MATERIALIZE.materialize(project, folder, command="status")
            self.assertFalse(status.blocked)
            self.assertEqual(status.drift, ())
            self.assertEqual(context_before, (folder / MATERIALIZE.CONTEXT_NAME).stat().st_mtime_ns)
            with self.assertRaises(MATERIALIZE.ProjectFolderError):
                MATERIALIZE.materialize(project, folder, command="sync")

    def test_rebuild_without_durable_remote_or_package_fails_before_folder_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            descriptor = root / "release.json"
            prove = lambda repository, ref, commit: {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True}
            RELEASE.create_release(project_path, descriptor, remote_verifier=prove)
            folder = root / "not-created"
            with self.assertRaises(MATERIALIZE.ProjectFolderError):
                MATERIALIZE.rebuild_release(descriptor, folder, workspace_root=root / "workspace")
            self.assertFalse(folder.exists())

    def test_rebuild_ignores_destination_home_head_and_uses_descriptor_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            descriptor, package = self._descriptor_package(root)
            home = root / "workspace" / "home"
            subprocess.run(["git", "-C", str(home), "commit", "--allow-empty", "-m", "local-only-head"], check=True, capture_output=True)
            folder = root / "destination"
            result = MATERIALIZE.rebuild_release(
                descriptor, folder, workspace_root=root / "workspace", package_path=package, source_host="source"
            )
            selected = json.loads(descriptor.read_text())
            self.assertEqual([state.head for state in result.members], [item["commit"] for item in selected["members"]])
            marker = json.loads((folder / MATERIALIZE.MARKER_NAME).read_text())
            self.assertEqual(marker["source_binding_commit"], selected["binding"]["commit"])

    def test_reference_member_is_detached_readonly_without_freezing_write_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            binding = project_path.read_text(encoding="utf-8")
            binding = binding.replace(
                'repo_id = "child"\nbacklog = true\nrender = "full"',
                'repo_id = "child"\nbacklog = true\nrender = "none"\naccess = "reference"',
            )
            project_path.write_text(binding, encoding="utf-8")
            generated = repos["child"] / ".agents" / "project.generated.md"
            if generated.exists():
                generated.unlink()
            (repos["child"] / "AGENTS.md").write_text("# child\n", encoding="utf-8")
            for repo in repos.values():
                subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
                subprocess.run(["git", "-C", str(repo), "commit", "-m", "reference topology"], check=True, capture_output=True)
            descriptor = root / "release.json"
            RELEASE.create_release(
                project_path, descriptor,
                remote_verifier=lambda repository, ref, commit: {
                    "kind": "remote-ref", "repository": repository, "ref": ref,
                    "target": commit, "verified": True,
                },
            )
            package = root / "package.json"
            RELEASE.pack_release(descriptor, package, root / "workspace")
            folder = root / "instance"
            result = MATERIALIZE.rebuild_release(
                descriptor, folder, workspace_root=root / "workspace",
                package_path=package, source_host="source",
            )
            states = {state.repo_id: state for state in result.members}
            self.assertEqual(states["home"].effective_mode, "exclusive-write")
            self.assertEqual(states["child"].effective_mode, "shared-read")
            self.assertTrue((folder / "members" / "home" / "AGENTS.md").stat().st_mode & stat.S_IWUSR)
            self.assertFalse((folder / "members" / "child" / "AGENTS.md").stat().st_mode & stat.S_IWUSR)

    def test_stale_committed_renderer_output_fails_before_folder_or_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            generated = repos["child"] / ".agents" / "project.generated.md"
            generated.write_bytes(generated.read_bytes() + b"\nhand edit\n")
            subprocess.run(["git", "-C", str(repos["child"]), "add", "."], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repos["child"]), "commit", "-m", "stale guidance"], check=True, capture_output=True)
            descriptor = root / "release.json"
            RELEASE.create_release(
                project_path, descriptor,
                remote_verifier=lambda repository, ref, commit: {
                    "kind": "remote-ref", "repository": repository, "ref": ref,
                    "target": commit, "verified": True,
                },
            )
            package = root / "package.json"
            RELEASE.pack_release(descriptor, package, root / "workspace")
            folder = root / "instance"
            with self.assertRaises(MATERIALIZE.ProjectFolderError):
                MATERIALIZE.rebuild_release(
                    descriptor, folder, workspace_root=root / "workspace",
                    package_path=package, source_host="source",
                )
            self.assertFalse(folder.exists())
            for repo in repos.values():
                refs = subprocess.run(
                    ["git", "-C", str(repo), "for-each-ref", "--format=%(refname)", "refs/agentops/project-rebuild/"],
                    check=True, capture_output=True, text=True,
                ).stdout.strip()
                self.assertEqual(refs, "")


if __name__ == "__main__":
    unittest.main()
