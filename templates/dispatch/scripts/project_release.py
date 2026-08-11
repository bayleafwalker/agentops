#!/usr/bin/env python3
"""Create and verify portable, Git-derived project release evidence.

This module deliberately never creates worktrees, project folders, leases, or
Git refs in a caller repository.  Remote verification is the only operation
that may use a network, and it runs in an empty temporary bare repository.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import tempfile
import tarfile
import tomllib
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Callable

import render_project


SCHEMA_RELEASE = "project-release/v1"
SCHEMA_PACKAGE = "project-evidence-package/v1"
SCHEMA_RECEIPT = "project-replication-receipt/v1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_PACKAGE_FILE_BYTES = 64 * 1024 * 1024
HOST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


class ReleaseError(ValueError):
    """A release/evidence input failed closed."""


@dataclass
class VerifiedPackageSnapshot:
    """Private immutable-once-created package bytes used by rebuild."""

    temporary: tempfile.TemporaryDirectory[str]
    descriptor_path: Path
    descriptor: dict[str, Any]
    package_path: Path
    package: dict[str, Any]
    bundle_paths: dict[str, Path]
    package_sha256: str

    def close(self) -> None:
        self.temporary.cleanup()

    def __enter__(self) -> "VerifiedPackageSnapshot":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@dataclass
class VerifiedDescriptorSnapshot:
    """Private bounded descriptor bytes used for one rebuild transaction."""

    temporary: tempfile.TemporaryDirectory[str]
    descriptor_path: Path
    descriptor: dict[str, Any]
    sha256: str

    def close(self) -> None:
        self.temporary.cleanup()

    def __enter__(self) -> "VerifiedDescriptorSnapshot":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(_canonical(value), ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


# Public, strict release APIs.  Consumers such as the materializer must use
# these instead of reaching into the implementation helpers below.
def canonical_digest(value: Any) -> str:
    return digest(value)


def load_release_descriptor(path: Path) -> dict[str, Any]:
    value = _load_json(path, "descriptor")
    _validate_descriptor_shape(value)
    return value


def load_evidence_package(path: Path, descriptor_path: Path) -> dict[str, Any]:
    value = _load_json(path, "package")
    _validate_package_shape(value)
    descriptor = load_release_descriptor(descriptor_path)
    expected = hashlib.sha256(descriptor_path.read_bytes()).hexdigest()
    if value["descriptor_sha256"] != expected:
        raise ReleaseError("package descriptor digest does not match descriptor")
    if {item["repo_id"] for item in value["members"]} != {item["repo_id"] for item in descriptor["members"]}:
        raise ReleaseError("package members do not correspond exactly to descriptor members")
    descriptor_by_id = {item["repo_id"]: item for item in descriptor["members"]}
    for item in value["members"]:
        if item["commit"] != descriptor_by_id[item["repo_id"]]["commit"]:
            raise ReleaseError(f"package commit does not match descriptor for {item['repo_id']}")
    return value


def stage_verified_descriptor(path: Path) -> VerifiedDescriptorSnapshot:
    """Take a bounded no-follow descriptor snapshot for a rebuild."""
    temporary = tempfile.TemporaryDirectory(prefix="agentops-release-descriptor-")
    root = Path(temporary.name)
    try:
        data = _bounded_regular_bytes(path, "descriptor")
        staged = root / "descriptor.json"
        staged.write_bytes(data)
        descriptor = load_release_descriptor(staged)
        return VerifiedDescriptorSnapshot(
            temporary, staged, descriptor, hashlib.sha256(data).hexdigest()
        )
    except Exception:
        temporary.cleanup()
        raise


def parse_verified_binding(content: bytes, descriptor: dict[str, Any]) -> dict[str, Any]:
    """Parse committed project.toml bytes and require descriptor topology."""
    try:
        raw = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ReleaseError(f"canonical project.toml is invalid: {error}") from error
    # Reuse the renderer's complete schema semantics against a private
    # synthetic workspace.  This validates exact top-level/member keys,
    # schema_version, display_name, document ownership/contradictions, URL and
    # ref syntax, without consulting any destination anchor.
    try:
        with tempfile.TemporaryDirectory(prefix="agentops-release-binding-") as temporary:
            workspace = Path(temporary)
            raw_home = raw.get("home_repo")
            safe_home = raw_home if isinstance(raw_home, str) and render_project.REPO_ID_RE.fullmatch(raw_home) else "__invalid_home__"
            home = workspace / safe_home
            home.mkdir(parents=True, exist_ok=True)
            (home / ".project" / "sources").mkdir(parents=True, exist_ok=True)
            binding_path = home / "project.toml"
            binding_path.write_bytes(content)
            render_project.load_project(
                binding_path, workspace_root=workspace, allow_missing_members=True
            )
    except (OSError, render_project.ProjectRenderError) as error:
        raise ReleaseError(f"canonical project.toml fails full binding schema validation: {error}") from error
    if raw.get("project_id") != descriptor["project_id"]:
        raise ReleaseError("canonical project.toml project_id does not match descriptor")
    members = raw.get("members")
    expected = descriptor["members"]
    if raw.get("home_repo") != next(
        item["repo_id"] for item in expected
        if item["repository"] == descriptor["binding"]["repository"]
        and item["commit"] == descriptor["binding"]["commit"]
    ) or not isinstance(members, list) or len(members) != len(expected):
        raise ReleaseError("canonical project.toml topology does not match descriptor")
    for raw_member, expected_member in zip(members, expected, strict=True):
        if not isinstance(raw_member, dict):
            raise ReleaseError("canonical project.toml member is malformed")
        for key in ("repo_id", "backlog", "render", "relationship", "access", "repository", "default_ref"):
            actual = raw_member.get(key, "implementation" if key == "relationship" else "write" if key == "access" else None)
            if actual != expected_member[key]:
                raise ReleaseError(f"canonical project.toml topology differs for {expected_member['repo_id']}")
        if _raw_document_contract(raw_member) != {
            key: expected_member["documents"][key] for key in ("required", "optional", "forbidden")
        }:
            raise ReleaseError(f"canonical project.toml document contract differs for {expected_member['repo_id']}")
    return raw


def _load_json(path: Path, label: str) -> Any:
    _reject_symlink_components(Path(path), label)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseError(f"cannot read {label}: {error}") from error


def _reject_symlink_components(path: Path, label: str) -> None:
    current = Path(path.anchor) if path.is_absolute() else Path(".")
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for component in parts:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ReleaseError(f"cannot inspect {label}: {error}") from error
        if stat.S_ISLNK(info.st_mode):
            raise ReleaseError(f"{label} contains a symlink path component")


def _open_directory_fd(parent: Path) -> int:
    """Open/create a directory tree while holding every traversed directory."""
    if any(component in {"", ".", ".."} for component in parent.parts):
        raise ReleaseError(f"output parent has unsafe path components: {parent}")
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(parent.anchor or ".", flags)
    components = parent.parts[1:] if parent.is_absolute() else parent.parts
    try:
        for component in components:
            try:
                next_fd = os.open(component, flags, dir_fd=fd)
            except FileNotFoundError:
                try:
                    os.mkdir(component, 0o755, dir_fd=fd)
                except FileExistsError:
                    pass
                next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except OSError as error:
        os.close(fd)
        raise ReleaseError(f"unsafe output parent {parent}: {error}") from error


def _open_existing_directory_fd(parent: Path, label: str) -> int:
    """Open an existing directory tree without following any component."""
    parent = Path(parent).absolute()
    if any(component in {"", ".", ".."} for component in parent.parts):
        raise ReleaseError(f"{label} has unsafe path components: {parent}")
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(parent.anchor or ".", flags)
    except OSError as error:
        raise ReleaseError(f"cannot open {label} parent: {error}") from error
    components = parent.parts[1:] if parent.is_absolute() else parent.parts
    try:
        for component in components:
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except OSError as error:
        os.close(fd)
        raise ReleaseError(f"{label} contains a missing or symlinked parent: {error}") from error


def _read_regular_fd(fd: int, label: str) -> bytes:
    try:
        info = os.fstat(fd)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ReleaseError(f"package file missing or not regular: {label}")
        if info.st_size > MAX_PACKAGE_FILE_BYTES:
            raise ReleaseError(f"package file exceeds bounded size: {label}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, MAX_PACKAGE_FILE_BYTES - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_PACKAGE_FILE_BYTES:
                raise ReleaseError(f"package file exceeds bounded size: {label}")
            chunks.append(chunk)
        if total != info.st_size:
            raise ReleaseError(f"file changed while staging: {label}")
        return b"".join(chunks)
    except OSError as error:
        raise ReleaseError(f"cannot read package file {label}: {error}") from error


def _read_relative_regular_fd(root_fd: int, raw: str, label: str) -> bytes:
    """Read a contained relative path while holding each no-follow parent FD."""
    if (
        not raw or raw.startswith("/") or "\\" in raw or "//" in raw
        or any(part in {"", ".", ".."} for part in raw.split("/"))
    ):
        raise ReleaseError(f"unsafe package file path: {raw}")
    current_fd = os.dup(root_fd)
    try:
        parts = raw.split("/")
        for component in parts[:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
        leaf_fd = os.open(
            parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=current_fd
        )
        try:
            return _read_regular_fd(leaf_fd, label)
        finally:
            os.close(leaf_fd)
    except OSError as error:
        raise ReleaseError(f"package file unavailable: {label}: {error}") from error
    finally:
        os.close(current_fd)


def _write_new_at(directory_fd: int, name: str, value: Any) -> None:
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ReleaseError(f"output has unsafe leaf name: {name}")
    try:
        leaf_fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
            dir_fd=directory_fd,
        )
    except FileExistsError as error:
        raise ReleaseError(f"refusing to overwrite existing output: {name}") from error
    except OSError as error:
        raise ReleaseError(f"cannot create output {name}: {error}") from error
    try:
        with os.fdopen(leaf_fd, "wb") as stream:
            stream.write(canonical_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            os.unlink(name, dir_fd=directory_fd)
        except OSError:
            pass
        raise


def _copy_new_at(directory_fd: int, name: str, source: Path) -> None:
    """Copy a bounded staged regular file into a held directory exclusively."""
    try:
        source_info = source.lstat()
    except OSError as error:
        raise ReleaseError(f"cannot inspect staged sidecar {source}: {error}") from error
    if stat.S_ISLNK(source_info.st_mode) or not stat.S_ISREG(source_info.st_mode):
        raise ReleaseError(f"staged sidecar is not a regular file: {source}")
    if source_info.st_size > MAX_PACKAGE_FILE_BYTES:
        raise ReleaseError(f"generated bundle exceeds bounded size: {name}")
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    destination_fd: int | None = None
    try:
        current_info = os.fstat(source_fd)
        if not stat.S_ISREG(current_info.st_mode) or current_info.st_size > MAX_PACKAGE_FILE_BYTES:
            raise ReleaseError(f"generated bundle exceeds bounded size: {name}")
        try:
            destination_fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o644,
                dir_fd=directory_fd,
            )
        except FileExistsError as error:
            raise ReleaseError(f"refusing to overwrite existing bundle sidecar: {name}") from error
        total = 0
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_PACKAGE_FILE_BYTES:
                raise ReleaseError(f"generated bundle exceeds bounded size: {name}")
            offset = 0
            while offset < len(chunk):
                offset += os.write(destination_fd, chunk[offset:])
        if total != current_info.st_size:
            raise ReleaseError(f"staged bundle changed while reading: {name}")
        os.fsync(destination_fd)
    except Exception:
        if destination_fd is not None:
            try:
                os.close(destination_fd)
            except OSError:
                pass
            try:
                os.unlink(name, dir_fd=directory_fd)
            except OSError:
                pass
            destination_fd = None
        raise
    finally:
        if destination_fd is not None:
            os.close(destination_fd)
        os.close(source_fd)


def _write_new(path: Path, value: Any) -> None:
    path = Path(path)
    directory_fd = _open_directory_fd(path.parent)
    try:
        _write_new_at(directory_fd, path.name, value)
    finally:
        os.close(directory_fd)


def _git(repo: Path, *args: str, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    inherited = os.environ.copy()
    inherited["GIT_OPTIONAL_LOCKS"] = "0"
    if env:
        inherited.update(env)
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False, env=inherited)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise ReleaseError(f"{repo}: git {' '.join(args)}: {detail}")
    return result


def _git_bytes(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    if result.returncode:
        raise ReleaseError(f"{repo}: git {' '.join(args)} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def _require_digest(value: str, label: str, length: int = 64) -> str:
    pattern = HEX64 if length == 64 else HEX40
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ReleaseError(f"{label} must be lowercase hexadecimal length {length}")
    return value


def _canonical_repo(value: Any, label: str) -> str:
    try:
        return render_project.canonical_repository_url(value, label)
    except render_project.ProjectRenderError as error:
        raise ReleaseError(str(error)) from error


def _canonical_ref(value: Any, label: str) -> str:
    try:
        return render_project.canonical_default_ref(value, label)
    except render_project.ProjectRenderError as error:
        raise ReleaseError(str(error)) from error


def _repo_status(repo: Path) -> None:
    result = _git(repo, "status", "--porcelain", "--untracked-files=all")
    if result.stdout.strip():
        raise ReleaseError(f"{repo}: clean repository required; worktree is dirty")


def _head(repo: Path) -> tuple[str, str | None]:
    commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if not HEX40.fullmatch(commit):
        raise ReleaseError(f"{repo}: HEAD is not a commit object")
    branch_result = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    return commit, branch_result.stdout.strip() if branch_result.returncode == 0 else None


def _show(repo: Path, commit: str, path: str) -> bytes:
    if not path or path.startswith("/") or ".." in Path(path).parts:
        raise ReleaseError(f"unsafe repository path: {path}")
    return _git_bytes(repo, "show", f"{commit}:{path}")


def _tracked_regular_at(repo: Path, commit: str, path: str) -> bytes:
    mode = _git(repo, "ls-tree", "-z", commit, "--", path).stdout
    if not mode:
        raise ReleaseError(f"{repo}: required document missing at {commit}:{path}")
    entries = mode.split("\0")
    if len(entries) < 2 or not entries[0].split(" ", 1)[0].startswith("100"):
        raise ReleaseError(f"{repo}: required document is not a regular tracked file: {path}")
    return _show(repo, commit, path)


def _member_document_record(member: render_project.MemberBinding, commit: str) -> dict[str, Any]:
    paths = list(member.required_documents)
    for path in member.optional_documents:
        if path not in paths:
            result = _git(member.repo_root, "cat-file", "-e", f"{commit}:{path}", check=False)
            if result.returncode == 0:
                paths.append(path)
    for path in member.forbidden_documents:
        if _git(member.repo_root, "cat-file", "-e", f"{commit}:{path}", check=False).returncode == 0:
            raise ReleaseError(f"{member.repo_id}: forbidden document is present at selected commit: {path}")
    files: list[dict[str, Any]] = []
    for path in paths:
        content = _tracked_regular_at(member.repo_root, commit, path)
        files.append({"path": path, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content), "commit": commit})
    files.sort(key=lambda item: item["path"])
    return {
        "required": list(member.required_documents),
        "optional": list(member.optional_documents),
        "forbidden": list(member.forbidden_documents),
        "files": files,
        "bundle_sha256": digest(files),
    }


def _binding_member(project: render_project.ProjectBinding, repo_id: str) -> render_project.MemberBinding:
    for member in project.members:
        if member.repo_id == repo_id:
            return member
    raise ReleaseError(f"unknown member: {repo_id}")


def _require_release_metadata(project: render_project.ProjectBinding) -> None:
    for member in project.members:
        if member.repository is None or member.default_ref is None:
            raise ReleaseError(
                f"{member.repo_id}: repository and default_ref are required for project-release creation"
            )


def create_release(
    project_path: Path,
    output: Path,
    *,
    remote_verifier: Callable[[str, str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    project = render_project.load_project(project_path)
    _require_release_metadata(project)
    verifier = remote_verifier or verify_remote
    observations: list[dict[str, Any]] = []
    for member in project.members:
        _repo_status(member.repo_root)
        commit, branch = _head(member.repo_root)
        documents = _member_document_record(member, commit)
        try:
            proof = verifier(member.repository, member.default_ref, commit)
        except Exception as error:
            raise ReleaseError(f"{member.repo_id}: remote durability verification failed: {error}") from error
        if (
            not isinstance(proof, dict)
            or proof.get("kind") != "remote-ref"
            or proof.get("repository") != member.repository
            or proof.get("ref") != member.default_ref
            or proof.get("target") != commit
            or proof.get("verified") is not True
        ):
            raise ReleaseError(f"{member.repo_id}: independent exact remote-ref verification failed")
        observations.append({
            "repo_id": member.repo_id,
            "backlog": member.backlog,
            "render": member.render,
            "relationship": member.relationship,
            "access": member.access,
            "repository": member.repository,
            "commit": commit,
            "branch": branch,
            "default_ref": member.default_ref,
            "documents": documents,
            "durability": {"kind": "remote-ref", "ref": member.default_ref, "target": commit, "verified": True},
        })
    topology_digest = digest(observations)
    home = _binding_member(project, project.home_repo)
    binding_commit, _ = _head(project.home_root)
    binding_bytes = _show(project.home_root, binding_commit, "project.toml")
    descriptor = {
        "schema": SCHEMA_RELEASE,
        "project_id": project.project_id,
        "binding": {
            "repository": home.repository,
            "commit": binding_commit,
            "path": "project.toml",
            "raw_sha256": hashlib.sha256(binding_bytes).hexdigest(),
        },
        "topology_digest": topology_digest,
        "members": observations,
    }
    if remote_verifier is None:
        for member in observations:
            verify_remote(
                member["repository"],
                member["default_ref"],
                member["commit"],
                documents=member["documents"],
                descriptor=descriptor,
                verify_binding=member["repo_id"] == project.home_repo,
            )
    if any(output.resolve().is_relative_to(member.repo_root.resolve()) for member in project.members):
        raise ReleaseError("release output must not be inside a declared member repository")
    _write_new(output, descriptor)
    return descriptor


def _tree_blob_bytes(repo: Path, commit: str, path: str) -> bytes:
    tree = _git(repo, "ls-tree", "-z", commit, "--", path).stdout
    if not tree:
        raise ReleaseError(f"selected commit is missing document: {path}")
    mode = tree.split(" ", 1)[0]
    if not mode.startswith("100"):
        raise ReleaseError(f"selected document is not a regular file: {path}")
    return _git_bytes(repo, "show", f"{commit}:{path}")


def _verify_document_objects(repo: Path, commit: str, documents: dict[str, Any]) -> None:
    for entry in documents["files"]:
        content = _tree_blob_bytes(repo, commit, entry["path"])
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ReleaseError(f"document object mismatch at {commit}:{entry['path']}")
    for path in documents["forbidden"]:
        if _git(repo, "cat-file", "-e", f"{commit}:{path}", check=False).returncode == 0:
            raise ReleaseError(f"forbidden document object is present at {commit}:{path}")


def _raw_document_contract(raw_member: dict[str, Any]) -> dict[str, list[str]]:
    render = raw_member["render"]
    access = raw_member.get("access", "write")
    required = ["AGENTS.md"]
    optional: list[str] = []
    forbidden: list[str] = []
    generated = ".agents/project.generated.md"
    if render == "none" or access == "reference":
        forbidden.append(generated)
    else:
        required.append(generated)
    raw_documents = raw_member.get("documents", {})
    if isinstance(raw_documents, list):
        raw_documents = {"required": raw_documents}
    if not isinstance(raw_documents, dict):
        raise ReleaseError(f"{raw_member.get('repo_id', '<unknown>')}: invalid document contract")
    def paths(key: str) -> list[str]:
        value = raw_documents.get(key, [])
        if not isinstance(value, list):
            raise ReleaseError(f"{raw_member.get('repo_id', '<unknown>')}: invalid document contract")
        result: list[str] = []
        for path in value:
            try:
                result.append(render_project._document_path(path, f"{raw_member.get('repo_id', '<unknown>')}.documents.{key}"))
            except render_project.ProjectRenderError as error:
                raise ReleaseError(str(error)) from error
        return result
    required.extend(paths("required"))
    required.extend(paths("authored"))
    required.extend(paths("generated"))
    optional.extend(paths("optional"))
    forbidden.extend(paths("forbidden"))
    return {
        "required": list(dict.fromkeys(required)),
        "optional": list(dict.fromkeys(optional)),
        "forbidden": list(dict.fromkeys(forbidden)),
    }


def _verify_binding_object(repo: Path, descriptor: dict[str, Any], commit: str) -> None:
    binding = descriptor["binding"]
    if commit != binding["commit"]:
        raise ReleaseError("binding commit is not the selected home commit")
    content = _tree_blob_bytes(repo, commit, binding["path"])
    if hashlib.sha256(content).hexdigest() != binding["raw_sha256"]:
        raise ReleaseError("canonical project.toml object digest does not match descriptor")
    parse_verified_binding(content, descriptor)
    try:
        raw = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ReleaseError(f"canonical project.toml is invalid: {error}") from error
    if raw.get("project_id") != descriptor["project_id"]:
        raise ReleaseError("canonical project.toml project_id does not match descriptor")
    raw_members = raw.get("members")
    if not isinstance(raw_members, list) or len(raw_members) != len(descriptor["members"]):
        raise ReleaseError("canonical project.toml member topology does not match descriptor")
    raw_home = raw.get("home_repo")
    descriptor_home = next((member["repo_id"] for member in descriptor["members"] if member["repository"] == binding["repository"] and member["commit"] == commit), None)
    if raw_home != descriptor_home:
        raise ReleaseError("canonical project.toml home_repo does not match descriptor")
    for raw_member, expected in zip(raw_members, descriptor["members"]):
        if not isinstance(raw_member, dict):
            raise ReleaseError("canonical project.toml member is malformed")
        semantic = {
            "repo_id": raw_member.get("repo_id"),
            "backlog": raw_member.get("backlog"),
            "render": raw_member.get("render"),
            "relationship": raw_member.get("relationship", "implementation"),
            "access": raw_member.get("access", "write"),
            "repository": raw_member.get("repository"),
            "default_ref": raw_member.get("default_ref"),
        }
        expected_semantic = {key: expected[key] for key in semantic}
        if semantic != expected_semantic or _raw_document_contract(raw_member) != {
            key: expected["documents"][key] for key in ("required", "optional", "forbidden")
        }:
            raise ReleaseError(f"canonical project.toml topology differs for {expected['repo_id']}")


def _extract_verified_bundle(path: Path, commit: str, destination: Path) -> None:
    """Extract one exact-commit bundle into a private inspection tree."""
    with tempfile.TemporaryDirectory(prefix="agentops-release-render-") as temporary:
        bare = Path(temporary) / "tree.git"
        _git(Path(temporary), "init", "--bare", "--initial-branch=main", str(bare))
        heads = _bundle_heads(path, bare)
        target: str | None = None
        for index, (_head, ref) in enumerate(heads):
            candidate = f"refs/private/render/{index}"
            fetched = _git(bare, "fetch", "--no-tags", str(path), f"{ref}:{candidate}", check=False)
            if fetched.returncode == 0 and _git(bare, "rev-parse", candidate, check=False).stdout.strip() == commit:
                target = candidate
                break
        if target is None:
            raise ReleaseError(f"bundle does not contain exact selected commit {commit}")
        archived = subprocess.run(
            ["git", "-C", str(bare), "archive", "--format=tar", commit],
            check=False, capture_output=True,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        if archived.returncode:
            raise ReleaseError(f"could not inspect selected bundle tree: {archived.stderr.decode(errors='replace').strip()}")
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(archived.stdout), mode="r:") as archive:
            archive.extractall(destination)


def _verify_renderer_semantics(
    descriptor: dict[str, Any],
    checked_bundles: dict[str, Path],
    package_members: list[dict[str, Any]],
) -> None:
    """Reject any non-current renderer-owned output in selected trees."""
    with tempfile.TemporaryDirectory(prefix="agentops-release-render-workspace-") as temporary:
        workspace = Path(temporary)
        for member in package_members:
            _extract_verified_bundle(
                checked_bundles[member["bundle"]], member["commit"], workspace / member["repo_id"]
            )
        home_id = next(
            member["repo_id"] for member in descriptor["members"]
            if member["repository"] == descriptor["binding"]["repository"]
            and member["commit"] == descriptor["binding"]["commit"]
        )
        project_path = workspace / home_id / descriptor["binding"]["path"]
        project = render_project.load_project(project_path, workspace_root=workspace)
        _require_renderer_semantics(
            project,
            workspace / home_id / "templates" / "dispatch" / "environment-record",
        )


def _require_renderer_semantics(
    project: render_project.ProjectBinding,
    environment_records_dir: Path,
) -> None:
    statuses = render_project.inspect_project(
        project, environment_records_dir=environment_records_dir
    )
    members = {member.repo_id: member for member in project.members}
    for status in statuses:
        member = members[status.repo_id]
        renderable = member.render != "none" and member.access != "reference"
        expected_generated = "in-sync" if renderable else "not-applicable"
        expected_pointer = "in-sync" if renderable else "not-applicable"
        if status.generated != expected_generated:
            raise ReleaseError(
                f"{status.repo_id}: selected committed renderer output is {status.generated}; "
                f"expected {expected_generated}"
            )
        if status.pointer != expected_pointer:
            raise ReleaseError(
                f"{status.repo_id}: selected committed project pointer is {status.pointer}; "
                f"expected {expected_pointer}"
            )
        if status.environment not in {"in-sync", "not-applicable"}:
            raise ReleaseError(
                f"{status.repo_id}: selected committed environment output is {status.environment}"
            )
        if status.environment_pointer not in {"in-sync", "not-applicable"}:
            raise ReleaseError(
                f"{status.repo_id}: selected committed environment pointer is {status.environment_pointer}"
            )


def verify_remote_project_render_state(descriptor: dict[str, Any]) -> None:
    """Verify renderer-owned committed state across all exact remote refs."""
    _validate_descriptor_shape(descriptor)
    with tempfile.TemporaryDirectory(prefix="agentops-release-remote-render-") as temporary:
        workspace = Path(temporary)
        bare_root = workspace / ".bare"
        bare_root.mkdir()
        for member in descriptor["members"]:
            repo_root = workspace / member["repo_id"]
            bare = bare_root / (member["repo_id"] + ".git")
            _git(workspace, "init", "--bare", "--initial-branch=main", str(bare))
            isolated = {
                "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
            }
            target = "refs/private/render-proof"
            fetched = _git(
                bare, "-c", "core.hooksPath=/dev/null", "fetch", "--no-tags",
                member["repository"], f"{member['default_ref']}:{target}",
                check=False, env=isolated,
            )
            if fetched.returncode:
                raise ReleaseError(
                    f"{member['repo_id']}: remote renderer verification failed: "
                    f"{fetched.stderr.strip()}"
                )
            if _git(bare, "rev-parse", target).stdout.strip() != member["commit"]:
                raise ReleaseError(f"{member['repo_id']}: remote ref moved during renderer verification")
            archived = subprocess.run(
                ["git", "-C", str(bare), "archive", "--format=tar", member["commit"]],
                check=False, capture_output=True,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            )
            if archived.returncode:
                raise ReleaseError(f"{member['repo_id']}: remote renderer tree unavailable")
            repo_root.mkdir()
            with tarfile.open(fileobj=io.BytesIO(archived.stdout), mode="r:") as archive:
                archive.extractall(repo_root)
        home_id = next(
            member["repo_id"] for member in descriptor["members"]
            if member["repository"] == descriptor["binding"]["repository"]
            and member["commit"] == descriptor["binding"]["commit"]
        )
        project = render_project.load_project(
            workspace / home_id / descriptor["binding"]["path"], workspace_root=workspace
        )
        _require_renderer_semantics(project, workspace / ".no-environment-record")


def verify_remote(
    repository: str,
    ref: str,
    commit: str,
    *,
    documents: dict[str, Any] | None = None,
    descriptor: dict[str, Any] | None = None,
    verify_binding: bool = False,
) -> dict[str, Any]:
    _canonical_repo(repository, "repository")
    _canonical_ref(ref, "ref")
    _require_digest(commit, "commit", 40)
    with tempfile.TemporaryDirectory(prefix="agentops-release-remote-") as temporary:
        bare = Path(temporary) / "proof.git"
        _git(Path(temporary), "init", "--bare", "--initial-branch=main", str(bare))
        isolated = {"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        target_ref = "refs/private/agentops-proof"
        fetched = _git(bare, "-c", "core.hooksPath=/dev/null", "fetch", "--no-tags", repository, f"{ref}:{target_ref}", check=False, env=isolated)
        if fetched.returncode:
            raise ReleaseError(f"remote unavailable or network failure for {repository} {ref}: {fetched.stderr.strip()}")
        observed = _git(bare, "rev-parse", target_ref).stdout.strip()
        if observed != commit:
            raise ReleaseError(f"remote integrity failure: {repository} {ref} points to {observed}, expected {commit}")
        if documents is not None:
            _verify_document_objects(bare, commit, documents)
        if verify_binding:
            if descriptor is None:
                raise ReleaseError("binding verification requires descriptor")
            _verify_binding_object(bare, descriptor, commit)
    return {"kind": "remote-ref", "repository": repository, "ref": ref, "target": commit, "verified": True}


def verified_remote_object(
    repository: str,
    ref: str,
    commit: str,
    path: str,
) -> bytes:
    """Fetch an exact remote ref in isolation and return one verified blob."""
    _canonical_repo(repository, "repository")
    _canonical_ref(ref, "ref")
    _require_digest(commit, "commit", 40)
    with tempfile.TemporaryDirectory(prefix="agentops-release-object-") as temporary:
        bare = Path(temporary) / "object.git"
        _git(Path(temporary), "init", "--bare", "--initial-branch=main", str(bare))
        isolated = {
            "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
        }
        target_ref = "refs/private/agentops-object"
        fetched = _git(
            bare, "-c", "core.hooksPath=/dev/null", "fetch", "--no-tags",
            repository, f"{ref}:{target_ref}", check=False, env=isolated,
        )
        if fetched.returncode or _git(bare, "rev-parse", target_ref).stdout.strip() != commit:
            raise ReleaseError(f"remote object did not resolve exact commit for {repository} {ref}")
        return _tree_blob_bytes(bare, commit, path)


def _safe_package_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not raw
        or path.parts == (".",)
        or re.match(r"^[A-Za-z]:", raw)
        or "\\" in raw
        or "//" in raw
        or any(part in {"", ".", ".."} for part in raw.split("/"))
        or any(ord(char) < 32 for char in raw)
    ):
        raise ReleaseError(f"unsafe package file path: {raw}")
    # Reject symlink components before resolving; resolve() alone would make a
    # symlink escape look like an ordinary contained path.
    current = root
    for component in path.parts:
        current = current / component
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ReleaseError(f"package path contains symlink: {raw}")
        except FileNotFoundError:
            continue
    candidate = (root / path).resolve(strict=False)
    if not candidate.is_relative_to(root.resolve()):
        raise ReleaseError(f"package file escapes root: {raw}")
    return candidate


def _bounded_regular_bytes(path: Path, label: str) -> bytes:
    path = Path(path)
    _reject_symlink_components(path, label)
    parent_fd = _open_existing_directory_fd(path.parent, label)
    try:
        leaf_fd = os.open(
            path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd
        )
        try:
            return _read_regular_fd(leaf_fd, label)
        finally:
            os.close(leaf_fd)
    finally:
        os.close(parent_fd)


def _bundle_heads(path: Path, repo: Path | None = None) -> list[tuple[str, str]]:
    command = ["bundle", "list-heads", str(path)]
    result = _git(repo, *command, check=False) if repo is not None else subprocess.run(["git", *command], capture_output=True, text=True, check=False, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    if result.returncode:
        raise ReleaseError(f"invalid Git bundle {path}: {result.stderr.strip()}")
    heads: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.split(" ", 1)
        if len(fields) != 2 or not HEX40.fullmatch(fields[0]):
            raise ReleaseError(f"invalid bundle advertised head: {line}")
        heads.append((fields[0], fields[1]))
    if not heads:
        raise ReleaseError(f"bundle has no advertised refs: {path}")
    return heads


def _verify_bundle(
    path: Path,
    commit: str,
    *,
    documents: dict[str, Any] | None = None,
    descriptor: dict[str, Any] | None = None,
    verify_binding: bool = False,
) -> list[tuple[str, str]]:
    if path.is_symlink() or not path.is_file():
        raise ReleaseError(f"bundle must be a regular file: {path}")
    with tempfile.TemporaryDirectory(prefix="agentops-release-bundle-") as temporary:
        bare = Path(temporary) / "empty.git"
        _git(Path(temporary), "init", "--bare", "--initial-branch=main", str(bare))
        check = _git(bare, "bundle", "verify", str(path), check=False)
        if check.returncode:
            raise ReleaseError(f"bundle verification failed: {check.stderr.strip() or check.stdout.strip()}")
        if "prerequisite" in check.stdout.lower() or "prerequisite" in check.stderr.lower():
            raise ReleaseError("incremental/prerequisite bundles are not accepted")
        heads = _bundle_heads(path, bare)
        selected_target: str | None = None
        for index, (_head, ref) in enumerate(heads):
            target = f"refs/private/bundle/{index}"
            fetched = _git(bare, "fetch", str(path), f"{ref}:{target}", check=False)
            if fetched.returncode:
                raise ReleaseError(f"bundle unbundle failed: {fetched.stderr.strip()}")
            # The v1 descriptor has no ancestor-selection field: the
            # advertised ref must identify the selected commit exactly.  A
            # future schema may model an ancestor proof explicitly.
            observed = _git(bare, "rev-parse", target, check=False).stdout.strip()
            if observed == commit:
                selected_target = target
                break
        if selected_target is not None:
            if documents is not None:
                _verify_document_objects(bare, commit, documents)
            if verify_binding:
                if descriptor is None:
                    raise ReleaseError("binding verification requires descriptor")
                _verify_binding_object(bare, descriptor, commit)
            return heads
    raise ReleaseError(f"bundle does not advertise a ref reaching required commit {commit}")


def verify_verified_bundle(
    path: Path,
    commit: str,
    *,
    documents: dict[str, Any] | None = None,
    descriptor: dict[str, Any] | None = None,
    verify_binding: bool = False,
) -> list[tuple[str, str]]:
    """Verify a standalone bundle and its selected Git objects strictly."""
    return _verify_bundle(
        path,
        commit,
        documents=documents,
        descriptor=descriptor,
        verify_binding=verify_binding,
    )


def verified_bundle_object(path: Path, commit: str, object_path: str) -> bytes:
    """Verify a standalone bundle in isolation and return one Git blob."""
    _verify_bundle(path, commit)
    with tempfile.TemporaryDirectory(prefix="agentops-release-object-") as temporary:
        bare = Path(temporary) / "object.git"
        _git(Path(temporary), "init", "--bare", "--initial-branch=main", str(bare))
        heads = _bundle_heads(path, bare)
        for index, (_head, ref) in enumerate(heads):
            target = f"refs/private/object/{index}"
            fetched = _git(bare, "fetch", "--no-tags", str(path), f"{ref}:{target}", check=False)
            if fetched.returncode == 0 and _git(bare, "rev-parse", target, check=False).stdout.strip() == commit:
                return _tree_blob_bytes(bare, commit, object_path)
    raise ReleaseError(f"bundle does not contain requested object at {object_path}")


def verify_release_package(
    package_path: Path,
    descriptor_path: Path,
    *,
    source_host: str,
    receipt_output: Path | None = None,
) -> dict[str, Any]:
    """Verify a descriptor-bound package and optionally emit its receipt."""
    return verify_package(
        package_path,
        receipt_output,
        descriptor_path=descriptor_path,
        source_host=source_host,
    )


def stage_verified_package(
    package_path: Path,
    descriptor_path: Path,
    *,
    source_host: str,
) -> VerifiedPackageSnapshot:
    """Verify once, then own private copies for the remainder of a rebuild."""
    temporary = tempfile.TemporaryDirectory(prefix="agentops-release-snapshot-")
    root = Path(temporary.name)
    try:
        descriptor_bytes = _bounded_regular_bytes(descriptor_path, "descriptor")
        staged_descriptor = root / "descriptor.json"
        staged_descriptor.write_bytes(descriptor_bytes)
        descriptor = load_release_descriptor(staged_descriptor)
        package_bytes = _bounded_regular_bytes(package_path, "package")
        staged_package = root / "package.json"
        staged_package.write_bytes(package_bytes)
        staged_value = _load_json(staged_package, "staged package")
        _validate_package_shape(staged_value)
        bundle_paths: dict[str, Path] = {}
        package_root_fd = _open_existing_directory_fd(package_path.parent, "package")
        try:
            for entry in staged_value["files"]:
                raw_path = entry["path"]
                _reject_symlink_components(package_path.parent / raw_path, raw_path)
                data = _read_relative_regular_fd(package_root_fd, raw_path, raw_path)
                if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                    raise ReleaseError(f"package changed while staging: {raw_path}")
                staged = _safe_package_path(root, raw_path)
                if staged == staged_package:
                    raise ReleaseError("package file path collides with staged package metadata")
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(data)
                bundle_paths[raw_path] = staged
        finally:
            os.close(package_root_fd)
        # Verification is performed against the private snapshot, never the
        # caller's mutable package directory.
        verify_package(staged_package, descriptor_path=staged_descriptor, source_host=source_host)
        package = load_evidence_package(staged_package, staged_descriptor)
        return VerifiedPackageSnapshot(
            temporary,
            staged_descriptor,
            descriptor,
            staged_package,
            package,
            bundle_paths,
            hashlib.sha256(package_bytes).hexdigest(),
        )
    except Exception:
        temporary.cleanup()
        raise


def pack_release(descriptor_path: Path, output: Path, workspace_root: Path | None = None) -> dict[str, Any]:
    descriptor = _load_json(descriptor_path, "descriptor")
    _validate_descriptor_shape(descriptor)
    if workspace_root is None:
        raise ReleaseError("pack requires an explicit workspace_root mapping")
    directory_fd = _open_directory_fd(output.parent)
    published: list[str] = []
    files: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    try:
        def exists_at(name: str) -> bool:
            try:
                os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                return True
            except FileNotFoundError:
                return False

        if exists_at(output.name):
            raise ReleaseError(f"refusing to overwrite existing output: {output}")
        bundle_names = [f"{output.stem}.{member['repo_id']}.bundle" for member in descriptor["members"]]
        if len(bundle_names) != len(set(bundle_names)):
            raise ReleaseError("descriptor members produce duplicate bundle sidecar names")
        if any(exists_at(name) for name in bundle_names):
            raise ReleaseError("refusing to overwrite existing bundle sidecar")
        with tempfile.TemporaryDirectory(prefix="agentops-release-pack-") as staging:
            staged_root = Path(staging)
            for member, bundle_name in zip(descriptor["members"], bundle_names):
                repo_id = member["repo_id"]
                repo = workspace_root / repo_id
                if not repo.is_dir():
                    raise ReleaseError(f"{repo_id}: repository is unavailable under explicit workspace_root")
                if output.resolve().is_relative_to(repo.resolve()):
                    raise ReleaseError("pack output must not be inside a declared member repository")
                if _git(repo, "cat-file", "-e", f"{member['commit']}^{{commit}}", check=False).returncode:
                    raise ReleaseError(f"{repo_id}: required commit is unavailable in declared repository")
                local_ref = _git(repo, "rev-parse", member["default_ref"], check=False)
                if local_ref.returncode or local_ref.stdout.strip() != member["commit"]:
                    raise ReleaseError(f"{repo_id}: declared default_ref does not select the descriptor commit")
                staged_bundle = staged_root / bundle_name
                # Export only the declared default branch.  --all can leak
                # unrelated refs and mutable local repository state.
                _git(repo, "bundle", "create", str(staged_bundle), member["default_ref"])
                data = _bounded_regular_bytes(staged_bundle, bundle_name)
                files.append({"path": bundle_name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
                members.append({"repo_id": repo_id, "commit": member["commit"], "bundle": bundle_name, "advertised_refs": [ref for _head, ref in _bundle_heads(staged_bundle)]})
            package = {"schema": SCHEMA_PACKAGE, "descriptor_sha256": hashlib.sha256(descriptor_path.read_bytes()).hexdigest(), "members": members, "files": files}
            for bundle_name in bundle_names:
                _copy_new_at(directory_fd, bundle_name, staged_root / bundle_name)
                published.append(bundle_name)
            _write_new_at(directory_fd, output.name, package)
            published.append(output.name)
            return package
    except Exception:
        for name in reversed(published):
            try:
                os.unlink(name, dir_fd=directory_fd)
            except OSError:
                pass
        raise
    finally:
        os.close(directory_fd)


def _validate_descriptor_shape(descriptor: Any) -> None:
    if not isinstance(descriptor, dict) or descriptor.get("schema") != SCHEMA_RELEASE:
        raise ReleaseError("invalid project-release/v1 descriptor")
    if set(descriptor) != {"schema", "project_id", "binding", "topology_digest", "members"}:
        raise ReleaseError("descriptor has missing or unsupported top-level fields")
    if not isinstance(descriptor.get("project_id"), str) or not descriptor["project_id"].strip():
        raise ReleaseError("descriptor project_id is required")
    try:
        if str(uuid.UUID(descriptor["project_id"])) != descriptor["project_id"].lower():
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise ReleaseError("descriptor project_id must be a canonical UUID") from error
    binding = descriptor.get("binding")
    if not isinstance(binding, dict) or set(binding) != {"repository", "commit", "path", "raw_sha256"}:
        raise ReleaseError("descriptor binding is malformed")
    _canonical_repo(binding["repository"], "binding.repository")
    _require_digest(binding["commit"], "binding.commit", 40)
    if binding["path"] != "project.toml":
        raise ReleaseError("binding.path must be normalized project.toml")
    _require_digest(binding["raw_sha256"], "binding.raw_sha256")
    _require_digest(descriptor["topology_digest"], "topology_digest")
    if not isinstance(descriptor.get("members"), list) or not descriptor["members"]:
        raise ReleaseError("descriptor members must be a non-empty array")
    seen: set[str] = set()
    ordered_members: list[dict[str, Any]] = []
    for member in descriptor["members"]:
        required = {"repo_id", "backlog", "render", "relationship", "access", "repository", "commit", "branch", "default_ref", "documents", "durability"}
        if not isinstance(member, dict) or set(member) != required:
            raise ReleaseError("descriptor member is malformed")
        if not isinstance(member["repo_id"], str) or not render_project.REPO_ID_RE.fullmatch(member["repo_id"]):
            raise ReleaseError("descriptor member repo_id is malformed")
        if member["repo_id"] in seen:
            raise ReleaseError(f"duplicate descriptor member: {member['repo_id']}")
        seen.add(member["repo_id"])
        if type(member["backlog"]) is not bool or member["render"] not in render_project.RENDER_MODES:
            raise ReleaseError(f"{member['repo_id']}: malformed backlog/render")
        if member["access"] not in render_project.MEMBER_ACCESS_MODES or not isinstance(member["relationship"], str) or not member["relationship"]:
            raise ReleaseError(f"{member['repo_id']}: malformed semantic member fields")
        _require_digest(member.get("commit", ""), f"{member['repo_id']}.commit", 40)
        if member["branch"] is not None and (not isinstance(member["branch"], str) or not member["branch"] or any(ord(c) < 32 for c in member["branch"])):
            raise ReleaseError(f"{member['repo_id']}: malformed branch")
        _canonical_repo(member.get("repository"), f"{member['repo_id']}.repository")
        _canonical_ref(member.get("default_ref"), f"{member['repo_id']}.default_ref")
        documents = member["documents"]
        if not isinstance(documents, dict) or set(documents) != {"required", "optional", "forbidden", "files", "bundle_sha256"}:
            raise ReleaseError(f"{member['repo_id']}: malformed document contract")
        groups: dict[str, list[str]] = {}
        for group in ("required", "optional", "forbidden"):
            value = documents[group]
            if not isinstance(value, list) or any(not isinstance(path, str) for path in value) or len(value) != len(set(value)):
                raise ReleaseError(f"{member['repo_id']}: malformed {group} document paths")
            groups[group] = []
            for path in value:
                try:
                    groups[group].append(render_project._document_path(path, f"{member['repo_id']}.documents.{group}"))
                except render_project.ProjectRenderError as error:
                    raise ReleaseError(str(error)) from error
        for left, right in (("required", "optional"), ("required", "forbidden"), ("optional", "forbidden")):
            overlap = set(groups[left]) & set(groups[right])
            if overlap:
                raise ReleaseError(f"{member['repo_id']}: contradictory document contracts: {sorted(overlap)}")
        _require_digest(documents["bundle_sha256"], f"{member['repo_id']}.documents.bundle_sha256")
        if not isinstance(documents["files"], list):
            raise ReleaseError(f"{member['repo_id']}: malformed document files")
        file_paths: set[str] = set()
        normalized_files: list[dict[str, Any]] = []
        for entry in documents["files"]:
            if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "bytes", "commit"}:
                raise ReleaseError(f"{member['repo_id']}: malformed document file entry")
            path = entry["path"]
            try:
                path = render_project._document_path(path, f"{member['repo_id']}.documents.files.path")
            except render_project.ProjectRenderError as error:
                raise ReleaseError(str(error)) from error
            if path in file_paths:
                raise ReleaseError(f"{member['repo_id']}: duplicate document file: {path}")
            file_paths.add(path)
            _require_digest(entry["sha256"], f"{member['repo_id']}.documents.files.sha256")
            if type(entry["bytes"]) is not int or entry["bytes"] < 0:
                raise ReleaseError(f"{member['repo_id']}: invalid document byte length")
            if entry["commit"] != member["commit"]:
                raise ReleaseError(f"{member['repo_id']}: document commit does not match member commit")
            normalized_files.append({"path": path, "sha256": entry["sha256"], "bytes": entry["bytes"], "commit": entry["commit"]})
        normalized_files.sort(key=lambda item: item["path"])
        for required_path in groups["required"]:
            if required_path not in file_paths:
                raise ReleaseError(f"{member['repo_id']}: required document is absent from descriptor files: {required_path}")
        if any(path in file_paths for path in groups["forbidden"]):
            raise ReleaseError(f"{member['repo_id']}: forbidden document is present in descriptor files")
        if digest(normalized_files) != documents["bundle_sha256"]:
            raise ReleaseError(f"{member['repo_id']}: document bundle digest mismatch")
        durability = member["durability"]
        if not isinstance(durability, dict) or set(durability) != {"kind", "ref", "target", "verified"} or durability.get("kind") not in {"remote-ref", "bundle"} or durability.get("target") != member["commit"] or durability.get("verified") is not True:
            raise ReleaseError(f"{member['repo_id']}: malformed durability proof")
        _canonical_ref(durability["ref"], f"{member['repo_id']}.durability.ref")
        ordered_members.append(member)
    if digest(ordered_members) != descriptor["topology_digest"]:
        raise ReleaseError("descriptor topology digest mismatch")
    if sum(
        1
        for member in ordered_members
        if member["repository"] == binding["repository"] and member["commit"] == binding["commit"]
    ) != 1:
        raise ReleaseError("descriptor binding does not identify exactly one home member")


def verify_package(
    package_path: Path,
    output: Path | None = None,
    *,
    descriptor_path: Path | None = None,
    source_host: str | None = None,
    verifier_host: str | None = None,
    verified_at: str | None = None,
    retention_mode: str = "pinned",
    retain_until: str | None = None,
) -> dict[str, Any]:
    package = _load_json(package_path, "package")
    _validate_package_shape(package)
    if descriptor_path is None:
        raise ReleaseError("package verification requires the bound descriptor")
    descriptor = _load_json(descriptor_path, "descriptor")
    _validate_descriptor_shape(descriptor)
    expected_descriptor = hashlib.sha256(descriptor_path.read_bytes()).hexdigest()
    if package["descriptor_sha256"] != expected_descriptor:
        raise ReleaseError("package descriptor digest does not match descriptor")
    descriptor_members = {member["repo_id"]: member for member in descriptor["members"]}
    package_members_by_id = {member["repo_id"]: member for member in package["members"]}
    if set(package_members_by_id) != set(descriptor_members):
        raise ReleaseError("package members do not correspond exactly to descriptor members")
    home_id = next(
        (
            member["repo_id"]
            for member in descriptor["members"]
            if member["repository"] == descriptor["binding"]["repository"]
            and member["commit"] == descriptor["binding"]["commit"]
        ),
        None,
    )
    root = package_path.parent.resolve()
    checked: dict[str, Path] = {}
    for entry in package["files"]:
        path = _safe_package_path(root, entry["path"])
        data = _bounded_regular_bytes(path, entry["path"])
        if len(data) != entry.get("bytes") or hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            raise ReleaseError(f"package file hash/length mismatch: {entry['path']}")
        checked[entry["path"]] = path
    package_members = package["members"]
    for member in package_members:
        bundle = member["bundle"]
        descriptor_member = descriptor_members[member["repo_id"]]
        if member["commit"] != descriptor_member["commit"]:
            raise ReleaseError(f"{member['repo_id']}: package commit does not match descriptor")
        actual = _verify_bundle(
            checked[bundle],
            member["commit"],
            documents=descriptor_member["documents"],
            descriptor=descriptor,
            verify_binding=member["repo_id"] == home_id,
        )
        actual_refs = [ref for _head, ref in actual]
        if actual_refs != member["advertised_refs"]:
            raise ReleaseError(f"{member['repo_id']}: advertised refs do not match bundle heads")
        if actual_refs != [descriptor_member["default_ref"]]:
            raise ReleaseError(f"{member['repo_id']}: bundle heads do not match descriptor default_ref")
    _verify_renderer_semantics(descriptor, checked, package_members)
    if retention_mode not in {"pinned", "expires"} or (retention_mode == "expires" and not retain_until) or (retention_mode == "pinned" and retain_until is not None):
        raise ReleaseError("retention must be pinned or expires with retain_until")
    source_host = _host_id(source_host, "source_host")
    verifier_host = _host_id(verifier_host or socket.gethostname(), "verifier_host")
    verified_at = _timestamp(verified_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "verified_at")
    if retention_mode == "expires":
        retain_until = _timestamp(retain_until, "retain_until")
        if datetime.fromisoformat(retain_until.replace("Z", "+00:00")) <= datetime.fromisoformat(verified_at.replace("Z", "+00:00")):
            raise ReleaseError("retain_until must be after verified_at")
    retention: dict[str, Any] = {"mode": retention_mode}
    if retain_until:
        retention["retain_until"] = retain_until
    receipt = {
        "schema": SCHEMA_RECEIPT,
        "descriptor_sha256": package.get("descriptor_sha256"),
        "package_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
        "source_host": source_host,
        "verifier_host": verifier_host,
        "verified_at": verified_at,
        "outcome": "verified",
        "members": [{"repo_id": member["repo_id"], "kind": "bundle", "result": "verified", "commit": member["commit"], "bundle_sha256": next(entry["sha256"] for entry in package["files"] if entry["path"] == member["bundle"])} for member in package_members],
        "replica_refs": [],
        "retention": retention,
    }
    if output is not None:
        _write_new(output, receipt)
    return receipt


def _validate_package_shape(package: Any) -> None:
    if not isinstance(package, dict) or set(package) != {"schema", "descriptor_sha256", "members", "files"} or package.get("schema") != SCHEMA_PACKAGE:
        raise ReleaseError("invalid project-evidence-package/v1 package")
    _require_digest(package["descriptor_sha256"], "package.descriptor_sha256")
    files = package["files"]
    members = package["members"]
    if not isinstance(files, list) or not files or not isinstance(members, list) or not members:
        raise ReleaseError("package members/files must be non-empty arrays")
    file_names: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "bytes"}:
            raise ReleaseError("malformed package file entry")
        if not isinstance(entry["path"], str):
            raise ReleaseError("package file path must be a string")
        # Validate the portable relative spelling before any caller can use
        # the path to open a sidecar.  This keeps verification and the
        # race-safe staging API on the same path policy.
        try:
            _safe_package_path(Path("/"), entry["path"])
        except ReleaseError:
            raise
        if entry["path"] == "package.json":
            raise ReleaseError("package metadata cannot also be a bundle file")
        if entry["path"] in file_names:
            raise ReleaseError(f"duplicate package file: {entry['path']}")
        file_names.add(entry["path"])
        _require_digest(entry["sha256"], f"package file {entry['path']}.sha256")
        if type(entry["bytes"]) is not int or entry["bytes"] < 0 or entry["bytes"] > MAX_PACKAGE_FILE_BYTES:
            raise ReleaseError(f"invalid package file length: {entry['path']}")
    member_ids: set[str] = set()
    bundles: set[str] = set()
    for member in members:
        if not isinstance(member, dict) or set(member) != {"repo_id", "commit", "bundle", "advertised_refs"}:
            raise ReleaseError("package member is malformed")
        if not isinstance(member["repo_id"], str) or member["repo_id"] in member_ids:
            raise ReleaseError("package member is malformed or duplicated")
        member_ids.add(member["repo_id"])
        _require_digest(member["commit"], f"{member['repo_id']}.commit", 40)
        bundle = member["bundle"]
        if not isinstance(bundle, str) or bundle in bundles or bundle not in file_names:
            raise ReleaseError(f"{member['repo_id']}: bundle is not a unique declared file")
        bundles.add(bundle)
        refs = member["advertised_refs"]
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs) or len(refs) != len(set(refs)):
            raise ReleaseError(f"{member['repo_id']}: malformed advertised refs")
        for ref in refs:
            _canonical_ref(ref, f"{member['repo_id']}.advertised_refs")
    if bundles != file_names:
        raise ReleaseError("package files and member bundles do not correspond exactly")


def _host_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HOST_ID.fullmatch(value) or any(ord(c) < 32 for c in value):
        raise ReleaseError(f"{label} must be a bounded host identifier")
    return value


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        raise ReleaseError(f"{label} must be an RFC3339 UTC timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReleaseError(f"{label} is not a valid timestamp") from error
    return value


def rebuild_plan(
    descriptor_path: Path,
    output: Path,
    package_path: Path | None = None,
    *,
    remote_verifier: Callable[[str, str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    descriptor = _load_json(descriptor_path, "descriptor")
    structural_error: str | None = None
    try:
        _validate_descriptor_shape(descriptor)
    except ReleaseError as error:
        structural_error = str(error)
        if not isinstance(descriptor, dict) or not isinstance(descriptor.get("members"), list):
            raise
    package = None
    package_error: str | None = None
    if package_path is not None:
        try:
            package = _load_json(package_path, "package")
            if not isinstance(package, dict) or package.get("descriptor_sha256") != hashlib.sha256(descriptor_path.read_bytes()).hexdigest():
                raise ReleaseError("package descriptor digest does not match rebuild descriptor")
            verify_package(package_path, descriptor_path=descriptor_path, source_host="rebuild-plan")
        except (OSError, UnicodeError, json.JSONDecodeError, ReleaseError) as error:
            package_error = str(error)
            package = None
    missing: list[dict[str, str]] = []
    verifier = remote_verifier or verify_remote
    home_id = next(
        (
            item["repo_id"]
            for item in descriptor["members"]
            if isinstance(item, dict)
            and item.get("repository") == descriptor.get("binding", {}).get("repository")
            and item.get("commit") == descriptor.get("binding", {}).get("commit")
        ),
        None,
    )
    for member in descriptor["members"]:
        if not isinstance(member, dict) or not isinstance(member.get("repo_id"), str):
            missing.append({"repo_id": "<malformed>", "reason": structural_error or "malformed descriptor member"})
            continue
        if structural_error:
            missing.append({"repo_id": member["repo_id"], "reason": structural_error})
            continue
        durability = member.get("durability", {})
        remote_error: str | None = None
        if durability.get("kind") == "remote-ref":
            try:
                if remote_verifier is None:
                    proof = verify_remote(
                        member.get("repository"),
                        member.get("default_ref"),
                        member.get("commit"),
                        documents=member["documents"],
                        descriptor=descriptor,
                        verify_binding=member["repo_id"] == home_id,
                    )
                else:
                    proof = verifier(member.get("repository"), member.get("default_ref"), member.get("commit"))
                if (
                    proof.get("verified") is True
                    and proof.get("repository") == member.get("repository")
                    and proof.get("ref") == member.get("default_ref")
                    and proof.get("target") == member.get("commit")
                ):
                    continue
                raise ReleaseError("remote proof shape did not match descriptor")
            except Exception as error:
                remote_error = f"remote verification failed: {error}"
        package_member = next((item for item in (package or {}).get("members", []) if item.get("repo_id") == member["repo_id"] and item.get("commit") == member["commit"]), None)
        if package_member is None:
            reason = "; ".join(item for item in (remote_error, package_error or "missing verified remote-ref or package evidence") if item)
            missing.append({"repo_id": member["repo_id"], "reason": reason})
    plan = {"schema": "project-rebuild-plan/v1", "descriptor_sha256": hashlib.sha256(descriptor_path.read_bytes()).hexdigest(), "ready": not missing, "missing": missing, "members": [member["repo_id"] for member in descriptor["members"]]}
    _write_new(output, plan)
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--project", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    verify = commands.add_parser("verify", aliases=["verify-remote"])
    verify.add_argument("--repository", required=True)
    verify.add_argument("--ref", required=True)
    verify.add_argument("--commit", required=True)
    verify.add_argument("--output", required=True, type=Path)
    pack = commands.add_parser("pack")
    pack.add_argument("--descriptor", required=True, type=Path)
    pack.add_argument("--output", required=True, type=Path)
    pack.add_argument("--workspace-root", required=True, type=Path)
    package = commands.add_parser("verify-package")
    package.add_argument("--package", required=True, type=Path)
    package.add_argument("--descriptor", required=True, type=Path)
    package.add_argument("--output", required=True, type=Path)
    package.add_argument("--source-host", required=True)
    package.add_argument("--verifier-host")
    package.add_argument("--verified-at")
    package.add_argument("--retention-mode", choices=("pinned", "expires"), default="pinned")
    package.add_argument("--retain-until")
    plan = commands.add_parser("rebuild-plan")
    plan.add_argument("--descriptor", required=True, type=Path)
    plan.add_argument("--output", required=True, type=Path)
    plan.add_argument("--package", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            value = create_release(args.project, args.output)
        elif args.command in {"verify", "verify-remote"}:
            value = verify_remote(args.repository, args.ref, args.commit)
            _write_new(args.output, value)
        elif args.command == "pack":
            value = pack_release(args.descriptor, args.output, args.workspace_root)
        elif args.command == "verify-package":
            value = verify_package(
                args.package,
                args.output,
                descriptor_path=args.descriptor,
                source_host=args.source_host,
                verifier_host=args.verifier_host,
                verified_at=args.verified_at,
                retention_mode=args.retention_mode,
                retain_until=args.retain_until,
            )
        else:
            value = rebuild_plan(args.descriptor, args.output, args.package)
        print(json.dumps(_canonical(value), indent=2, ensure_ascii=False))
    except (OSError, ReleaseError, render_project.ProjectRenderError) as error:
        print(f"error: {error}", file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
