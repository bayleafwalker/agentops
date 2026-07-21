#!/usr/bin/env python3
"""Check and synchronize canonical dispatch skills into opted-in repositories."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "skills"
SYNCABLE_STATUSES = {"drifted", "missing"}


class SyncError(ValueError):
    """Raised when the requested synchronization cannot be performed safely."""


class DirtyWorktreeError(SyncError):
    """Raised when skill paths have uncommitted changes."""


@dataclass(frozen=True)
class SkillStatus:
    name: str
    content: str
    symlink: str
    diff: str = ""

    @property
    def needs_sync(self) -> bool:
        return self.content in SYNCABLE_STATUSES or (
            self.content != "repo-local" and self.symlink != "in-sync"
        )


def _path_entries(root: Path) -> list[tuple[str, str, bytes]]:
    if root.is_symlink():
        return [("link", ".", os.readlink(root).encode("utf-8"))]

    entries: list[tuple[str, str, bytes]] = []
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories: list[str] = []
        for name in sorted(directory_names):
            candidate = current_path / name
            relative = candidate.relative_to(root).as_posix()
            if candidate.is_symlink():
                entries.append(("link", relative, os.readlink(candidate).encode("utf-8")))
            else:
                entries.append(("dir", relative, b""))
                directories.append(name)
        directory_names[:] = directories

        for name in sorted(file_names):
            candidate = current_path / name
            relative = candidate.relative_to(root).as_posix()
            if candidate.is_symlink():
                entries.append(("link", relative, os.readlink(candidate).encode("utf-8")))
            else:
                entries.append(("file", relative, candidate.read_bytes()))
    return entries


def tree_digest(root: Path) -> str:
    """Return a stable digest of a skill tree including paths, links, and contents."""
    digest = hashlib.sha256()
    for kind, relative, value in _path_entries(root):
        digest.update(kind.encode("utf-8"))
        digest.update(b"\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value)
        digest.update(b"\0")
    return digest.hexdigest()


def _tree_diff(template: Path, repository: Path) -> str:
    left = {relative: (kind, value) for kind, relative, value in _path_entries(template)}
    right = {relative: (kind, value) for kind, relative, value in _path_entries(repository)}
    chunks: list[str] = []

    for relative in sorted(set(left) | set(right)):
        template_entry = left.get(relative)
        repository_entry = right.get(relative)
        if template_entry is None:
            chunks.append(f"Only in repository: {relative}")
            continue
        if repository_entry is None:
            chunks.append(f"Only in template: {relative}")
            continue

        template_kind, template_value = template_entry
        repository_kind, repository_value = repository_entry
        if template_kind != repository_kind:
            chunks.append(
                f"Type differs for {relative}: template={template_kind}, repository={repository_kind}"
            )
            continue
        if template_value == repository_value:
            continue
        if template_kind != "file":
            chunks.append(f"Value differs for {relative}")
            continue
        try:
            template_text = template_value.decode("utf-8")
            repository_text = repository_value.decode("utf-8")
        except UnicodeDecodeError:
            chunks.append(f"Binary content differs for {relative}")
            continue
        chunks.extend(
            difflib.unified_diff(
                template_text.splitlines(),
                repository_text.splitlines(),
                fromfile=f"template/{relative}",
                tofile=f"repository/{relative}",
                lineterm="",
            )
        )

    return "\n".join(chunks)


def _template_is_repo_local(repo_root: Path, template_root: Path) -> bool:
    """Return whether the canonical template tree is owned by this repository."""
    try:
        template_root.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return True


def _expected_symlink(repo_root: Path, name: str, template_root: Path) -> str:
    link = repo_root / ".claude" / "skills" / name
    if _template_is_repo_local(repo_root, template_root):
        return os.path.relpath(template_root / name, start=link.parent)
    return f"../../.agents/skills/{name}"


def _symlink_status(repo_root: Path, name: str, template_root: Path) -> str:
    link = repo_root / ".claude" / "skills" / name
    expected = _expected_symlink(repo_root, name, template_root)
    if link.is_symlink():
        return "in-sync" if os.readlink(link) == expected else "drifted"
    return "drifted" if link.exists() else "missing"


def inspect_skills(
    repo_root: Path,
    names: Iterable[str],
    *,
    template_root: Path = TEMPLATE_ROOT,
) -> list[SkillStatus]:
    """Compare selected skill trees and their Claude skill symlinks."""
    statuses: list[SkillStatus] = []
    canonical_source = _template_is_repo_local(repo_root, template_root)
    for name in names:
        template = template_root / name
        repository = repo_root / ".agents" / "skills" / name
        if not template.is_dir():
            statuses.append(SkillStatus(name, "repo-local", "not-applicable"))
            continue
        if canonical_source:
            statuses.append(SkillStatus(name, "canonical", _symlink_status(repo_root, name, template_root)))
            continue
        if not repository.is_dir() or repository.is_symlink():
            statuses.append(SkillStatus(name, "missing", _symlink_status(repo_root, name, template_root)))
            continue
        if tree_digest(template) == tree_digest(repository):
            statuses.append(SkillStatus(name, "in-sync", _symlink_status(repo_root, name, template_root)))
            continue
        statuses.append(
            SkillStatus(
                name,
                "drifted",
                _symlink_status(repo_root, name, template_root),
                _tree_diff(template, repository),
            )
        )
    return statuses


def _manifest_skills(repo_root: Path) -> list[str]:
    manifests = sorted(repo_root.glob("*.dispatch.json"))
    if len(manifests) != 1:
        if not manifests:
            raise SyncError(f"{repo_root}: no *.dispatch.json manifest; pass --skills explicitly")
        raise SyncError(f"{repo_root}: expected one *.dispatch.json manifest")
    value = json.loads(manifests[0].read_text(encoding="utf-8"))
    selected = value.get("skills", {}).get("selected") if isinstance(value, dict) else None
    if not isinstance(selected, list) or not selected or not all(isinstance(name, str) and name for name in selected):
        raise SyncError(f"{manifests[0]}: skills.selected must be a non-empty string array")
    return selected


def resolve_skills(repo_root: Path, explicit: Iterable[str] | None) -> list[str]:
    """Use explicit skills when provided, otherwise read the repository manifest."""
    source = explicit if explicit is not None else _manifest_skills(repo_root)
    names: list[str] = []
    for value in source:
        for name in value.split(","):
            normalized = name.strip()
            if normalized and normalized not in names:
                names.append(normalized)
    if not names:
        raise SyncError("at least one skill must be selected")
    return names


def _dirty_skill_paths(repo_root: Path, names: Iterable[str]) -> str:
    pathspecs: list[str] = []
    for name in names:
        pathspecs.extend((f".agents/skills/{name}", f".claude/skills/{name}"))
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                *pathspecs,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise SyncError("git is required for --apply") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or "not a git worktree"
        raise SyncError(f"{repo_root}: cannot inspect skill worktree state: {detail}")
    return result.stdout.strip()


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _copy_skill(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staged = Path(temporary) / source.name
        shutil.copytree(source, staged, symlinks=True)
        _remove_path(destination)
        staged.rename(destination)


def _repair_symlink(repo_root: Path, name: str, template_root: Path) -> None:
    link = repo_root / ".claude" / "skills" / name
    link.parent.mkdir(parents=True, exist_ok=True)
    _remove_path(link)
    link.symlink_to(_expected_symlink(repo_root, name, template_root))


def apply_sync(
    repo_root: Path,
    names: Iterable[str],
    *,
    template_root: Path = TEMPLATE_ROOT,
) -> list[SkillStatus]:
    """Copy canonical selected skills and repair their symlinks when the worktree is clean."""
    names = list(names)
    dirty = _dirty_skill_paths(repo_root, names)
    if dirty:
        raise DirtyWorktreeError(
            "refusing --apply because a selected .agents/skills or .claude/skills path is dirty:\n"
            f"{dirty}"
        )

    statuses = inspect_skills(repo_root, names, template_root=template_root)
    for status in statuses:
        if status.content == "repo-local":
            continue
        if status.content in SYNCABLE_STATUSES:
            _copy_skill(template_root / status.name, repo_root / ".agents" / "skills" / status.name)
        if status.symlink != "in-sync":
            _repair_symlink(repo_root, status.name, template_root)
    return inspect_skills(repo_root, names, template_root=template_root)


def _print_statuses(statuses: Iterable[SkillStatus]) -> None:
    for status in statuses:
        print(f"{status.name}: {status.content}; symlink: {status.symlink}")
        if status.diff:
            print(status.diff)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="compare selected skills with the canonical template")
    check.add_argument("--repo", required=True, type=Path, help="repository root")
    check.add_argument("--skills", nargs="+", help="override manifest-selected skill names")
    check.add_argument("--apply", action="store_true", help="copy drifted or missing canonical skills")
    args = parser.parse_args(argv)

    repo_root = args.repo.resolve()
    try:
        names = resolve_skills(repo_root, args.skills)
        before = inspect_skills(repo_root, names)
        if args.apply:
            _print_statuses(before)
            statuses = apply_sync(repo_root, names)
            print("after apply:")
        else:
            statuses = before
        _print_statuses(statuses)
    except SyncError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    return 1 if any(status.needs_sync for status in statuses) else 0


if __name__ == "__main__":
    raise SystemExit(main())
