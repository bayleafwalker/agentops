#!/usr/bin/env python3
"""Create and synchronize rebuildable multi-repository project folders."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tempfile
import uuid

import fcntl

import render_project
import project_release


TOOL_ID = "agentops-project-folder/v2"
TOOL_VERSION = "2"
MARKER_NAME = ".agentops-project-folder.json"
CONTEXT_NAME = "project.context.json"
MEMBERS_DIRECTORY = "members"
LEASE_NAME = ".agentops-project-folder.lease"
LEASE_LOCK_NAME = ".agentops-project-folder.lease.lock"
LEASE_SCHEMA = "agentops-project-folder-lease/v1"
BLOCKED_STATUSES = {
    "dirty", "non-fast-forward", "unexpected-branch", "unexpected-head",
    "unexpected-member", "missing-member", "missing-worktree", "unavailable-ref",
    "invalid-worktree", "foreign-worktree",
}
# These paths are local runtime state, never project inputs.  They are
# explicitly admitted at the instance root so workers and evidence staging do
# not make a derived folder uninspectable.  Their contents are intentionally
# excluded from context_sources and all provenance digests.
MANAGED_RUNTIME_PATHS = frozenset({
    ".session", ".workers", ".cache", "cache", ".evidence", ".evidence-staging",
    "evidence", "evidence-staging",
})
INSTANCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class ProjectFolderError(ValueError):
    """Raised when a materialized project folder cannot be managed safely."""


@dataclass(frozen=True)
class WorktreeState:
    repo_id: str
    primary_repo: Path
    worktree: Path
    branch: str
    default_ref: str
    head: str
    status: str
    detail: str = ""
    effective_mode: str = "exclusive-write"

    @property
    def blocked(self) -> bool:
        return self.status in BLOCKED_STATUSES


@dataclass(frozen=True)
class MaterializationResult:
    command: str
    folder: Path
    members: tuple[WorktreeState, ...]
    render_statuses: tuple[render_project.MemberStatus, ...]
    drift: tuple[str, ...] = ()

    @property
    def blocked(self) -> bool:
        return any(member.blocked for member in self.members) or bool(self.drift)


def _git(
    repo: Path,
    *arguments: str,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        git_environment = os.environ.copy()
        # Avoid optional index locks while inspecting worktrees.  Required
        # ref/worktree locks remain enforced by Git for mutating operations.
        git_environment["GIT_OPTIONAL_LOCKS"] = "0"
        if env:
            git_environment.update(env)
        result = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=git_environment,
        )
    except FileNotFoundError as error:
        raise ProjectFolderError(
            "git is required for project-folder operations"
        ) from error
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise ProjectFolderError(f"{repo}: git {' '.join(arguments)}: {detail}")
    return result


def _atomic_write(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise ProjectFolderError(f"refusing to replace symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _atomic_write_private(path: Path, content: bytes) -> None:
    """Atomically write a local-only record with owner-only permissions."""
    if path.is_symlink():
        raise ProjectFolderError(f"refusing to replace symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


@contextmanager
def _lease_lock(folder: Path):
    """Serialize lease changes locally; this is deliberately not distributed."""
    lock_path = folder / LEASE_LOCK_NAME
    if lock_path.is_symlink():
        raise ProjectFolderError(f"lease lock must not be a symlink: {lock_path}")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _binding_provenance(project: render_project.ProjectBinding) -> tuple[str, str]:
    """Return the local binding revision and bytes digest.

    The digest is deliberately of the binding file, rather than an implicit
    working-tree state.  It makes a materialization inspectable without
    pretending that an absolute local path is portable identity.
    """
    commit = _git(project.home_root, "rev-parse", "HEAD").stdout.strip()
    digest = hashlib.sha256(project.project_path.read_bytes()).hexdigest()
    return commit, digest


def _marker(
    project: render_project.ProjectBinding, *, instance: str, mode: str,
    readonly_enforced: bool = False,
) -> dict[str, object]:
    commit, digest = _binding_provenance(project)
    return {
        "schema_version": 2,
        "tool": TOOL_ID,
        "tool_version": TOOL_VERSION,
        "project_id": project.project_id,
        "instance_id": instance,
        "mode": mode,
        # This is intentionally an instance property, rather than a project
        # property: one host may use a convenience read-only checkout while
        # another only observes the shared-read operational contract.
        "readonly_enforced": readonly_enforced,
        "canonical_project": str(project.project_path),
        "source_binding_commit": commit,
        "source_binding_sha256": digest,
    }


def _resolved_readonly_enforcement(folder: Path, requested: bool | None) -> bool:
    """Resolve opt-in enforcement without following an untrusted marker path.

    Existing v2 instances predate this property and retain the compatible
    operational-only behaviour.  A caller may opt in only at setup time.
    """
    if requested is not None:
        return requested
    marker = folder.expanduser().absolute() / MARKER_NAME
    if not marker.exists():
        return False
    if marker.is_symlink() or not marker.is_file():
        raise ProjectFolderError(f"project-folder marker must be a regular file: {marker}")
    try:
        value = json.loads(marker.read_text(encoding="utf-8")).get("readonly_enforced", False)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectFolderError(f"cannot read project-folder marker: {error}") from error
    if not isinstance(value, bool):
        raise ProjectFolderError("project-folder marker readonly_enforced must be boolean")
    return value


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _release_marker(path: Path) -> dict[str, object] | None:
    marker = path / MARKER_NAME
    if not marker.is_file() or marker.is_symlink():
        return None
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    release = value.get("release") if isinstance(value, dict) else None
    return release if isinstance(release, dict) else None


def _prepare_folder(
    project: render_project.ProjectBinding,
    folder: Path,
    *,
    require_existing: bool,
    instance: str,
    mode: str,
    readonly_enforced: bool = False,
    mutate: bool = True,
) -> Path:
    requested = folder.expanduser().absolute()
    if requested.is_symlink():
        raise ProjectFolderError(f"project folder must not be a symlink: {requested}")
    folder = requested.resolve()
    if folder == Path("/") or folder == project.workspace_root:
        raise ProjectFolderError(f"refusing broad project-folder target: {folder}")
    for member in project.members:
        if folder == member.repo_root or _is_within(folder, member.repo_root):
            raise ProjectFolderError(
                f"project folder must not be inside member repository {member.repo_root}"
            )
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ProjectFolderError(f"project folder must be a real directory: {folder}")
    if require_existing and not folder.is_dir():
        raise ProjectFolderError(
            f"project folder does not exist; run setup first: {folder}"
        )
    if not folder.exists():
        if not mutate:
            raise ProjectFolderError(
                f"project folder does not exist; run setup first: {folder}"
            )
        folder.mkdir(parents=True, exist_ok=True)
    git_path = folder / ".git"
    if git_path.is_symlink() or (
        git_path.exists() and not (git_path.is_dir() and not any(git_path.iterdir()))
    ):
        raise ProjectFolderError(f"project folder must not itself be a git repository: {folder}")

    marker_path = folder / MARKER_NAME
    if marker_path.is_symlink():
        raise ProjectFolderError(
            f"project-folder marker must not be a symlink: {marker_path}"
        )
    for name in ("AGENTS.md", CONTEXT_NAME):
        managed = folder / name
        if managed.is_symlink() or (managed.exists() and not managed.is_file()):
            raise ProjectFolderError(
                f"derived context path must be a regular file: {managed}"
            )
    entries = {entry.name for entry in folder.iterdir()}
    bootstrap_allowed = MANAGED_RUNTIME_PATHS | {".git"}
    if entries and not marker_path.is_file() and not entries.issubset(bootstrap_allowed):
        raise ProjectFolderError(
            f"refusing non-empty folder without {MARKER_NAME}: {folder}"
        )
    allowed = {
        MARKER_NAME,
        CONTEXT_NAME,
        "AGENTS.md",
        MEMBERS_DIRECTORY,
        ".git",  # permitted only as an empty placeholder; see check above
        LEASE_NAME,
        LEASE_LOCK_NAME,
    }
    allowed.update(MANAGED_RUNTIME_PATHS)
    unexpected = sorted(entries - allowed)
    if unexpected:
        raise ProjectFolderError(
            f"project folder contains non-derived path(s): {', '.join(unexpected)}"
        )
    for name in MANAGED_RUNTIME_PATHS:
        runtime_path = folder / name
        if runtime_path.is_symlink() or (runtime_path.exists() and not runtime_path.is_dir()):
            raise ProjectFolderError(f"managed runtime path must be a real directory: {runtime_path}")
    release_marker_exists = False
    if marker_path.is_file() and not marker_path.is_symlink():
        try:
            release_marker_probe = json.loads(marker_path.read_text(encoding="utf-8"))
            release_marker_exists = isinstance(release_marker_probe, dict) and isinstance(release_marker_probe.get("release"), dict)
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    try:
        if release_marker_exists:
            raise ProjectFolderError("release marker uses descriptor provenance")
        expected_marker = _marker(
            project, instance=instance, mode=mode, readonly_enforced=readonly_enforced
        )
    except ProjectFolderError:
        try:
            release_marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProjectFolderError(f"cannot read release-pinned marker: {error}") from error
        if not isinstance(release_marker, dict) or not isinstance(release_marker.get("release"), dict):
            raise ProjectFolderError("release-pinned marker has invalid provenance")
        expected_marker = {
            key: release_marker.get(key)
            for key in (
                "schema_version", "tool", "tool_version", "project_id", "instance_id",
                "mode", "readonly_enforced", "canonical_project",
                "source_binding_commit", "source_binding_sha256", "release",
            )
        }
        expected_marker["readonly_enforced"] = readonly_enforced
    if marker_path.exists():
        try:
            current_marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProjectFolderError(
                f"cannot read project-folder marker: {error}"
            ) from error
        # v1 folders were single-instance exclusive-write folders.  Upgrade
        # them in-place only for the compatible default invocation.
        legacy = {
            "tool": "agentops-project-folder/v1",
            "project_id": project.project_id,
            "canonical_project": str(project.project_path),
        }
        if current_marker == legacy and instance == "default" and mode == "exclusive-write":
            if mutate:
                _atomic_write(marker_path, _json_bytes(expected_marker))
        else:
            # Missing enforcement is the compatible v2 default.  Normalize
            # only for comparison so the next mutating operation records it.
            normalized_marker = dict(current_marker)
            normalized_marker.setdefault("readonly_enforced", False)
            if isinstance(current_marker.get("release"), dict):
                expected_marker["release"] = current_marker["release"]
            if any(
                normalized_marker.get(key) != expected_marker[key]
            for key in ("schema_version", "tool", "project_id", "instance_id", "mode", "canonical_project")
            ) or normalized_marker.get("readonly_enforced") != readonly_enforced:
                raise ProjectFolderError(
                    f"project-folder marker does not match {project.project_path}"
                )
            if mutate and current_marker != expected_marker:
                _atomic_write(marker_path, _json_bytes(expected_marker))
    elif mutate:
        _atomic_write(marker_path, _json_bytes(expected_marker))
    else:
        raise ProjectFolderError(f"project folder has no {MARKER_NAME}: {folder}")
    members_root = folder / MEMBERS_DIRECTORY
    if members_root.is_symlink():
        raise ProjectFolderError(
            f"members directory must not be a symlink: {members_root}"
        )
    if members_root.exists() and not members_root.is_dir():
        raise ProjectFolderError(f"members path must be a directory: {members_root}")
    if mutate:
        members_root.mkdir(exist_ok=True)
    elif not members_root.is_dir():
        raise ProjectFolderError(f"members path does not exist: {members_root}")
    return folder


def _lease_identity(
    *, host: str | None = None, pid: str | None = None, runtime_session_id: str | None = None
) -> dict[str, object]:
    """Resolve an explicit lease holder identity from args, env, then this process."""
    selected_host = host or os.environ.get("AGENTOPS_PROJECT_LEASE_HOST") or socket.gethostname()
    selected_pid = pid or os.environ.get("AGENTOPS_PROJECT_LEASE_PID") or str(os.getpid())
    selected_runtime = (
        runtime_session_id
        if runtime_session_id is not None
        else os.environ.get("AGENTOPS_PROJECT_RUNTIME_SESSION_ID")
    )
    if not selected_host:
        raise ProjectFolderError("lease holder host must not be empty")
    try:
        parsed_pid = int(selected_pid)
    except ValueError as error:
        raise ProjectFolderError("lease holder pid must be an integer") from error
    if parsed_pid < 1:
        raise ProjectFolderError("lease holder pid must be positive")
    identity: dict[str, object] = {"host": selected_host, "pid": parsed_pid}
    if selected_runtime:
        identity["runtime_session_id"] = selected_runtime
    return identity


def _read_lease(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ProjectFolderError(f"lease record must be a regular file: {path}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectFolderError(f"cannot read lease record: {error}") from error
    required = {"schema", "project_id", "instance_id", "host", "pid", "acquired_at", "heartbeat_at"}
    if not isinstance(record, dict) or not required.issubset(record):
        raise ProjectFolderError(f"invalid lease record: {path}")
    if record["schema"] != LEASE_SCHEMA:
        raise ProjectFolderError(f"unsupported lease record schema: {record['schema']}")
    return record


def _lease_matches(record: dict[str, object], identity: dict[str, object]) -> bool:
    expected = {key: record.get(key) for key in ("host", "pid", "runtime_session_id") if key in record}
    return expected == identity


def lease(
    project: render_project.ProjectBinding,
    folder: Path,
    *,
    action: str,
    instance: str = "default",
    mode: str = "exclusive-write",
    host: str | None = None,
    pid: str | None = None,
    runtime_session_id: str | None = None,
) -> dict[str, object] | None:
    """Manage an advisory lease local to one materialization instance.

    Leases never expire and are never stolen automatically.  They coordinate
    only processes that can see this local filesystem; they are not a
    cross-host lock or authority record.
    """
    if action not in {"acquire", "heartbeat", "release", "status"}:
        raise ProjectFolderError(f"unsupported lease action: {action}")
    if not INSTANCE_RE.fullmatch(instance):
        raise ProjectFolderError("instance must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    if mode not in {"shared-read", "exclusive-write"}:
        raise ProjectFolderError(f"unsupported instance mode: {mode}")
    readonly_enforced = _resolved_readonly_enforcement(folder, None)
    folder = _prepare_folder(
        project, folder, require_existing=True, instance=instance, mode=mode,
        readonly_enforced=readonly_enforced, mutate=False,
    )
    lease_path = folder / LEASE_NAME
    with _lease_lock(folder):
        # A destroy may have run after the first validation while this caller
        # waited for the advisory lock.  Revalidate under the lock before any
        # lease mutation so a waiting holder cannot revive a removed instance.
        _prepare_folder(
            project, folder, require_existing=True, instance=instance, mode=mode,
            readonly_enforced=readonly_enforced, mutate=False,
        )
        existing = _read_lease(lease_path)
        if action == "status":
            return existing
        identity = _lease_identity(host=host, pid=pid, runtime_session_id=runtime_session_id)
        if action == "acquire":
            if existing is not None:
                raise ProjectFolderError(f"instance already has a local lease: {lease_path}")
            now = datetime.now(timezone.utc).isoformat()
            record: dict[str, object] = {
                "schema": LEASE_SCHEMA,
                "scope": "local-only",
                "project_id": project.project_id,
                "instance_id": instance,
                **identity,
                "acquired_at": now,
                "heartbeat_at": now,
            }
            _atomic_write_private(lease_path, _json_bytes(record))
            return record
        if existing is None:
            raise ProjectFolderError(f"instance has no local lease: {lease_path}")
        if existing.get("project_id") != project.project_id or existing.get("instance_id") != instance:
            raise ProjectFolderError(f"lease record does not match this project instance: {lease_path}")
        if not _lease_matches(existing, identity):
            raise ProjectFolderError("lease holder identity does not match; refusing local lease mutation")
        if action == "heartbeat":
            updated = dict(existing)
            updated["heartbeat_at"] = datetime.now(timezone.utc).isoformat()
            _atomic_write_private(lease_path, _json_bytes(updated))
            return updated
        lease_path.unlink()
        return None


def _fetch_and_prune(repo: Path) -> None:
    _git(repo, "fetch", "--prune", "origin")
    _git(repo, "worktree", "prune")


def _default_ref(repo: Path) -> str:
    symbolic = _git(
        repo,
        "symbolic-ref",
        "--quiet",
        "--short",
        "refs/remotes/origin/HEAD",
        check=False,
    )
    if symbolic.returncode == 0 and symbolic.stdout.strip():
        return symbolic.stdout.strip()
    for candidate in ("origin/main", "origin/master"):
        if (
            _git(
                repo,
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/remotes/{candidate}",
                check=False,
            ).returncode
            == 0
        ):
            return candidate
    raise ProjectFolderError(
        f"{repo}: cannot resolve remote default branch from origin/HEAD, origin/main, or origin/master"
    )


def _materialized_branch(
    project: render_project.ProjectBinding, instance: str, repo_id: str
) -> str:
    return f"agentops-project/{project.project_id}/{instance}/{repo_id}"


def _effective_member_mode(
    member: render_project.MemberBinding, instance_mode: str
) -> str:
    """Return the actual worktree mode for one member.

    A reference member is deliberately detached even in a writable project
    instance.  ``access`` is therefore a materialization boundary, rather
    than merely context metadata.
    """
    if instance_mode == "shared-read" or member.access == "reference":
        return "shared-read"
    return "exclusive-write"


def _common_git_dir(repo: Path) -> Path:
    result = _git(repo, "rev-parse", "--git-common-dir")
    value = Path(result.stdout.strip())
    return (value if value.is_absolute() else repo / value).resolve()


def _validate_existing_worktree(
    primary: Path,
    worktree: Path,
    branch: str,
    *,
    mode: str,
    expected_head: str | None = None,
) -> None:
    if worktree.is_symlink() or not worktree.is_dir():
        raise ProjectFolderError(
            f"member worktree must be a real directory: {worktree}"
        )
    if _common_git_dir(worktree) != _common_git_dir(primary):
        raise ProjectFolderError(
            f"member path is not a worktree of {primary}: {worktree}"
        )
    current = _git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if mode == "shared-read":
        if current.returncode == 0:
            raise ProjectFolderError(f"{worktree}: shared-read worktree must be detached")
        if expected_head and _git(worktree, "rev-parse", "HEAD").stdout.strip() != expected_head:
            raise ProjectFolderError(
                f"{worktree}: shared-read worktree does not match recorded default ref"
            )
        return
    if current.returncode != 0 or current.stdout.strip() != branch:
        actual = current.stdout.strip() or "detached"
        raise ProjectFolderError(
            f"{worktree}: expected materialized branch {branch}, found {actual}"
        )


def _ensure_worktree(
    project: render_project.ProjectBinding,
    member: render_project.MemberBinding,
    folder: Path,
    default_ref: str,
    *,
    instance: str,
    mode: str,
    start_ref: str | None = None,
) -> tuple[Path, str]:
    worktree = folder / MEMBERS_DIRECTORY / member.repo_id
    branch = _materialized_branch(project, instance, member.repo_id)
    if worktree.exists() or worktree.is_symlink():
        _validate_existing_worktree(
            member.repo_root,
            worktree,
            branch,
            mode=mode,
            # Existing detached/reference worktrees deliberately retain the
            # commit that was recorded when they were created.  A later fetch
            # must report drift, never move them implicitly.
            expected_head=None,
        )
        if mode == "exclusive-write":
            _git(worktree, "branch", f"--set-upstream-to={default_ref}", branch)
        return worktree, branch

    worktree.parent.mkdir(parents=True, exist_ok=True)
    checkout_ref = start_ref or default_ref
    if mode == "shared-read":
        _git(member.repo_root, "worktree", "add", "--detach", str(worktree), checkout_ref)
        return worktree, branch
    branch_exists = (
        _git(
            member.repo_root,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
            check=False,
        ).returncode
        == 0
    )
    if branch_exists:
        _git(member.repo_root, "worktree", "add", str(worktree), branch)
    else:
        _git(
            member.repo_root,
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree),
            checkout_ref,
        )
    _git(worktree, "branch", f"--set-upstream-to={default_ref}", branch)
    return worktree, branch


def _worktree_state(
    member: render_project.MemberBinding,
    worktree: Path,
    branch: str,
    default_ref: str,
    *,
    mode: str,
    advance: bool,
) -> WorktreeState:
    current = _git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    head = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    if mode == "shared-read":
        if current.returncode == 0:
            return WorktreeState(
                member.repo_id, member.repo_root, worktree, branch, default_ref,
                head, "unexpected-branch", "shared-read worktree must be detached", mode,
            )
        target = _git(worktree, "rev-parse", default_ref).stdout.strip()
        if head != target:
            ancestor = _git(worktree, "merge-base", "--is-ancestor", head, target, check=False)
            if ancestor.returncode == 0:
                return WorktreeState(member.repo_id, member.repo_root, worktree, branch, default_ref, head, "behind", f"detached {head} is behind {default_ref} ({target})", mode)
            if ancestor.returncode != 1:
                detail = ancestor.stderr.strip() or ancestor.stdout.strip() or "merge-base failed"
                raise ProjectFolderError(
                    f"{worktree}: cannot compare {head} with {default_ref}: {detail}"
                )
            return WorktreeState(member.repo_id, member.repo_root, worktree, branch, default_ref, head, "unexpected-head", f"detached {head} does not match {default_ref} ({target})", mode)
        dirty = _git(worktree, "status", "--porcelain", "--untracked-files=all").stdout.strip()
        return WorktreeState(member.repo_id, member.repo_root, worktree, branch, default_ref, head, "dirty" if dirty else "current", dirty, mode)
    if current.returncode != 0 or current.stdout.strip() != branch:
        actual = current.stdout.strip() or "detached"
        return WorktreeState(
            member.repo_id,
            member.repo_root,
            worktree,
            branch,
            default_ref,
            head,
            "unexpected-branch",
            f"expected {branch}; found {actual}", mode,
        )
    dirty = _git(
        worktree, "status", "--porcelain", "--untracked-files=all"
    ).stdout.strip()
    if dirty:
        return WorktreeState(
            member.repo_id,
            member.repo_root,
            worktree,
            branch,
            default_ref,
            head,
            "dirty",
            dirty, mode,
        )

    target = _git(worktree, "rev-parse", default_ref).stdout.strip()
    if head == target:
        return WorktreeState(
            member.repo_id,
            member.repo_root,
            worktree,
            branch,
            default_ref,
            head,
            "current", "", mode,
        )
    ancestor = _git(worktree, "merge-base", "--is-ancestor", head, target, check=False)
    if ancestor.returncode == 0:
        if not advance:
            return WorktreeState(
                member.repo_id, member.repo_root, worktree, branch, default_ref,
                head, "behind", f"local {head} is behind {default_ref} ({target})", mode,
            )
        _git(worktree, "merge", "--ff-only", default_ref)
        updated = _git(worktree, "rev-parse", "HEAD").stdout.strip()
        return WorktreeState(
            member.repo_id,
            member.repo_root,
            worktree,
            branch,
            default_ref,
            updated,
            "updated", "", mode,
        )
    if ancestor.returncode != 1:
        detail = (
            ancestor.stderr.strip() or ancestor.stdout.strip() or "merge-base failed"
        )
        raise ProjectFolderError(
            f"{worktree}: cannot compare {head} with {default_ref}: {detail}"
        )
    return WorktreeState(
        member.repo_id,
        member.repo_root,
        worktree,
        branch,
        default_ref,
        head,
        "non-fast-forward",
        f"local {head} cannot fast-forward to {default_ref} ({target})", mode,
    )


def _pinned_worktree_state(
    member: render_project.MemberBinding,
    worktree: Path,
    branch: str,
    default_ref: str,
    commit: str,
    *,
    mode: str,
) -> WorktreeState:
    current = _git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    head = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    if mode == "shared-read" and current.returncode == 0:
        return WorktreeState(member.repo_id, member.repo_root, worktree, branch, default_ref, head, "unexpected-branch", "pinned shared-read worktree must be detached", mode)
    if mode == "exclusive-write" and (current.returncode != 0 or current.stdout.strip() != branch):
        return WorktreeState(member.repo_id, member.repo_root, worktree, branch, default_ref, head, "unexpected-branch", f"expected {branch}; found {current.stdout.strip() or 'detached'}", mode)
    dirty = _git(worktree, "status", "--porcelain", "--untracked-files=all").stdout.strip()
    if dirty:
        return WorktreeState(member.repo_id, member.repo_root, worktree, branch, default_ref, head, "dirty", dirty, mode)
    if head != commit:
        return WorktreeState(member.repo_id, member.repo_root, worktree, branch, default_ref, head, "unexpected-head", f"expected pinned commit {commit}", mode)
    return WorktreeState(member.repo_id, member.repo_root, worktree, branch, default_ref, head, "current", "", mode)


def _set_shared_read_worktree_writable(worktree: Path, *, writable: bool) -> None:
    """Apply local shared-read permissions without traversing symlinks.

    A linked worktree's `.git` is a regular pointer file; its common Git
    directory remains outside this tree and is never chmodded here.  The
    operation deliberately only changes write bits, preserving executable
    bits and avoiding an attempt to reconstruct repository file modes.
    """
    if worktree.is_symlink() or not worktree.is_dir():
        raise ProjectFolderError(f"member worktree must be a real directory: {worktree}")
    root = worktree.resolve()
    if root != worktree.absolute():
        raise ProjectFolderError(f"member worktree must not resolve through a symlink: {worktree}")

    def chmod_path(path: Path, *, directory: bool) -> None:
        if path.is_symlink():
            return
        try:
            mode = path.stat(follow_symlinks=False).st_mode
        except OSError as error:
            raise ProjectFolderError(f"cannot inspect shared-read member path {path}: {error}") from error
        if writable:
            # Minimum owner permissions needed for Git's checked removal;
            # do not broaden group/other access or alter executable bits.
            target = mode | stat.S_IWUSR
            if directory:
                target |= stat.S_IXUSR
        else:
            target = mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        try:
            os.chmod(path, target, follow_symlinks=False)
        except OSError as error:
            raise ProjectFolderError(f"cannot change shared-read member path {path}: {error}") from error

    # os.walk does not follow directory symlinks.  Chmod only paths emitted
    # beneath a verified worktree root, and leave every symlink untouched.
    for directory, directories, files in os.walk(root, topdown=False, followlinks=False):
        current = Path(directory)
        if not _is_within(current, root):
            raise ProjectFolderError(f"refusing path outside shared-read worktree: {current}")
        for name in files:
            chmod_path(current / name, directory=False)
        for name in directories:
            candidate = current / name
            if not candidate.is_symlink():
                chmod_path(candidate, directory=True)
        chmod_path(current, directory=True)


def _enforce_shared_read_worktrees(states: tuple[WorktreeState, ...]) -> None:
    """Freeze only clean, valid shared-read members after context generation."""
    for state in states:
        dirty = _git(
            state.worktree, "status", "--porcelain", "--untracked-files=all"
        ).stdout.strip()
        if dirty:
            raise ProjectFolderError(
                f"refusing shared-read filesystem enforcement for dirty {state.repo_id}"
            )
        _validate_existing_worktree(
            state.primary_repo, state.worktree, state.branch,
            mode="shared-read", expected_head=state.head,
        )
        _set_shared_read_worktree_writable(state.worktree, writable=False)


def _resolved_context(
    project: render_project.ProjectBinding,
    folder: Path,
    command: str,
    instance: str,
    mode: str,
    readonly_enforced: bool,
    states: tuple[WorktreeState, ...],
    render_statuses: tuple[render_project.MemberStatus, ...],
    release_provenance: dict[str, object] | None = None,
) -> dict[str, object]:
    binding_by_id = {member.repo_id: member for member in project.members}
    render_by_id = {status.repo_id: status for status in render_statuses}
    members: list[dict[str, object]] = []
    for state in states:
        binding = binding_by_id[state.repo_id]
        render_status = render_by_id.get(state.repo_id)
        members.append(
            {
                "repo_id": state.repo_id,
                "primary_repo": str(state.primary_repo),
                "worktree": str(state.worktree.relative_to(folder)),
                "branch": state.branch,
                "effective_mode": state.effective_mode,
                "reference": binding.access == "reference",
                "default_ref": state.default_ref,
                "head": state.head,
                "sync_status": state.status,
                "sync_detail": state.detail or None,
                "dirty_after_render": bool(
                    _git(
                        state.worktree, "status", "--porcelain", "--untracked-files=all"
                    ).stdout.strip()
                ),
                "backlog": binding.backlog,
                "render": binding.render,
                "relationship": binding.relationship,
                "access": binding.access,
                "render_status": (
                    {
                        "generated": render_status.generated,
                        "pointer": render_status.pointer,
                    }
                    if render_status is not None
                    else None
                ),
                "path_notes": list(binding.path_notes),
            }
        )
    context_sources = _context_sources(project, folder, states)
    context_bundle_sha256 = _context_bundle_sha256(context_sources)
    result = {
        "schema_version": 2,
        "tool": TOOL_ID,
        "command": command,
        "project_id": project.project_id,
        "instance_id": instance,
        "mode": mode,
        "readonly_enforced": readonly_enforced,
        "display_name": project.display_name,
        "home_repo": project.home_repo,
        "canonical_project": str(project.project_path),
        "source_binding_commit": (
            release_provenance["binding"]["commit"] if release_provenance else _binding_provenance(project)[0]
        ),
        "source_binding_sha256": (
            release_provenance["binding"]["raw_sha256"] if release_provenance else _binding_provenance(project)[1]
        ),
        "context_bundle_sha256": context_bundle_sha256,
        "context_sources": context_sources,
        "folder": str(folder),
        "members": members,
    }
    if release_provenance is not None:
        result["release"] = release_provenance
    return result


def _source_record(
    *,
    scope: str,
    kind: str,
    path: Path,
    folder: Path,
    source_commit: str | None = None,
    member_id: str | None = None,
    applies_to: tuple[str, ...] = (),
) -> dict[str, object]:
    """Describe one actual context input without depending on discovery rules.

    Paths inside an instance are deliberately relative to the instance.  Paths
    outside it (the host environment file) stay absolute so an explanation is
    useful even after the instance has moved.
    """
    if path.is_symlink() or not path.is_file():
        raise ProjectFolderError(f"context source must be a regular file: {path}")
    record: dict[str, object] = {
        "scope": scope,
        "kind": kind,
        "path": str(path.relative_to(folder)) if _is_within(path, folder) else str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    if source_commit is not None:
        record["source_commit"] = source_commit
    if member_id is not None:
        record["member_id"] = member_id
    if applies_to:
        record["applies_to"] = list(applies_to)
    return record


def _context_sources(
    project: render_project.ProjectBinding,
    folder: Path,
    states: tuple[WorktreeState, ...],
) -> list[dict[str, object]]:
    """Return deterministic provenance for the context files actually present.

    Project inputs are resolved from the home *member worktree*, rather than
    from the local anchor checkout.  This is especially important for
    shared-read instances, whose detached member commits are the only files a
    reader is meant to rely on.
    """
    by_id = {state.repo_id: state for state in states}
    home = by_id[project.home_repo]
    sources: list[dict[str, object]] = []
    environment_agents = project.workspace_root / "AGENTS.md"
    if environment_agents.exists():
        sources.append(_source_record(
            scope="environment", kind="agents", path=environment_agents, folder=folder
        ))

    instance_project = render_project.load_project(
        home.worktree / "project.toml", workspace_root=folder / MEMBERS_DIRECTORY
    )
    sources.append(_source_record(
        scope="project", kind="binding", path=instance_project.project_path,
        folder=folder, source_commit=home.head, member_id=home.repo_id,
    ))
    fragments = render_project.load_fragments(instance_project)
    for fragment in fragments:
        applies_to = tuple(
            member.repo_id for member in instance_project.members
            if member.render in fragment.levels
        )
        if applies_to:
            sources.append(_source_record(
                scope="project", kind="project-source", path=fragment.path,
                folder=folder, source_commit=home.head, member_id=home.repo_id,
                applies_to=applies_to,
            ))

    for member in instance_project.members:
        state = by_id[member.repo_id]
        agents = state.worktree / "AGENTS.md"
        if agents.exists():
            sources.append(_source_record(
                scope="repository", kind="agents", path=agents, folder=folder,
                source_commit=state.head, member_id=member.repo_id,
            ))
        generated = state.worktree / ".agents" / "project.generated.md"
        if generated.exists():
            sources.append(_source_record(
                scope="repository", kind="generated-project-guidance", path=generated,
                folder=folder, source_commit=state.head, member_id=member.repo_id,
            ))
        overlay = state.worktree / ".agents" / "overlays" / f"{member.repo_id}.project-overrides.md"
        if overlay.exists():
            sources.append(_source_record(
                scope="repository", kind="member-overlay", path=overlay,
                folder=folder, source_commit=state.head, member_id=member.repo_id,
            ))
    # Every input order is semantically significant for a context trace.  The
    # construction order above is explicit; sorting only makes the persisted
    # representation independent of filesystem enumeration.
    return sorted(
        sources,
        key=lambda record: (
            str(record["scope"]), str(record["kind"]), str(record["member_id"] if "member_id" in record else ""), str(record["path"]),
        ),
    )


def _context_bundle_sha256(context_sources: list[dict[str, object]]) -> str:
    payload = json.dumps(context_sources, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _binding_shape(project: render_project.ProjectBinding) -> tuple[object, ...]:
    """Return the logical fields that must not change inside one instance."""
    return (
        project.project_id,
        project.display_name,
        project.home_repo,
        tuple(
            (
                member.repo_id,
                member.backlog,
                member.render,
                member.relationship,
                member.access,
                member.path_notes,
                member.required_documents,
                member.optional_documents,
                member.forbidden_documents,
                member.repository,
                member.default_ref,
            )
            for member in project.members
        ),
    )


def _validate_instance_binding(
    canonical: render_project.ProjectBinding,
    folder: Path,
) -> render_project.ProjectBinding:
    """Require the materialized home revision to contain the selected binding."""
    materialized = render_project.load_project(
        folder / MEMBERS_DIRECTORY / canonical.home_repo / "project.toml",
        workspace_root=folder / MEMBERS_DIRECTORY,
        allow_missing_members=True,
    )
    release = _release_marker(folder)
    if release is not None:
        # A release marker is the authority for a pinned instance.  Do not
        # compare against the mutable destination anchor, but do validate the
        # complete logical binding embedded in the marker before destroy (or
        # any other lifecycle mutation).  This catches same-member-set
        # semantic/document/path drift, not just a changed project id.
        if materialized.project_id != release.get("project_id", canonical.project_id):
            raise ProjectFolderError("release-pinned home project_id differs from descriptor provenance")
        expected_members = release.get("members")
        if not isinstance(expected_members, list):
            raise ProjectFolderError("release-pinned marker has no semantic member topology")
        if release.get("home_repo") != materialized.home_repo or len(expected_members) != len(materialized.members):
            raise ProjectFolderError("release-pinned home binding topology differs from descriptor provenance")
        for expected, actual in zip(expected_members, materialized.members, strict=True):
            if not isinstance(expected, dict):
                raise ProjectFolderError("release-pinned marker member is malformed")
            expected_documents = expected.get("documents", {})
            if not isinstance(expected_documents, dict):
                raise ProjectFolderError("release-pinned marker document contract is malformed")
            expected_shape = (
                expected.get("repo_id"), expected.get("backlog"), expected.get("render"),
                expected.get("relationship"), expected.get("access"),
                tuple(expected.get("path_notes", [])),
                tuple(expected_documents.get("required", [])),
                tuple(expected_documents.get("optional", [])),
                tuple(expected_documents.get("forbidden", [])),
                expected.get("repository"), expected.get("default_ref"),
            )
            actual_shape = (
                actual.repo_id, actual.backlog, actual.render, actual.relationship,
                actual.access, actual.path_notes, actual.required_documents,
                actual.optional_documents, actual.forbidden_documents,
                actual.repository, actual.default_ref,
            )
            if expected_shape != actual_shape:
                raise ProjectFolderError(
                    f"release-pinned home binding differs for {actual.repo_id}"
                )
        return materialized
    if _binding_shape(materialized) != _binding_shape(canonical):
        raise ProjectFolderError(
            "materialized home repository project binding differs from the "
            "canonical binding selected at setup"
        )
    return materialized


def _folder_agents(
    project: render_project.ProjectBinding,
    states: tuple[WorktreeState, ...],
    *, instance: str, mode: str, readonly_enforced: bool,
) -> bytes:
    lines = [
        "<!-- agentops-project-folder: DO NOT HAND-EDIT",
        f"     project_id: {project.project_id}",
        f"     instance_id: {instance}",
        f"     mode: {mode}",
        f"     tool: {TOOL_ID}",
        "-->",
        "",
        f"# {project.display_name} project scope",
        "",
        f"Canonical binding: `{project.project_path}`.",
        "This folder is derived. Writable instances are destroyable only after clean-state checks; repository truth remains in repository commits and refs.",
        f"Instance mode is `{mode}`. shared-read filesystem enforcement is `{str(readonly_enforced).lower()}`.",
        "Dispatcher worktrees continue to anchor on primary clones, never these project worktrees.",
        "",
        "## Members",
        "",
    ]
    bindings = {member.repo_id: member for member in project.members}
    for state in states:
        binding = bindings[state.repo_id]
        lines.append(
            f"- `{state.repo_id}`: `{state.worktree.relative_to(state.worktree.parents[1])}` "
            f"(backlog={str(binding.backlog).lower()}, render={binding.render}, "
            f"relationship={binding.relationship}, access={binding.access}, "
            f"effective_mode={state.effective_mode}, "
            f"tracks `{state.default_ref}`)"
        )
        for note in binding.path_notes:
            lines.append(f"  - {note}")
    lines.extend(
        (
            "",
            f"Resolved machine context: `{CONTEXT_NAME}`.",
            "Use status to inspect without mutation; refresh-context never fetches or advances Git.",
            "Run project-scoped sprintctl reads from a member worktree so remote backend identity is explicit:",
            f"`cd {MEMBERS_DIRECTORY}/{project.home_repo} && sprintctl usage --context --project --json`.",
            "",
        )
    )
    return "\n".join(lines).encode("utf-8")


def _write_resolved_context(
    project: render_project.ProjectBinding,
    folder: Path,
    command: str,
    instance: str,
    mode: str,
    readonly_enforced: bool,
    states: tuple[WorktreeState, ...],
    render_statuses: tuple[render_project.MemberStatus, ...],
) -> str:
    _atomic_write(folder / "AGENTS.md", _folder_agents(
        project, states, instance=instance, mode=mode,
        readonly_enforced=readonly_enforced,
    ))
    context = _resolved_context(
        project, folder, command, instance, mode, readonly_enforced, states, render_statuses
    )
    _atomic_write(
        folder / CONTEXT_NAME,
        _json_bytes(context),
    )
    return str(context["context_bundle_sha256"])


def _write_marker_context_bundle(
    project: render_project.ProjectBinding,
    folder: Path,
    *,
    instance: str,
    mode: str,
    readonly_enforced: bool,
    context_bundle_sha256: str,
) -> None:
    """Record the exact generated context bundle on the v2 instance marker."""
    path = folder / MARKER_NAME
    try:
        marker = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectFolderError(f"cannot read project-folder marker: {error}") from error
    expected = _marker(
        project, instance=instance, mode=mode, readonly_enforced=readonly_enforced
    )
    if isinstance(marker.get("release"), dict):
        expected["release"] = marker["release"]
    if any(marker.get(key) != value for key, value in expected.items()):
        raise ProjectFolderError("project-folder marker changed during context materialization")
    expected["context_bundle_sha256"] = context_bundle_sha256
    _atomic_write(path, _json_bytes(expected))


def _status_drift(
    project: render_project.ProjectBinding,
    folder: Path,
    states: tuple[WorktreeState, ...],
    *,
    environment_records_dir: Path = render_project.ENVIRONMENT_RECORDS_DIR,
    materialized_project: render_project.ProjectBinding | None = None,
) -> tuple[str, ...]:
    """Compare the persisted snapshot with current local facts, read-only.

    This deliberately reports all discrepancies it can inspect.  A broken
    member or stale context must not hide drift in the remaining members.
    """
    context_path = folder / CONTEXT_NAME
    if context_path.is_symlink() or not context_path.is_file():
        return ("context: STALE (project.context.json is missing)",)
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return (f"context: INVALID ({error})",)
    if not isinstance(context, dict):
        return ("context: INVALID (root is not an object)",)
    drift: list[str] = []
    release = _release_marker(folder)
    if release is not None:
        recorded_release = context.get("release")
        if recorded_release != release:
            drift.append("release: STALE (marker/context release provenance differs)")
        # Release provenance is descriptor-owned; mutable anchor HEAD and
        # project.toml bytes are deliberately not consulted here.
        release_members = {
            item.get("repo_id"): item for item in release.get("members", [])
            if isinstance(item, dict)
        } if isinstance(release.get("members"), list) else {}
        def same_release_ref(recorded: object, current: object) -> bool:
            if recorded == current:
                return True
            if isinstance(recorded, str) and isinstance(current, str) and recorded.startswith("refs/heads/"):
                return current == "origin/" + recorded.removeprefix("refs/heads/")
            return False
        for state in states:
            pinned = release_members.get(state.repo_id)
            if pinned is None or pinned.get("commit") != state.head or not same_release_ref(pinned.get("default_ref"), state.default_ref):
                drift.append(f"release {state.repo_id}: STALE (selected head/ref changed)")
    if release is None:
        try:
            current_commit, current_digest = _binding_provenance(project)
            if context.get("source_binding_commit") != current_commit:
                drift.append(
                    "binding commit: STALE (recorded "
                    f"{context.get('source_binding_commit')}; current {current_commit})"
                )
            if context.get("source_binding_sha256") != current_digest:
                drift.append("binding digest: STALE (canonical project.toml changed)")
        except ProjectFolderError as error:
            drift.append(f"binding provenance: UNAVAILABLE ({error})")

    expected_ids = [member.repo_id for member in project.members]
    rows = context.get("members")
    recorded_ids = [row.get("repo_id") for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    missing = [repo_id for repo_id in expected_ids if repo_id not in recorded_ids]
    unexpected = [repo_id for repo_id in recorded_ids if repo_id not in expected_ids]
    if missing:
        drift.append("topology: STALE (missing recorded member(s): " + ", ".join(missing) + ")")
    if unexpected:
        drift.append("topology: STALE (unexpected recorded member(s): " + ", ".join(unexpected) + ")")
    if recorded_ids != expected_ids and not (missing or unexpected):
        drift.append("topology: STALE (member order differs from canonical binding)")

    by_id = {state.repo_id: state for state in states}
    rows_list = rows if isinstance(rows, list) else []
    recorded_by_id = {
        row.get("repo_id"): row for row in rows_list
        if isinstance(row, dict) and isinstance(row.get("repo_id"), str)
    }
    for repo_id in expected_ids:
        state = by_id.get(repo_id)
        row = recorded_by_id.get(repo_id)
        if state is None or row is None:
            continue
        for field, current in (("branch", state.branch), ("default_ref", state.default_ref), ("head", state.head)):
            ref_equivalent = (
                field == "default_ref"
                and isinstance(row.get(field), str)
                and isinstance(current, str)
                and row[field].startswith("refs/heads/")
                and current == "origin/" + row[field].removeprefix("refs/heads/")
            )
            if row.get(field) != current and not ref_equivalent:
                drift.append(f"{repo_id} {field}: STALE (recorded {row.get(field)}; current {current})")

    sources = context.get("context_sources")
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get("path"), str):
                drift.append("context sources: INVALID (malformed source record)")
                continue
            source_path = Path(source["path"])
            if source_path.is_absolute():
                expected_environment = (project.workspace_root / "AGENTS.md").resolve()
                if (
                    source.get("scope") != "environment"
                    or source.get("kind") != "agents"
                    or source_path.resolve() != expected_environment
                ):
                    drift.append(f"document: INVALID (untrusted absolute context source {source['path']})")
                    continue
            else:
                candidate = (folder / source_path).resolve()
                if not _is_within(candidate, folder.resolve()):
                    drift.append(f"document: INVALID (context source escapes folder: {source['path']})")
                    continue
                source_path = candidate
            if not _is_within(source_path.resolve(), folder.resolve()) and source_path != (project.workspace_root / "AGENTS.md").resolve():
                drift.append(f"document: INVALID (foreign context source {source['path']})")
                continue
            if not source_path.is_file() or source_path.is_symlink():
                drift.append(f"document: STALE (missing context source {source['path']})")
                continue
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if source.get("sha256") != digest:
                drift.append(f"document: STALE (hash changed for {source['path']})")
    elif sources is not None:
        drift.append("context sources: INVALID (not an array)")

    # Render/document contracts are checked against the materialized member
    # files, including missing AGENTS and render:none violations.  Do not
    # follow files through an invalid/foreign worktree while producing status.
    inspectable = not any(
        state.status in {"invalid-worktree", "foreign-worktree", "unexpected-branch"}
        for state in states
    )
    try:
        if not inspectable:
            return tuple(dict.fromkeys(drift))
        materialized = materialized_project or render_project.load_project(
            folder / MEMBERS_DIRECTORY / project.home_repo / "project.toml",
            workspace_root=folder / MEMBERS_DIRECTORY,
            allow_missing_members=True,
        )
        for status in render_project.inspect_project(
            materialized, environment_records_dir=environment_records_dir
        ):
            # Environment output is host-local and may be unavailable to a
            # read-only status caller even when project documents are sound.
            # Its explicit document contract is checked below; do not turn a
            # different host's active environment record into false project
            # topology drift.
            if status.generated not in {"in-sync", "not-applicable"} or status.pointer not in {"in-sync", "not-applicable"}:
                drift.append(
                    f"documents {status.repo_id}: STALE "
                    f"generated={status.generated} pointer={status.pointer}"
                )
            for path, state in status.documents:
                if state in {"missing", "unexpected", "invalid"}:
                    drift.append(f"document {status.repo_id}/{path}: {state}")
    except (OSError, render_project.ProjectRenderError) as error:
        drift.append(f"documents: UNAVAILABLE ({error})")
    return tuple(dict.fromkeys(drift))


def _materialize_unlocked(
    project: render_project.ProjectBinding,
    folder: Path,
    *,
    command: str,
    instance: str = "default",
    mode: str = "exclusive-write",
    readonly_enforced: bool = False,
    environment_records_dir: Path = render_project.ENVIRONMENT_RECORDS_DIR,
) -> MaterializationResult:
    if not INSTANCE_RE.fullmatch(instance):
        raise ProjectFolderError(
            "instance must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"
        )
    if mode not in {"shared-read", "exclusive-write"}:
        raise ProjectFolderError(f"unsupported instance mode: {mode}")
    if command in {"sync", "refresh-context"} and _release_marker(folder) is not None:
        raise ProjectFolderError(
            f"{command} refuses release-pinned instances; rebuild from a new descriptor"
        )
    folder = _prepare_folder(
        project, folder, require_existing=command != "setup", instance=instance,
        mode=mode, readonly_enforced=readonly_enforced, mutate=command != "status",
    )
    release = _release_marker(folder)
    if release is not None:
        project = _release_project_view(project, release)
    if release is not None:
        binding = release.get("binding")
        binding_commit = binding.get("commit", "") if isinstance(binding, dict) else ""
    else:
        try:
            binding_commit, _binding_digest = _binding_provenance(project)
        except ProjectFolderError as error:
            if command != "status":
                raise
            binding_commit = ""
    states: list[WorktreeState] = []
    pinned_members = {
        item.get("repo_id"): item for item in release.get("members", [])
        if isinstance(item, dict)
    } if release is not None and isinstance(release.get("members"), list) else {}
    for member in project.members:
        if not member.repo_root.is_dir():
            if command == "status":
                states.append(WorktreeState(
                    member.repo_id, member.repo_root,
                    folder / MEMBERS_DIRECTORY / member.repo_id, "", "", "",
                    "missing-member", f"canonical member repository is unavailable: {member.repo_root}",
                ))
                continue
            raise ProjectFolderError(f"member repository does not exist: {member.repo_root}")
        if command in {"setup", "sync"}:
            _fetch_and_prune(member.repo_root)
        pinned = pinned_members.get(member.repo_id)
        try:
            default_ref = pinned.get("default_ref") if pinned is not None else _default_ref(member.repo_root)
            if not isinstance(default_ref, str):
                raise ProjectFolderError("pinned member default_ref is malformed")
        except ProjectFolderError as error:
            if command == "status":
                states.append(WorktreeState(
                    member.repo_id, member.repo_root,
                    folder / MEMBERS_DIRECTORY / member.repo_id, "", "", "",
                    "unavailable-ref", str(error),
                ))
                continue
            raise
        branch = _materialized_branch(project, instance, member.repo_id)
        effective_mode = _effective_member_mode(member, mode)
        if command in {"setup", "sync"}:
            worktree, branch = _ensure_worktree(
                project,
                member,
                folder,
                default_ref,
                instance=instance,
                mode=effective_mode,
                start_ref=(binding_commit if member.repo_id == project.home_repo else None),
            )
        else:
            worktree = folder / MEMBERS_DIRECTORY / member.repo_id
            if not worktree.is_dir():
                if command != "status":
                    raise ProjectFolderError(f"materialized member worktree is unavailable: {worktree}")
                states.append(WorktreeState(
                    member.repo_id, member.repo_root, worktree, branch, default_ref, "",
                    "missing-worktree", f"materialized member worktree is unavailable: {worktree}",
                    effective_mode,
                ))
                continue
            try:
                _validate_existing_worktree(member.repo_root, worktree, branch, mode=effective_mode)
            except ProjectFolderError as error:
                if command != "status":
                    raise
                detail = str(error)
                status = "foreign-worktree" if "not a worktree of" in detail else "invalid-worktree"
                if "detached" in detail or "expected materialized branch" in detail:
                    status = "unexpected-branch"
                states.append(WorktreeState(
                    member.repo_id, member.repo_root, worktree, branch, default_ref, "",
                    status, detail, effective_mode,
                ))
                continue
        try:
            states.append(
                _pinned_worktree_state(
                    member, worktree, branch, default_ref, pinned["commit"], mode=effective_mode
                ) if pinned is not None else _worktree_state(
                    member,
                    worktree,
                    branch,
                    default_ref,
                    mode=effective_mode,
                    # A detached/reference worktree is a recorded inspection
                    # point: sync may fetch and report drift, never advance it.
                    advance=(
                        command == "sync"
                        and effective_mode == "exclusive-write"
                        and member.repo_id != project.home_repo
                    ),
                )
            )
        except ProjectFolderError as error:
            if command != "status":
                raise
            states.append(WorktreeState(
                member.repo_id, member.repo_root, worktree, branch, default_ref, "",
                "invalid-worktree", str(error), effective_mode,
            ))

    # Directory entries under members/ are materialized worktrees only when
    # declared by the binding.  Report extras without touching them.
    members_root = folder / MEMBERS_DIRECTORY
    expected_ids = {member.repo_id for member in project.members}
    if command == "status" and members_root.is_dir():
        for entry in sorted(members_root.iterdir(), key=lambda path: path.name):
            if entry.name in expected_ids or entry.name.startswith("."):
                continue
            states.append(WorktreeState(
                entry.name, entry, entry, "", "", "", "unexpected-member",
                "member directory is not declared by the canonical project binding",
            ))

    state_tuple = tuple(states)
    if mode == "shared-read" and readonly_enforced and any(
        state.blocked for state in state_tuple
    ):
        raise ProjectFolderError(
            "refusing shared-read filesystem enforcement while member state is blocked"
        )
    render_statuses: tuple[render_project.MemberStatus, ...] = ()
    materialized_binding_error: str | None = None
    try:
        materialized_project = _validate_instance_binding(project, folder)
    except ProjectFolderError as error:
        if command != "status":
            raise
        # Status must remain useful when the canonical binding has changed or
        # gained a member since this disposable instance was materialized.
        materialized_project = None
        materialized_binding_error = str(error)
    # shared-read intentionally does not render into member worktrees: that
    # would immediately make an otherwise detached inspection instance dirty.
    release_refresh = command == "refresh-context" and _release_marker(folder) is not None
    if command != "status" and mode == "exclusive-write" and not release_refresh and not any(state.blocked for state in state_tuple):
        # Reference members are detached context inputs even in an
        # exclusive-write instance.  Selective application prevents project
        # rendering from changing their AGENTS pointers or generated files.
        writable_members = tuple(
            member for member in materialized_project.members
            if member.access != "reference"
        )
        if writable_members:
            render_statuses = tuple(
                render_project.apply_project(
                    replace(materialized_project, members=writable_members),
                    environment_records_dir=environment_records_dir,
                )
            )

    for member in project.members if command in {"setup", "sync"} else ():
        _git(member.repo_root, "worktree", "prune")
    if command != "status":
        contract_statuses = render_project.inspect_project(
            materialized_project, environment_records_dir=environment_records_dir
        )
        contract_violations = render_project.document_contract_violations(
            materialized_project,
            contract_statuses,
            check_renderer_state=True,
        )
        if contract_violations:
            raise ProjectFolderError(
                "materialized document contract violations:\n"
                + "\n".join(f"- {item}" for item in contract_violations)
            )
        context_bundle_sha256 = _write_resolved_context(
            project, folder, command, instance, mode, readonly_enforced,
            state_tuple, render_statuses,
        )
        _write_marker_context_bundle(
            project,
            folder,
            instance=instance,
            mode=mode,
            readonly_enforced=readonly_enforced,
            context_bundle_sha256=context_bundle_sha256,
        )
        enforced_states = tuple(
            state
            for state, member in zip(state_tuple, project.members, strict=True)
            if member.access == "reference"
            or (mode == "shared-read" and readonly_enforced)
        )
        if enforced_states:
            _enforce_shared_read_worktrees(enforced_states)
    drift = ()
    if command == "status":
        drift_items = list(_status_drift(
            project, folder, state_tuple,
            environment_records_dir=environment_records_dir,
            materialized_project=materialized_project,
        ))
        if materialized_binding_error:
            drift_items.insert(0, f"materialized binding: STALE ({materialized_binding_error})")
        drift = tuple(dict.fromkeys(drift_items))
    return MaterializationResult(command, folder, state_tuple, render_statuses, drift)


def _release_project_matches(
    project: render_project.ProjectBinding,
    descriptor: dict[str, object],
) -> None:
    descriptor_home = next(
        item["repo_id"] for item in descriptor["members"]
        if item["repository"] == descriptor["binding"]["repository"]
        and item["commit"] == descriptor["binding"]["commit"]
    )
    if descriptor["project_id"] != project.project_id or project.home_repo != descriptor_home or descriptor.get("binding", {}).get("repository") != next(
        (member.repository for member in project.members if member.repo_id == project.home_repo), None
    ):
        raise ProjectFolderError("descriptor project identity/home binding differs from canonical project.toml")
    descriptor_members = descriptor.get("members")
    if not isinstance(descriptor_members, list) or len(descriptor_members) != len(project.members):
        raise ProjectFolderError("descriptor member topology differs from canonical project.toml")
    for expected, actual in zip(descriptor_members, project.members, strict=True):
        if not isinstance(expected, dict):
            raise ProjectFolderError("descriptor member is malformed")
        for key in ("repo_id", "backlog", "render", "relationship", "access", "repository", "default_ref"):
            if expected.get(key) != (actual.repo_id if key == "repo_id" else getattr(actual, key)):
                raise ProjectFolderError(f"descriptor topology differs for {actual.repo_id}: {key}")
        documents = expected.get("documents")
        if not isinstance(documents, dict) or {
            key: list(getattr(actual, f"{key}_documents"))
            for key in ("required", "optional", "forbidden")
        } != {key: documents.get(key) for key in ("required", "optional", "forbidden")}:
            raise ProjectFolderError(f"descriptor document contract differs for {actual.repo_id}")


def _descriptor_project_shell(
    descriptor: dict[str, object], workspace_root: Path, descriptor_path: Path
) -> render_project.ProjectBinding:
    members: list[render_project.MemberBinding] = []
    for item in descriptor["members"]:
        members.append(
            render_project.MemberBinding(
                repo_id=item["repo_id"],
                backlog=item["backlog"],
                render=item["render"],
                relationship=item["relationship"],
                access=item["access"],
                path_notes=(),
                required_documents=tuple(item["documents"]["required"]),
                optional_documents=tuple(item["documents"]["optional"]),
                forbidden_documents=tuple(item["documents"]["forbidden"]),
                repo_root=(workspace_root / item["repo_id"]).resolve(),
                repository=item["repository"],
                default_ref=item["default_ref"],
            )
        )
    home_id = next(
        item["repo_id"] for item in descriptor["members"]
        if item["repository"] == descriptor["binding"]["repository"]
        and item["commit"] == descriptor["binding"]["commit"]
    )
    return render_project.ProjectBinding(
        project_path=descriptor_path.resolve(),
        workspace_root=workspace_root.resolve(),
        project_id=descriptor["project_id"],
        display_name="release-pinned project",
        home_repo=home_id,
        members=tuple(members),
    )


def _release_project_view(
    canonical: render_project.ProjectBinding,
    release: dict[str, object],
) -> render_project.ProjectBinding:
    """Reconstruct the pinned logical binding without consulting the anchor.

    The destination's current project.toml may be older or have a different
    member set.  Lifecycle/status operations still need the descriptor's full
    topology so missing and unexpected members are visible rather than being
    silently skipped.
    """
    raw_members = release.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise ProjectFolderError("release marker has no member topology")
    members: list[render_project.MemberBinding] = []
    for raw in raw_members:
        if not isinstance(raw, dict):
            raise ProjectFolderError("release marker member is malformed")
        documents = raw.get("documents")
        if not isinstance(documents, dict):
            raise ProjectFolderError("release marker document contract is malformed")
        members.append(render_project.MemberBinding(
            repo_id=raw.get("repo_id"),
            backlog=raw.get("backlog"),
            render=raw.get("render"),
            relationship=raw.get("relationship"),
            access=raw.get("access"),
            path_notes=tuple(raw.get("path_notes", [])),
            required_documents=tuple(documents.get("required", [])),
            optional_documents=tuple(documents.get("optional", [])),
            forbidden_documents=tuple(documents.get("forbidden", [])),
            repo_root=(canonical.workspace_root / raw.get("repo_id")).resolve(),
            repository=raw.get("repository"),
            default_ref=raw.get("default_ref"),
        ))
    home_repo = release.get("home_repo")
    if not isinstance(home_repo, str) or home_repo not in {member.repo_id for member in members}:
        binding = release.get("binding")
        home_repo = next(
            (member.repo_id for member in members
             if isinstance(binding, dict) and member.repository == binding.get("repository")),
            "",
        )
    if not home_repo:
        raise ProjectFolderError("release marker has no home member")
    return render_project.ProjectBinding(
        project_path=canonical.project_path,
        workspace_root=canonical.workspace_root,
        project_id=release.get("project_id", canonical.project_id),
        display_name=release.get("display_name", canonical.display_name),
        home_repo=home_repo,
        members=tuple(members),
    )


def _release_anchor_errors(
    project: render_project.ProjectBinding,
    descriptor: dict[str, object],
    workspace_root: Path,
    folder: Path,
    instance: str,
) -> list[str]:
    errors: list[str] = []
    anchors = {member.repo_id: member for member in project.members}
    descriptor_members = descriptor.get("members", [])
    if not isinstance(descriptor_members, list):
        return ["descriptor members are not an array"]
    descriptor_ids = [item.get("repo_id") for item in descriptor_members if isinstance(item, dict)]
    if descriptor_ids != [member.repo_id for member in project.members]:
        errors.append("descriptor member topology/order does not match canonical project.toml")
    folder_resolved = folder.expanduser().absolute().resolve(strict=False)
    for repo_id in sorted(set(anchors) | set(descriptor_ids)):
        member = anchors.get(repo_id)
        expected = next((item for item in descriptor_members if isinstance(item, dict) and item.get("repo_id") == repo_id), None)
        if member is None or expected is None:
            errors.append(f"{repo_id}: missing canonical/descriptor member")
            continue
        anchor = member.repo_root
        if not anchor.is_dir():
            errors.append(f"{repo_id}: missing anchor {anchor}")
            continue
        try:
            top = _git(anchor, "rev-parse", "--show-toplevel").stdout.strip()
            if Path(top).resolve() != anchor.resolve():
                errors.append(f"{repo_id}: anchor is not the expected Git root")
        except ProjectFolderError as error:
            errors.append(f"{repo_id}: invalid Git anchor ({error})")
        try:
            origin = _git(anchor, "remote", "get-url", "origin").stdout.strip()
            if origin != expected.get("repository"):
                errors.append(f"{repo_id}: origin URL mismatch (recorded {origin!r})")
        except ProjectFolderError as error:
            errors.append(f"{repo_id}: origin unavailable ({error})")
        if _is_within(folder_resolved, anchor.resolve()):
            errors.append(f"{repo_id}: target folder is inside anchor")
        branch = _materialized_branch(project, instance, repo_id)
        if _git(anchor, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0:
            errors.append(f"{repo_id}: materialized branch already exists: {branch}")
        private_prefix = "refs/agentops/project-rebuild/"
        if _git(anchor, "for-each-ref", "--format=%(refname)", private_prefix, check=False).stdout.strip():
            errors.append(f"{repo_id}: stale private rebuild refs exist")
    if folder_resolved.exists():
        errors.append(f"target folder already exists: {folder_resolved}")
    return errors


def rebuild_release(
    descriptor_path: Path,
    folder: Path,
    *,
    workspace_root: Path,
    instance: str = "default",
    mode: str = "exclusive-write",
    package_path: Path | None = None,
    source_host: str | None = None,
    receipt_output: Path | None = None,
) -> MaterializationResult:
    """Rebuild a release-pinned view from descriptor refs or verified bundles."""
    if not INSTANCE_RE.fullmatch(instance):
        raise ProjectFolderError("invalid rebuild instance")
    if mode not in {"shared-read", "exclusive-write"}:
        raise ProjectFolderError("unsupported rebuild mode")
    if receipt_output is not None and package_path is None:
        raise ProjectFolderError("--receipt-output requires --package")
    if source_host is not None and package_path is None:
        raise ProjectFolderError("--source-host requires --package")
    descriptor_source_path = descriptor_path
    descriptor_snapshot = project_release.stage_verified_descriptor(descriptor_source_path)
    descriptor_path = descriptor_snapshot.descriptor_path
    descriptor = descriptor_snapshot.descriptor
    descriptor_members = descriptor["members"]
    project = _descriptor_project_shell(descriptor, workspace_root, descriptor_source_path)
    home_id = project.home_repo
    errors = _release_anchor_errors(project, descriptor, workspace_root, folder, instance)
    if errors:
        descriptor_snapshot.close()
        raise ProjectFolderError("release rebuild preflight failed:\n" + "\n".join(f"- {item}" for item in errors))

    source_host_value = source_host or socket.gethostname()
    package: dict[str, object] | None = None
    package_error: str | None = None
    package_snapshot: project_release.VerifiedPackageSnapshot | None = None
    if package_path is not None:
        try:
            package_snapshot = project_release.stage_verified_package(
                package_path,
                descriptor_path,
                source_host=source_host_value,
            )
            if package_snapshot.descriptor != descriptor:
                raise project_release.ReleaseError("descriptor changed during package staging")
            package = package_snapshot.package
        except (OSError, project_release.ReleaseError) as error:
            package_error = str(error)

    remote_errors: dict[str, str] = {}
    for member in descriptor_members:
        try:
            project_release.verify_remote(
                member["repository"], member["default_ref"], member["commit"],
                documents=member["documents"], descriptor=descriptor,
                verify_binding=member["repo_id"] == home_id,
            )
        except Exception as error:
            remote_errors[member["repo_id"]] = str(error)
    if not remote_errors and package_snapshot is None:
        try:
            project_release.verify_remote_project_render_state(descriptor)
        except project_release.ReleaseError as error:
            raise ProjectFolderError(
                f"release renderer preflight failed before acquisition: {error}"
            ) from error
    package_members = {
        member["repo_id"]: member for member in (package or {}).get("members", [])
        if isinstance(member, dict)
    }
    acquisition_plan_errors: list[str] = []
    for member in descriptor_members:
        if member["repo_id"] in remote_errors and member["repo_id"] not in package_members:
            acquisition_plan_errors.append(
                f"{member['repo_id']}: {remote_errors[member['repo_id']]}"
                f"; no verified package fallback ({package_error or 'package unavailable'})"
            )
    binding_bytes: bytes | None = None
    if home_id not in remote_errors:
        try:
            binding_bytes = project_release.verified_remote_object(
                descriptor["binding"]["repository"],
                descriptor_members[[item["repo_id"] for item in descriptor_members].index(home_id)]["default_ref"],
                descriptor["binding"]["commit"],
                "project.toml",
            )
        except project_release.ReleaseError as error:
            remote_errors[home_id] = str(error)
    if binding_bytes is None and package_snapshot is not None:
        home_package = package_members.get(home_id)
        if home_package is not None:
            try:
                binding_bytes = project_release.verified_bundle_object(
                    package_snapshot.bundle_paths[home_package["bundle"]],
                    home_package["commit"],
                    "project.toml",
                )
            except project_release.ReleaseError as error:
                acquisition_plan_errors.append(f"{home_id}: verified package binding object unavailable: {error}")
    if binding_bytes is None:
        acquisition_plan_errors.append(f"{home_id}: canonical project.toml object is unavailable")
    if acquisition_plan_errors:
        if package_snapshot is not None:
            package_snapshot.close()
        descriptor_snapshot.close()
        raise ProjectFolderError("release acquisition plan failed:\n" + "\n".join(f"- {item}" for item in acquisition_plan_errors))
    try:
        committed_binding = project_release.parse_verified_binding(binding_bytes, descriptor)
        project = replace(project, display_name=committed_binding.get("display_name", project.display_name))
    except project_release.ReleaseError as error:
        if package_snapshot is not None:
            package_snapshot.close()
        descriptor_snapshot.close()
        raise ProjectFolderError(f"descriptor-selected canonical project.toml rejected: {error}") from error
    transaction = uuid.uuid4().hex
    private_refs: list[tuple[Path, str]] = []
    acquisitions: dict[str, str] = {}
    created_worktrees: list[tuple[Path, Path]] = []
    created_branches: list[tuple[Path, str]] = []
    folder_created = False
    receipt_created = False
    readonly_enforced = False
    states: list[WorktreeState] = []

    def cleanup_refs() -> list[str]:
        failures: list[str] = []
        for anchor, ref in reversed(private_refs):
            result = _git(anchor, "update-ref", "-d", ref, check=False)
            if result.returncode:
                failures.append(f"{anchor}: could not delete {ref}: {result.stderr.strip()}")
        return failures

    def rollback() -> list[str]:
        failures: list[str] = []
        for anchor, worktree in reversed(created_worktrees):
            if readonly_enforced:
                try:
                    _set_shared_read_worktree_writable(worktree, writable=True)
                except ProjectFolderError as error:
                    failures.append(f"could not restore writable worktree {worktree}: {error}")
            result = _git(anchor, "worktree", "remove", "--force", str(worktree), check=False)
            if result.returncode:
                failures.append(f"{anchor}: could not remove worktree {worktree}: {result.stderr.strip()}")
        for anchor, branch in reversed(created_branches):
            result = _git(anchor, "branch", "-D", branch, check=False)
            if result.returncode:
                failures.append(f"{anchor}: could not remove branch {branch}: {result.stderr.strip()}")
        for path in (folder / MARKER_NAME, folder / CONTEXT_NAME, folder / "AGENTS.md"):
            try:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            except OSError as error:
                failures.append(f"could not remove created file {path}: {error}")
        if receipt_created and receipt_output is not None:
            try:
                if receipt_output.is_file() and not receipt_output.is_symlink():
                    receipt_output.unlink()
            except OSError as error:
                failures.append(f"could not remove created receipt {receipt_output}: {error}")
        try:
            members_path = folder / MEMBERS_DIRECTORY
            if members_path.is_dir() and not any(members_path.iterdir()):
                members_path.rmdir()
            if folder_created and folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        except OSError as error:
            failures.append(f"could not remove empty rebuild folder: {error}")
        return failures

    try:
        for member in descriptor_members:
            anchor = project.members[[item.repo_id for item in project.members].index(member["repo_id"])].repo_root
            private_ref = f"refs/agentops/project-rebuild/{transaction}/{member['repo_id']}"
            fetch_environment = {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull,
            }
            fetched = _git(
                anchor, "-c", "core.hooksPath=/dev/null", "fetch",
                "--no-write-fetch-head", "--no-tags", "--no-auto-maintenance",
                "origin", f"{member['default_ref']}:{private_ref}",
                check=False, env=fetch_environment,
            )
            observed = _git(anchor, "rev-parse", private_ref, check=False).stdout.strip()
            if observed:
                private_refs.append((anchor, private_ref))
            if fetched.returncode == 0 and observed == member["commit"] and member["repo_id"] not in remote_errors:
                acquisitions[member["repo_id"]] = "remote-ref"
            else:
                if observed:
                    _git(anchor, "update-ref", "-d", private_ref)
                package_member = package_members.get(member["repo_id"])
                if package_member is None or package_path is None:
                    reason = remote_errors.get(member["repo_id"], package_error or "exact remote acquisition failed")
                    raise ProjectFolderError(f"{member['repo_id']}: {reason}; no verified package fallback")
                if package_snapshot is None:
                    raise ProjectFolderError(f"{member['repo_id']}: verified package snapshot is unavailable")
                bundle = package_snapshot.bundle_paths[package_member["bundle"]]
                fetched_bundle = _git(
                    anchor, "-c", "core.hooksPath=/dev/null", "fetch",
                    "--no-write-fetch-head", "--no-tags", "--no-auto-maintenance",
                    str(bundle), f"{member['default_ref']}:{private_ref}",
                    check=False, env=fetch_environment,
                )
                observed = _git(anchor, "rev-parse", private_ref, check=False).stdout.strip()
                if fetched_bundle.returncode or observed != member["commit"]:
                    raise ProjectFolderError(f"{member['repo_id']}: verified package fallback did not acquire exact commit")
                if (anchor, private_ref) not in private_refs:
                    private_refs.append((anchor, private_ref))
                acquisitions[member["repo_id"]] = "bundle"
        folder.mkdir(parents=True, exist_ok=False)
        folder_created = True
        (folder / MEMBERS_DIRECTORY).mkdir()
        for member in descriptor_members:
            anchor = project.members[[item.repo_id for item in project.members].index(member["repo_id"])].repo_root
            worktree = folder / MEMBERS_DIRECTORY / member["repo_id"]
            effective_mode = "shared-read" if mode == "shared-read" or member["access"] == "reference" else "exclusive-write"
            branch = _materialized_branch(project, instance, member["repo_id"])
            private_ref = next(ref for ref_anchor, ref in private_refs if ref_anchor == anchor and ref.endswith("/" + member["repo_id"]))
            if effective_mode == "exclusive-write":
                _git(anchor, "worktree", "add", "-b", branch, str(worktree), private_ref)
                created_branches.append((anchor, branch))
            else:
                _git(anchor, "worktree", "add", "--detach", str(worktree), private_ref)
            created_worktrees.append((anchor, worktree))
            states.append(WorktreeState(member["repo_id"], anchor, worktree, branch, member["default_ref"], member["commit"], "current", "", effective_mode))
        state_tuple = tuple(states)
        readonly_enforced = mode == "shared-read" or any(
            member["access"] == "reference" for member in descriptor_members
        )
        if readonly_enforced:
            _enforce_shared_read_worktrees(tuple(
                state for state in state_tuple if state.effective_mode == "shared-read"
            ))
        release_provenance = {
            "schema": "agentops-release-pinned/v1",
            "descriptor_sha256": (
                package_snapshot.package["descriptor_sha256"]
                if package_snapshot is not None
                else descriptor_snapshot.sha256
            ),
            "descriptor_path": str(descriptor_source_path.resolve()),
            "project_id": project.project_id,
            "home_repo": project.home_repo,
            "display_name": project.display_name,
            "binding": descriptor["binding"],
            "topology_digest": descriptor["topology_digest"],
            "members": [
                {
                    "repo_id": member["repo_id"],
                    "backlog": member["backlog"],
                    "render": member["render"],
                    "relationship": member["relationship"],
                    "access": member["access"],
                    "repository": member["repository"],
                    "commit": member["commit"],
                    "default_ref": member["default_ref"],
                    "path_notes": [],
                    "documents": {
                        key: list(member["documents"][key])
                        for key in ("required", "optional", "forbidden")
                    },
                    "acquisition": acquisitions[member["repo_id"]],
                }
                for member in descriptor_members
            ],
            "package_sha256": package_snapshot.package_sha256 if package_snapshot else None,
            "source_host": source_host_value if package_path else None,
            "receipt_reference": str(receipt_output) if receipt_output else None,
        }
        descriptor_sha = release_provenance["descriptor_sha256"]
        marker = {
            "schema_version": 2,
            "tool": TOOL_ID,
            "tool_version": TOOL_VERSION,
            "project_id": project.project_id,
            "instance_id": instance,
            "mode": mode,
            "readonly_enforced": readonly_enforced,
            "canonical_project": f"descriptor:{descriptor_sha}",
            "source_binding_commit": descriptor["binding"]["commit"],
            "source_binding_sha256": descriptor["binding"]["raw_sha256"],
            "release": release_provenance,
        }
        _atomic_write(folder / MARKER_NAME, _json_bytes(marker))
        agents = _folder_agents(project, state_tuple, instance=instance, mode=mode, readonly_enforced=readonly_enforced)
        agents += b"\nRelease-pinned view: descriptor and exact selected Git commits are authoritative.\n"
        _atomic_write(folder / "AGENTS.md", agents)
        context = _resolved_context(project, folder, "rebuild", instance, mode, readonly_enforced, state_tuple, (), release_provenance)
        _atomic_write(folder / CONTEXT_NAME, _json_bytes(context))
        if receipt_output and package_snapshot:
            project_release.verify_release_package(
                package_snapshot.package_path,
                package_snapshot.descriptor_path,
                source_host=source_host_value,
                receipt_output=receipt_output,
            )
            receipt_created = True
        ref_failures = cleanup_refs()
        private_refs.clear()
        if ref_failures:
            raise ProjectFolderError("release rebuild completed but private ref cleanup failed:\n" + "\n".join(ref_failures))
        if package_snapshot is not None:
            package_snapshot.close()
            package_snapshot = None
        descriptor_snapshot.close()
        return MaterializationResult("rebuild", folder, state_tuple, ())
    except Exception as error:
        rollback_failures = rollback() if folder_created else []
        rollback_failures.extend(cleanup_refs())
        private_refs.clear()
        if package_snapshot is not None:
            package_snapshot.close()
        descriptor_snapshot.close()
        detail = str(error)
        if rollback_failures:
            detail += "\nrollback incomplete; recovery required:\n" + "\n".join(rollback_failures)
        raise ProjectFolderError(detail) from error


def materialize(
    project: render_project.ProjectBinding,
    folder: Path,
    *,
    command: str,
    instance: str = "default",
    mode: str = "exclusive-write",
    enforce_readonly: bool | None = None,
    environment_records_dir: Path = render_project.ENVIRONMENT_RECORDS_DIR,
) -> MaterializationResult:
    """Materialize while serializing every mutating instance operation.

    Read-only status intentionally creates neither an instance nor a lock file.
    Mutating setup, sync, and context refresh share the lease lock with destroy
    and refuse to alter an actively leased instance. A lease holder must release
    before changing the instance projection.
    """
    if not INSTANCE_RE.fullmatch(instance):
        raise ProjectFolderError(
            "instance must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"
        )
    if mode not in {"shared-read", "exclusive-write"}:
        raise ProjectFolderError(f"unsupported instance mode: {mode}")
    if command in {"sync", "refresh-context"} and _release_marker(folder) is not None:
        raise ProjectFolderError(
            f"{command} refuses release-pinned instances; rebuild from a new descriptor"
        )
    if enforce_readonly is True and (command != "setup" or mode != "shared-read"):
        raise ProjectFolderError("--enforce-readonly is valid only with shared-read setup")
    readonly_enforced = _resolved_readonly_enforcement(folder, enforce_readonly)
    if command == "status":
        return _materialize_unlocked(
            project,
            folder,
            command=command,
            instance=instance,
            mode=mode,
            readonly_enforced=readonly_enforced,
            environment_records_dir=environment_records_dir,
        )

    requested = folder.expanduser().absolute()
    bootstrap_allowed = MANAGED_RUNTIME_PATHS | {".git"}
    initialize = command == "setup" and (
        not requested.exists()
        or (
            requested.is_dir()
            and {entry.name for entry in requested.iterdir()}.issubset(bootstrap_allowed)
        )
    )
    prepared = _prepare_folder(
        project,
        folder,
        require_existing=command != "setup",
        instance=instance,
        mode=mode,
        readonly_enforced=readonly_enforced,
        mutate=initialize,
    )
    with _lease_lock(prepared):
        if (prepared / LEASE_NAME).exists():
            raise ProjectFolderError(
                "refusing to mutate an actively leased project instance; "
                "release the lease first"
            )
        return _materialize_unlocked(
            project,
            prepared,
            command=command,
            instance=instance,
            mode=mode,
            readonly_enforced=readonly_enforced,
            environment_records_dir=environment_records_dir,
        )


def _destroy_locked(
    project: render_project.ProjectBinding,
    folder: Path,
    *,
    instance: str = "default",
    mode: str = "exclusive-write",
    readonly_enforced: bool = False,
    check_only: bool = False,
) -> MaterializationResult:
    """Remove a verified-clean instance using Git's worktree lifecycle."""
    folder = _prepare_folder(
        project, folder, require_existing=True, instance=instance, mode=mode,
        readonly_enforced=readonly_enforced, mutate=False,
    )
    release = _release_marker(folder)
    if release is not None:
        project = _release_project_view(project, release)
    # Validate the complete logical binding before any worktree or root-file
    # removal.  IDs alone are insufficient: render/access/path guidance drift
    # must retain the disposable instance for explicit repair or rebuild.
    _validate_instance_binding(project, folder)
    lease = folder / LEASE_NAME
    if lease.exists() or lease.is_symlink():
        raise ProjectFolderError(f"refusing to destroy leased instance: {lease}")
    if (folder / ".git").exists():
        raise ProjectFolderError(
            "refusing to destroy instance with root .git entry; remove the empty placeholder explicitly"
        )
    session = folder / ".session"
    if session.is_symlink() or (session.is_dir() and any(session.iterdir())):
        raise ProjectFolderError("refusing to destroy instance with non-empty .session")
    for name in sorted(MANAGED_RUNTIME_PATHS - {".session"}):
        runtime_path = folder / name
        if runtime_path.is_symlink() or (runtime_path.is_dir() and any(runtime_path.iterdir())):
            raise ProjectFolderError(
                f"refusing to destroy instance with non-empty managed runtime path: {runtime_path}"
            )
    members_root = folder / MEMBERS_DIRECTORY
    expected_ids = {member.repo_id for member in project.members}
    actual_ids = {entry.name for entry in members_root.iterdir()}
    unexpected_ids = sorted(actual_ids - expected_ids)
    missing_ids = sorted(expected_ids - actual_ids)
    if unexpected_ids or missing_ids:
        detail: list[str] = []
        if unexpected_ids:
            detail.append("unexpected member(s): " + ", ".join(unexpected_ids))
        if missing_ids:
            detail.append("missing member(s): " + ", ".join(missing_ids))
        raise ProjectFolderError("refusing to destroy instance; topology preflight failed (" + "; ".join(detail) + ")")
    states: list[WorktreeState] = []
    pinned_members = {
        item.get("repo_id"): item for item in release.get("members", [])
        if isinstance(item, dict)
    } if release is not None and isinstance(release.get("members"), list) else {}
    for member in project.members:
        pinned = pinned_members.get(member.repo_id)
        default_ref = pinned.get("default_ref") if pinned is not None else _default_ref(member.repo_root)
        worktree = folder / MEMBERS_DIRECTORY / member.repo_id
        branch = _materialized_branch(project, instance, member.repo_id)
        effective_mode = _effective_member_mode(member, mode)
        _validate_existing_worktree(
            member.repo_root, worktree, branch, mode=effective_mode
        )
        state = (
            _pinned_worktree_state(member, worktree, branch, default_ref, pinned["commit"], mode=effective_mode)
            if pinned is not None
            else _worktree_state(member, worktree, branch, default_ref, mode=effective_mode, advance=False)
        )
        allowed_statuses = {"current"}
        if effective_mode == "shared-read":
            # A clean detached reference can be safely removed even when its
            # remote default ref advanced after materialization.
            allowed_statuses.add("behind")
        if state.status not in allowed_statuses:
            raise ProjectFolderError(f"refusing to destroy {member.repo_id}: {state.status}: {state.detail}")
        # A clean exclusive branch must be at its configured protected remote
        # ref.  This deliberately errs on retention rather than guessing
        # whether another local ref or reflog is durable protection.
        states.append(state)
    result = MaterializationResult("destroy-check" if check_only else "destroy", folder, tuple(states), ())
    if check_only:
        return result
    for member in project.members:
        worktree = folder / MEMBERS_DIRECTORY / member.repo_id
        if member.access == "reference" or (
            readonly_enforced
            and _effective_member_mode(member, mode) == "shared-read"
        ):
            # Git must remove the worktree itself; make just the local member
            # tree owner-writable again after all destroy checks have passed.
            _set_shared_read_worktree_writable(worktree, writable=True)
        _git(member.repo_root, "worktree", "remove", str(worktree))
        _git(member.repo_root, "worktree", "prune")
    # Only generated, now-empty directories are removed.  Member worktrees
    # were removed above through Git, never through raw recursive deletion.
    for name in ("AGENTS.md", CONTEXT_NAME, MARKER_NAME):
        path = folder / name
        if path.exists():
            path.unlink()
    if session.is_dir():
        session.rmdir()
    for name in sorted(MANAGED_RUNTIME_PATHS - {".session"}):
        runtime_path = folder / name
        if runtime_path.is_dir():
            runtime_path.rmdir()
    lock_path = folder / LEASE_LOCK_NAME
    if lock_path.exists():
        lock_path.unlink()
    (folder / MEMBERS_DIRECTORY).rmdir()
    folder.rmdir()
    return result


