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

import fcntl

import render_project


TOOL_ID = "agentops-project-folder/v2"
TOOL_VERSION = "2"
MARKER_NAME = ".agentops-project-folder.json"
CONTEXT_NAME = "project.context.json"
MEMBERS_DIRECTORY = "members"
LEASE_NAME = ".agentops-project-folder.lease"
LEASE_LOCK_NAME = ".agentops-project-folder.lease.lock"
LEASE_SCHEMA = "agentops-project-folder-lease/v1"
BLOCKED_STATUSES = {"dirty", "non-fast-forward", "unexpected-branch", "unexpected-head"}
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

    @property
    def blocked(self) -> bool:
        return any(member.blocked for member in self.members)


def _git(
    repo: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=False,
            capture_output=True,
            text=True,
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
    if (folder / ".git").exists() or (folder / ".git").is_symlink():
        raise ProjectFolderError(
            f"project folder must not itself be a git repository: {folder}"
        )

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
    if entries and not marker_path.is_file():
        raise ProjectFolderError(
            f"refusing non-empty folder without {MARKER_NAME}: {folder}"
        )
    allowed = {
        MARKER_NAME,
        CONTEXT_NAME,
        "AGENTS.md",
        MEMBERS_DIRECTORY,
        ".session",
        LEASE_NAME,
        LEASE_LOCK_NAME,
    }
    unexpected = sorted(entries - allowed)
    if unexpected:
        raise ProjectFolderError(
            f"project folder contains non-derived path(s): {', '.join(unexpected)}"
        )
    expected_marker = _marker(
        project, instance=instance, mode=mode, readonly_enforced=readonly_enforced
    )
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
    return {
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
        "source_binding_commit": _binding_provenance(project)[0],
        "source_binding_sha256": _binding_provenance(project)[1],
        "context_bundle_sha256": context_bundle_sha256,
        "context_sources": context_sources,
        "folder": str(folder),
        "members": members,
    }


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
    )
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
    if any(marker.get(key) != value for key, value in expected.items()):
        raise ProjectFolderError("project-folder marker changed during context materialization")
    expected["context_bundle_sha256"] = context_bundle_sha256
    _atomic_write(path, _json_bytes(expected))


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
    folder = _prepare_folder(
        project, folder, require_existing=command != "setup", instance=instance,
        mode=mode, readonly_enforced=readonly_enforced, mutate=command != "status",
    )
    binding_commit, _binding_digest = _binding_provenance(project)
    states: list[WorktreeState] = []
    for member in project.members:
        if command in {"setup", "sync"}:
            _fetch_and_prune(member.repo_root)
        default_ref = _default_ref(member.repo_root)
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
            _validate_existing_worktree(
                member.repo_root, worktree, branch, mode=effective_mode
            )
        states.append(
            _worktree_state(
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

    state_tuple = tuple(states)
    if mode == "shared-read" and readonly_enforced and any(
        state.blocked for state in state_tuple
    ):
        raise ProjectFolderError(
            "refusing shared-read filesystem enforcement while member state is blocked"
        )
    render_statuses: tuple[render_project.MemberStatus, ...] = ()
    materialized_project = _validate_instance_binding(project, folder)
    # shared-read intentionally does not render into member worktrees: that
    # would immediately make an otherwise detached inspection instance dirty.
    if command != "status" and mode == "exclusive-write" and not any(state.blocked for state in state_tuple):
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
    return MaterializationResult(command, folder, state_tuple, render_statuses)


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
    initialize = command == "setup" and (
        not requested.exists()
        or (requested.is_dir() and not any(requested.iterdir()))
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
    lease = folder / LEASE_NAME
    if lease.exists() or lease.is_symlink():
        raise ProjectFolderError(f"refusing to destroy leased instance: {lease}")
    session = folder / ".session"
    if session.is_symlink() or (session.is_dir() and any(session.iterdir())):
        raise ProjectFolderError("refusing to destroy instance with non-empty .session")
    states: list[WorktreeState] = []
    for member in project.members:
        default_ref = _default_ref(member.repo_root)
        worktree = folder / MEMBERS_DIRECTORY / member.repo_id
        branch = _materialized_branch(project, instance, member.repo_id)
        effective_mode = _effective_member_mode(member, mode)
        _validate_existing_worktree(
            member.repo_root, worktree, branch, mode=effective_mode
        )
        state = _worktree_state(
            member, worktree, branch, default_ref, mode=effective_mode, advance=False
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
        project = render_project.load_project(
            args.project,
            workspace_root=args.workspace_root,
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
    except (ProjectFolderError, render_project.ProjectRenderError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1 if result.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
