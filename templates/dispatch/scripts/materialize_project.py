#!/usr/bin/env python3
"""Create and synchronize rebuildable multi-repository project folders."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import render_project


TOOL_ID = "agentops-project-folder/v1"
MARKER_NAME = ".agentops-project-folder.json"
CONTEXT_NAME = "project.context.json"
MEMBERS_DIRECTORY = "members"
BLOCKED_STATUSES = {"dirty", "non-fast-forward", "unexpected-branch"}


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


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _marker(project: render_project.ProjectBinding) -> dict[str, object]:
    return {
        "tool": TOOL_ID,
        "project_id": project.project_id,
        "canonical_project": str(project.project_path),
    }


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
    allowed = {MARKER_NAME, CONTEXT_NAME, "AGENTS.md", MEMBERS_DIRECTORY}
    unexpected = sorted(entries - allowed)
    if unexpected:
        raise ProjectFolderError(
            f"project folder contains non-derived path(s): {', '.join(unexpected)}"
        )
    expected_marker = _marker(project)
    if marker_path.exists():
        try:
            current_marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProjectFolderError(
                f"cannot read project-folder marker: {error}"
            ) from error
        if current_marker != expected_marker:
            raise ProjectFolderError(
                f"project-folder marker does not match {project.project_path}"
            )
    else:
        _atomic_write(marker_path, _json_bytes(expected_marker))
    members_root = folder / MEMBERS_DIRECTORY
    if members_root.is_symlink():
        raise ProjectFolderError(
            f"members directory must not be a symlink: {members_root}"
        )
    if members_root.exists() and not members_root.is_dir():
        raise ProjectFolderError(f"members path must be a directory: {members_root}")
    members_root.mkdir(exist_ok=True)
    return folder


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


def _materialized_branch(project: render_project.ProjectBinding, repo_id: str) -> str:
    return f"agentops-project/{project.project_id}/{repo_id}"


def _common_git_dir(repo: Path) -> Path:
    result = _git(repo, "rev-parse", "--git-common-dir")
    value = Path(result.stdout.strip())
    return (value if value.is_absolute() else repo / value).resolve()


def _validate_existing_worktree(primary: Path, worktree: Path, branch: str) -> None:
    if worktree.is_symlink() or not worktree.is_dir():
        raise ProjectFolderError(
            f"member worktree must be a real directory: {worktree}"
        )
    if _common_git_dir(worktree) != _common_git_dir(primary):
        raise ProjectFolderError(
            f"member path is not a worktree of {primary}: {worktree}"
        )
    current = _git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
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
) -> tuple[Path, str]:
    worktree = folder / MEMBERS_DIRECTORY / member.repo_id
    branch = _materialized_branch(project, member.repo_id)
    if worktree.exists() or worktree.is_symlink():
        _validate_existing_worktree(member.repo_root, worktree, branch)
        _git(worktree, "branch", f"--set-upstream-to={default_ref}", branch)
        return worktree, branch

    worktree.parent.mkdir(parents=True, exist_ok=True)
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
            default_ref,
        )
    _git(worktree, "branch", f"--set-upstream-to={default_ref}", branch)
    return worktree, branch


def _worktree_state(
    member: render_project.MemberBinding,
    worktree: Path,
    branch: str,
    default_ref: str,
) -> WorktreeState:
    current = _git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    head = _git(worktree, "rev-parse", "HEAD").stdout.strip()
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
            f"expected {branch}; found {actual}",
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
            dirty,
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
            "current",
        )
    ancestor = _git(worktree, "merge-base", "--is-ancestor", head, target, check=False)
    if ancestor.returncode == 0:
        _git(worktree, "merge", "--ff-only", default_ref)
        updated = _git(worktree, "rev-parse", "HEAD").stdout.strip()
        return WorktreeState(
            member.repo_id,
            member.repo_root,
            worktree,
            branch,
            default_ref,
            updated,
            "updated",
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
        f"local {head} cannot fast-forward to {default_ref} ({target})",
    )


def _resolved_context(
    project: render_project.ProjectBinding,
    folder: Path,
    command: str,
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
    return {
        "schema_version": 1,
        "tool": TOOL_ID,
        "command": command,
        "project_id": project.project_id,
        "display_name": project.display_name,
        "home_repo": project.home_repo,
        "canonical_project": str(project.project_path),
        "folder": str(folder),
        "members": members,
    }


def _folder_agents(
    project: render_project.ProjectBinding,
    states: tuple[WorktreeState, ...],
) -> bytes:
    lines = [
        "<!-- agentops-project-folder: DO NOT HAND-EDIT",
        f"     project_id: {project.project_id}",
        f"     tool: {TOOL_ID}",
        "-->",
        "",
        f"# {project.display_name} project scope",
        "",
        f"Canonical binding: `{project.project_path}`.",
        "This folder is derived and deletable; repository truth remains in the member repositories.",
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
            f"tracks `{state.default_ref}`)"
        )
        for note in binding.path_notes:
            lines.append(f"  - {note}")
    lines.extend(
        (
            "",
            f"Resolved machine context: `{CONTEXT_NAME}`.",
            "Run the project-folder sync command before starting a new cross-repository work window.",
            "",
        )
    )
    return "\n".join(lines).encode("utf-8")


def _write_resolved_context(
    project: render_project.ProjectBinding,
    folder: Path,
    command: str,
    states: tuple[WorktreeState, ...],
    render_statuses: tuple[render_project.MemberStatus, ...],
) -> None:
    _atomic_write(folder / "AGENTS.md", _folder_agents(project, states))
    _atomic_write(
        folder / CONTEXT_NAME,
        _json_bytes(
            _resolved_context(project, folder, command, states, render_statuses)
        ),
    )


def materialize(
    project: render_project.ProjectBinding,
    folder: Path,
    *,
    command: str,
) -> MaterializationResult:
    folder = _prepare_folder(project, folder, require_existing=command == "sync")
    states: list[WorktreeState] = []
    for member in project.members:
        _fetch_and_prune(member.repo_root)
        default_ref = _default_ref(member.repo_root)
        worktree, branch = _ensure_worktree(project, member, folder, default_ref)
        states.append(_worktree_state(member, worktree, branch, default_ref))

    state_tuple = tuple(states)
    render_statuses: tuple[render_project.MemberStatus, ...] = ()
    if not any(state.blocked for state in state_tuple):
        materialized_project = render_project.load_project(
            folder / MEMBERS_DIRECTORY / project.home_repo / "project.toml",
            workspace_root=folder / MEMBERS_DIRECTORY,
        )
        render_statuses = tuple(render_project.apply_project(materialized_project))

    for member in project.members:
        _git(member.repo_root, "worktree", "prune")
    _write_resolved_context(project, folder, command, state_tuple, render_statuses)
    return MaterializationResult(command, folder, state_tuple, render_statuses)


def _print_result(result: MaterializationResult) -> None:
    print(f"{result.command}: {result.folder}")
    for member in result.members:
        print(
            f"{member.repo_id}: {member.status}; branch={member.branch}; "
            f"default={member.default_ref}; head={member.head}"
        )
        if member.detail:
            for line in member.detail.splitlines():
                print(f"  {line}")
    for status in result.render_statuses:
        print(
            f"render {status.repo_id}: generated={status.generated}; pointer={status.pointer}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("setup", "sync"):
        command = commands.add_parser(name)
        command.add_argument(
            "--project", required=True, type=Path, help="canonical project.toml"
        )
        command.add_argument(
            "--folder", required=True, type=Path, help="derived project folder"
        )
        command.add_argument(
            "--workspace-root",
            type=Path,
            help="primary repository parent (default: parent of the home repository)",
        )
    args = parser.parse_args(argv)

    try:
        project = render_project.load_project(
            args.project,
            workspace_root=args.workspace_root,
        )
        result = materialize(project, args.folder, command=args.command)
        _print_result(result)
    except (ProjectFolderError, render_project.ProjectRenderError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1 if result.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