def destroy(
    project: render_project.ProjectBinding,
    folder: Path,
    *,
    instance: str = "default",
    mode: str = "exclusive-write",
    check_only: bool = False,
) -> MaterializationResult:
    """Destroy under the same local lock used by lease mutations."""
    readonly_enforced = _resolved_readonly_enforcement(folder, None)
    prepared = _prepare_folder(
        project, folder, require_existing=True, instance=instance, mode=mode,
        readonly_enforced=readonly_enforced, mutate=False,
    )
    with _lease_lock(prepared):
        return _destroy_locked(
            project, prepared, instance=instance, mode=mode,
            readonly_enforced=readonly_enforced, check_only=check_only,
        )


def _print_result(result: MaterializationResult) -> None:
    print(f"{result.command}: {result.folder}")
    for member in result.members:
        print(
            f"{member.repo_id}: {member.status}; effective_mode={member.effective_mode}; branch={member.branch}; "
            f"default={member.default_ref}; head={member.head}"
        )
        if member.detail:
            for line in member.detail.splitlines():
                print(f"  {line}")
    for status in result.render_statuses:
        print(
            f"render {status.repo_id}: generated={status.generated}; pointer={status.pointer}"
        )
    for line in result.drift:
        print(f"drift: {line}")


def _print_context_explain(project: render_project.ProjectBinding, result: MaterializationResult, member_id: str | None) -> None:
    """Print the persisted source records, never a fresh discovery approximation."""
    members = [member_id] if member_id else [member.repo_id for member in project.members]
    known = {member.repo_id: member for member in project.members}
    for repo_id in members:
        if repo_id not in known:
            raise ProjectFolderError(f"unknown project member: {repo_id}")
    path = result.folder / CONTEXT_NAME
    try:
        context = json.loads(path.read_text(encoding="utf-8"))
        sources = context["context_sources"]
        bundle = context["context_bundle_sha256"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ProjectFolderError(f"cannot read persisted context provenance: {error}") from error
    if not isinstance(sources, list) or not isinstance(bundle, str):
        raise ProjectFolderError("persisted context provenance has invalid shape")
    print(f"Context bundle sha256: {bundle}")
    print("Context sources (persisted order):")
    for source in sources:
        if not isinstance(source, dict):
            raise ProjectFolderError("persisted context source is not an object")
        source_member = source.get("member_id")
        if source_member is not None and source_member not in members:
            continue
        fields = [
            f"scope={source.get('scope')}",
            f"kind={source.get('kind')}",
            f"path={source.get('path')}",
            f"sha256={source.get('sha256')}",
        ]
        if source_member is not None:
            fields.append(f"member={source_member}")
        if source.get("source_commit") is not None:
            fields.append(f"source_commit={source['source_commit']}")
        if source.get("applies_to"):
            fields.append("applies_to=" + ",".join(source["applies_to"]))
        print("  " + " ".join(fields))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    rebuild_command = commands.add_parser(
        "rebuild", help="materialize a release descriptor without rendering"
    )
    rebuild_command.add_argument("--descriptor", required=True, type=Path)
    rebuild_command.add_argument("--folder", required=True, type=Path)
    rebuild_command.add_argument("--workspace-root", required=True, type=Path)
    rebuild_command.add_argument("--instance", default="default")
    rebuild_command.add_argument("--mode", choices=("shared-read", "exclusive-write"), default="exclusive-write")
    rebuild_command.add_argument("--package", type=Path)
    rebuild_command.add_argument("--source-host")
    rebuild_command.add_argument("--receipt-output", type=Path)
    for name in ("setup", "sync", "status", "refresh-context", "context", "destroy"):
        command = commands.add_parser(name)
        command.add_argument(
            "--project", required=True, type=Path, help="canonical project.toml"
        )
        command.add_argument(
            "--folder", required=True, type=Path, help="derived project folder"
        )
        command.add_argument(
            "--instance", default="default", help="materialization instance identity (default: default)"
        )
        command.add_argument(
            "--mode", choices=("shared-read", "exclusive-write"), default="exclusive-write",
            help="instance mode (default: exclusive-write)",
        )
        command.add_argument(
            "--workspace-root",
            type=Path,
            help="primary repository parent (default: parent of the home repository)",
        )
        command.add_argument(
            "--environment-records-dir",
            type=Path,
            default=render_project.ENVIRONMENT_RECORDS_DIR,
            help="directory to search for environment-record/v1 files (default: templates/dispatch/environment-record)",
        )
        if name == "destroy":
            command.add_argument("--check", action="store_true", help="validate destruction without removing the instance")
        if name == "setup":
            command.add_argument(
                "--enforce-readonly", action="store_true", default=None,
                help="on shared-read instances, remove member worktree write bits after setup (Unix-local)",
            )
        if name == "context":
            command.add_argument("--member", help="member whose repository context to explain")
            command.add_argument("--explain", action="store_true", help="print source precedence and provenance")
    lease_command = commands.add_parser("lease", help="manage a local-only advisory instance lease")
    lease_command.add_argument("action", choices=("acquire", "heartbeat", "release", "status"))
    lease_command.add_argument("--project", required=True, type=Path, help="canonical project.toml")
    lease_command.add_argument("--folder", required=True, type=Path, help="derived project folder")
    lease_command.add_argument("--instance", default="default", help="materialization instance identity (default: default)")
    lease_command.add_argument("--mode", choices=("shared-read", "exclusive-write"), default="exclusive-write")
    lease_command.add_argument("--workspace-root", type=Path, help="primary repository parent (default: parent of the home repository)")
    lease_command.add_argument("--host", help="local holder host (default: AGENTOPS_PROJECT_LEASE_HOST or hostname)")
    lease_command.add_argument("--pid", help="local holder pid (default: AGENTOPS_PROJECT_LEASE_PID or this process)")
    lease_command.add_argument("--runtime-session-id", help="runtime session identity (default: AGENTOPS_PROJECT_RUNTIME_SESSION_ID when set)")
    args = parser.parse_args(argv)

    try:
        if args.command == "rebuild":
            result = rebuild_release(
                args.descriptor,
                args.folder,
                workspace_root=args.workspace_root,
                instance=args.instance,
                mode=args.mode,
                package_path=args.package,
                source_host=args.source_host,
                receipt_output=args.receipt_output,
            )
            _print_result(result)
            return 0
        project = render_project.load_project(
            args.project,
            workspace_root=args.workspace_root,
            allow_missing_members=args.command == "status",
        )
        if args.command == "lease":
            record = lease(
                project, args.folder, action=args.action, instance=args.instance, mode=args.mode,
                host=args.host, pid=args.pid, runtime_session_id=args.runtime_session_id,
            )
            print(json.dumps(record, indent=2, sort_keys=True) if record is not None else "null")
            return 0
        if args.command == "destroy":
            result = destroy(project, args.folder, instance=args.instance, mode=args.mode, check_only=args.check)
        else:
            result = materialize(
                project, args.folder, command="status" if args.command == "context" else args.command, instance=args.instance,
                mode=args.mode, enforce_readonly=getattr(args, "enforce_readonly", None),
                environment_records_dir=args.environment_records_dir,
            )
        _print_result(result)
        if args.command == "context" and args.explain:
            _print_context_explain(project, result, args.member)
    except (ProjectFolderError, render_project.ProjectRenderError, project_release.ReleaseError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1 if result.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
