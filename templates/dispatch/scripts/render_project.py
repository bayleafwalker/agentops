#!/usr/bin/env python3
"""Render and check deterministic project instruction bundles."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
from uuid import UUID


REPO_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
FRONTMATTER_RE = re.compile(
    rb"\A---(?:\r\n|\n)(?P<header>.*?)(?:\r\n|\n)---(?:\r\n|\n)",
    re.DOTALL,
)
RENDER_LEVELS_RE = re.compile(r"^render_levels\s*:\s*\[(?P<levels>[^]]*)\]\s*$")
SOURCE_HASH_RE = re.compile(rb"source_bundle_sha256: (?P<digest>[0-9a-f]{64})")
RENDER_LEVELS = {"baseline", "full"}
RENDER_MODES = RENDER_LEVELS | {"none"}
RENDER_PREFIX = b"<!-- agentops-render: DO NOT HAND-EDIT\n"
POINTER_START = b"<!-- agentops-project-pointer:start -->"
POINTER_END = b"<!-- agentops-project-pointer:end -->"
POINTER_BLOCK = b"\n".join(
    (
        POINTER_START,
        b"See `.agents/project.generated.md` for cross-repo project context "
        b"(agentops-managed; do not hand-edit).",
        POINTER_END,
    )
)


class ProjectRenderError(ValueError):
    """Raised when a project cannot be checked or rendered safely."""


class DirtyProjectError(ProjectRenderError):
    """Raised when render inputs or managed outputs are dirty."""


@dataclass(frozen=True)
class MemberBinding:
    repo_id: str
    backlog: bool
    render: str
    path_notes: tuple[str, ...]
    repo_root: Path

    @property
    def generated_path(self) -> Path:
        return self.repo_root / ".agents" / "project.generated.md"

    @property
    def agents_path(self) -> Path:
        return self.repo_root / "AGENTS.md"

    @property
    def override_path(self) -> Path:
        return (
            self.repo_root
            / ".agents"
            / "overlays"
            / f"{self.repo_id}.project-overrides.md"
        )


@dataclass(frozen=True)
class ProjectBinding:
    project_path: Path
    workspace_root: Path
    project_id: str
    display_name: str
    home_repo: str
    members: tuple[MemberBinding, ...]

    @property
    def home_root(self) -> Path:
        return self.workspace_root / self.home_repo

    @property
    def sources_root(self) -> Path:
        return self.home_root / ".project" / "sources"


@dataclass(frozen=True)
class SourceFragment:
    path: Path
    levels: frozenset[str]
    raw: bytes
    body: bytes


@dataclass(frozen=True)
class ExpectedRender:
    source_bundle_sha256: str
    header: bytes
    body: bytes

    @property
    def content(self) -> bytes:
        return self.header + self.body


@dataclass(frozen=True)
class MemberStatus:
    repo_id: str
    render: str
    generated: str
    pointer: str
    detail: str = ""

    @property
    def needs_sync(self) -> bool:
        clean = {"in-sync", "not-applicable"}
        return self.generated not in clean or self.pointer not in clean


def _exact_keys(
    value: dict[str, object],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    subject: str,
) -> None:
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required - optional)
    if missing:
        raise ProjectRenderError(
            f"{subject}: missing required field(s): {', '.join(missing)}"
        )
    if extra:
        raise ProjectRenderError(f"{subject}: unsupported field(s): {', '.join(extra)}")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectRenderError(f"{field} must be a non-empty string")
    return value


def _canonical_uuid4(value: object) -> str:
    text = _required_text(value, "project_id")
    try:
        parsed = UUID(text)
    except ValueError as error:
        raise ProjectRenderError("project_id must be a UUID") from error
    if parsed.version != 4 or str(parsed) != text:
        raise ProjectRenderError("project_id must be a canonical UUIDv4")
    return text


def load_project(
    project_path: Path, *, workspace_root: Path | None = None
) -> ProjectBinding:
    """Load and validate a canonical project.toml and its member locations."""
    project_path = project_path.resolve()
    if project_path.name != "project.toml":
        raise ProjectRenderError(
            f"{project_path}: project file must be named project.toml"
        )
    try:
        raw = tomllib.loads(project_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ProjectRenderError(
            f"{project_path}: project file does not exist"
        ) from error
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ProjectRenderError(
            f"{project_path}: cannot read project: {error}"
        ) from error
    if not isinstance(raw, dict):
        raise ProjectRenderError(f"{project_path}: project root must be a table")
    _exact_keys(
        raw,
        required={
            "schema_version",
            "project_id",
            "display_name",
            "home_repo",
            "members",
        },
        subject=str(project_path),
    )
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ProjectRenderError("schema_version must be integer 1")

    project_id = _canonical_uuid4(raw["project_id"])
    display_name = _required_text(raw["display_name"], "display_name")
    home_repo = _required_text(raw["home_repo"], "home_repo")
    if not REPO_ID_RE.fullmatch(home_repo):
        raise ProjectRenderError("home_repo must match ^[A-Za-z0-9._-]+$")

    raw_members = raw["members"]
    if not isinstance(raw_members, list) or not raw_members:
        raise ProjectRenderError("members must be a non-empty array of tables")

    workspace = (workspace_root or project_path.parent.parent).resolve()
    expected_home = (workspace / home_repo).resolve()
    if project_path.parent != expected_home:
        raise ProjectRenderError(
            f"{project_path}: canonical project.toml must live at the home repo root {expected_home}"
        )

    members: list[MemberBinding] = []
    seen: set[str] = set()
    for index, raw_member in enumerate(raw_members):
        subject = f"members[{index}]"
        if not isinstance(raw_member, dict):
            raise ProjectRenderError(f"{subject} must be a table")
        _exact_keys(
            raw_member,
            required={"repo_id", "backlog", "render"},
            optional={"path_notes"},
            subject=subject,
        )
        repo_id = _required_text(raw_member["repo_id"], f"{subject}.repo_id")
        if not REPO_ID_RE.fullmatch(repo_id):
            raise ProjectRenderError(f"{subject}.repo_id must match ^[A-Za-z0-9._-]+$")
        if repo_id in seen:
            raise ProjectRenderError(f"duplicate member repo_id: {repo_id}")
        seen.add(repo_id)
        if type(raw_member["backlog"]) is not bool:
            raise ProjectRenderError(f"{subject}.backlog must be a boolean")
        render = _required_text(raw_member["render"], f"{subject}.render")
        if render not in RENDER_MODES:
            raise ProjectRenderError(
                f"{subject}.render must be full, baseline, or none"
            )
        raw_notes = raw_member.get("path_notes", [])
        if not isinstance(raw_notes, list) or not all(
            isinstance(note, str) and note.strip() for note in raw_notes
        ):
            raise ProjectRenderError(
                f"{subject}.path_notes must be an array of non-empty strings"
            )
        repo_root = (workspace / repo_id).resolve()
        if not repo_root.is_dir():
            raise ProjectRenderError(f"member repository does not exist: {repo_root}")
        members.append(
            MemberBinding(
                repo_id=repo_id,
                backlog=raw_member["backlog"],
                render=render,
                path_notes=tuple(raw_notes),
                repo_root=repo_root,
            )
        )

    if home_repo not in seen:
        raise ProjectRenderError("home_repo must also appear exactly once in members")
    project = ProjectBinding(
        project_path=project_path,
        workspace_root=workspace,
        project_id=project_id,
        display_name=display_name,
        home_repo=home_repo,
        members=tuple(members),
    )
    if (
        any(member.render != "none" for member in members)
        and not project.sources_root.is_dir()
    ):
        raise ProjectRenderError(
            f"project sources directory does not exist: {project.sources_root}"
        )
    return project


def _parse_fragment(path: Path) -> SourceFragment:
    if path.is_symlink() or not path.is_file():
        raise ProjectRenderError(f"project source must be a regular file: {path}")
    raw = path.read_bytes()
    match = FRONTMATTER_RE.match(raw)
    if match is None:
        raise ProjectRenderError(f"{path}: missing --- frontmatter with render_levels")
    try:
        header = match.group("header").decode("utf-8")
        raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProjectRenderError(f"{path}: source must be UTF-8") from error
    lines = [line.strip() for line in header.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ProjectRenderError(f"{path}: frontmatter must contain only render_levels")
    levels_match = RENDER_LEVELS_RE.fullmatch(lines[0])
    if levels_match is None:
        raise ProjectRenderError(
            f"{path}: render_levels must use [baseline, full] syntax"
        )
    levels = [
        part.strip() for part in levels_match.group("levels").split(",") if part.strip()
    ]
    if not levels or len(set(levels)) != len(levels) or set(levels) - RENDER_LEVELS:
        raise ProjectRenderError(
            f"{path}: render_levels must contain unique baseline/full values"
        )
    return SourceFragment(path, frozenset(levels), raw, raw[match.end() :])


def load_fragments(project: ProjectBinding) -> tuple[SourceFragment, ...]:
    if not project.sources_root.exists():
        return ()
    return tuple(
        _parse_fragment(path) for path in sorted(project.sources_root.glob("*.md"))
    )


def _override_bytes(member: MemberBinding) -> bytes:
    path = member.override_path
    if not path.exists():
        return b""
    if path.is_symlink() or not path.is_file():
        raise ProjectRenderError(f"member override must be a regular file: {path}")
    value = path.read_bytes()
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProjectRenderError(f"{path}: override must be UTF-8") from error
    return value


def expected_render(
    project: ProjectBinding,
    member: MemberBinding,
    fragments: tuple[SourceFragment, ...],
) -> ExpectedRender:
    if member.render == "none":
        raise ProjectRenderError(
            f"{member.repo_id}: render:none has no generated output"
        )
    selected = tuple(
        fragment for fragment in fragments if member.render in fragment.levels
    )
    override = _override_bytes(member)
    bundle = b"".join(fragment.raw for fragment in selected) + override
    digest = hashlib.sha256(bundle).hexdigest()
    header = (
        "<!-- agentops-render: DO NOT HAND-EDIT\n"
        f"     project_id: {project.project_id}\n"
        f"     project: {project.display_name}\n"
        f"     member: {member.repo_id}\n"
        f"     render: {member.render}\n"
        f"     source_bundle_sha256: {digest}\n"
        "     tool: agentops-render/v1\n"
        "-->\n"
    ).encode("utf-8")
    body = b"".join(fragment.body for fragment in selected) + override
    return ExpectedRender(digest, header, body)


def _pointer_counts(content: bytes) -> tuple[int, int]:
    return content.count(POINTER_START), content.count(POINTER_END)


def _pointer_span(content: bytes) -> tuple[int, int]:
    starts, ends = _pointer_counts(content)
    if starts != 1 or ends != 1:
        raise ProjectRenderError(
            "AGENTS.md has duplicate or unbalanced project pointer sentinels"
        )
    start = content.index(POINTER_START)
    try:
        end = content.index(POINTER_END, start) + len(POINTER_END)
    except ValueError as error:
        raise ProjectRenderError(
            "AGENTS.md project pointer sentinels are out of order"
        ) from error
    return start, end


def _with_pointer(content: bytes) -> bytes:
    starts, ends = _pointer_counts(content)
    if starts == 0 and ends == 0:
        if not content:
            return POINTER_BLOCK + b"\n"
        if content.endswith(b"\n\n"):
            separator = b""
        elif content.endswith(b"\n"):
            separator = b"\n"
        else:
            separator = b"\n\n"
        return content + separator + POINTER_BLOCK + b"\n"
    start, end = _pointer_span(content)
    return content[:start] + POINTER_BLOCK + content[end:]


def _without_pointer(content: bytes) -> bytes:
    starts, ends = _pointer_counts(content)
    if starts == 0 and ends == 0:
        return content
    start, end = _pointer_span(content)
    return content[:start] + content[end:]


def _read_regular_or_empty(path: Path) -> bytes:
    if path.is_symlink():
        raise ProjectRenderError(f"managed path must not be a symlink: {path}")
    if not path.exists():
        return b""
    if not path.is_file():
        raise ProjectRenderError(f"managed path must be a regular file: {path}")
    return path.read_bytes()


def _pointer_status(member: MemberBinding) -> str:
    content = _read_regular_or_empty(member.agents_path)
    starts, ends = _pointer_counts(content)
    if member.render == "none":
        if starts == 0 and ends == 0:
            return "not-applicable"
        try:
            return (
                "unexpected"
                if _without_pointer(content) != content
                else "not-applicable"
            )
        except ProjectRenderError:
            return "invalid"
    try:
        expected = _with_pointer(content)
    except ProjectRenderError:
        return "invalid"
    if starts == 0 and ends == 0:
        return "missing"
    return "in-sync" if expected == content else "hand-edited"


def _generated_status(
    member: MemberBinding, expected: ExpectedRender | None
) -> tuple[str, str]:
    path = member.generated_path
    if path.is_symlink():
        return "invalid", "generated path must not be a symlink"
    if not path.exists():
        return ("not-applicable", "") if member.render == "none" else ("missing", "")
    if not path.is_file():
        return "invalid", "generated path is not a regular file"
    actual = path.read_bytes()
    if member.render == "none":
        if actual.startswith(RENDER_PREFIX):
            return "unexpected", "render:none member retains managed output"
        return "conflict", "render:none output is not agentops-managed"
    assert expected is not None
    header_end = actual.find(b"-->\n")
    if header_end == -1 or not actual.startswith(RENDER_PREFIX):
        return "invalid", "generated output has no valid agentops provenance header"
    header_end += len(b"-->\n")
    actual_header = actual[:header_end]
    actual_body = actual[header_end:]
    digest_match = SOURCE_HASH_RE.search(actual_header)
    if digest_match is None:
        return "invalid", "generated output has no valid source bundle hash"
    declared = digest_match.group("digest").decode("ascii")
    if declared != expected.source_bundle_sha256:
        return "stale", "source or override content changed after the last render"
    if actual_header != expected.header:
        return "stale", "project binding metadata changed after the last render"
    if actual_body != expected.body:
        return "hand-edited", "generated body differs while its source hash is current"
    return "in-sync", ""


def inspect_project(project: ProjectBinding) -> list[MemberStatus]:
    fragments = load_fragments(project)
    statuses: list[MemberStatus] = []
    for member in project.members:
        expected = (
            None
            if member.render == "none"
            else expected_render(project, member, fragments)
        )
        generated, detail = _generated_status(member, expected)
        statuses.append(
            MemberStatus(
                repo_id=member.repo_id,
                render=member.render,
                generated=generated,
                pointer=_pointer_status(member),
                detail=detail,
            )
        )
    return statuses


def _git_dirty(repo_root: Path, pathspecs: set[str]) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *sorted(pathspecs),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "not a git worktree"
        raise ProjectRenderError(
            f"{repo_root}: cannot inspect worktree state: {detail}"
        )
    return result.stdout.strip()


def _dirty_render_paths(project: ProjectBinding) -> str:
    pathspecs: dict[Path, set[str]] = {}
    for member in project.members:
        pathspecs.setdefault(member.repo_root, set()).update(
            {
                "AGENTS.md",
                ".agents/project.generated.md",
                f".agents/overlays/{member.repo_id}.project-overrides.md",
            }
        )
    pathspecs.setdefault(project.home_root, set()).update(
        {"project.toml", ".project/sources"}
    )
    dirty: list[str] = []
    for repo_root, paths in sorted(pathspecs.items(), key=lambda item: str(item[0])):
        result = _git_dirty(repo_root, paths)
        if result:
            dirty.append(f"[{repo_root}]\n{result}")
    return "\n".join(dirty)


def _atomic_write(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise ProjectRenderError(f"refusing to replace symlink: {path}")
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


def apply_project(project: ProjectBinding) -> list[MemberStatus]:
    """Apply deterministic renders after refusing dirty inputs and managed paths."""
    before = inspect_project(project)
    if not any(status.needs_sync for status in before):
        return before
    dirty = _dirty_render_paths(project)
    if dirty:
        raise DirtyProjectError(
            "refusing --apply because project render inputs or managed outputs are dirty:\n"
            f"{dirty}"
        )

    fragments = load_fragments(project)
    operations: list[tuple[MemberBinding, ExpectedRender | None, bytes, bytes]] = []
    for member in project.members:
        agents = _read_regular_or_empty(member.agents_path)
        if member.render == "none":
            if member.generated_path.is_symlink():
                raise ProjectRenderError(
                    f"refusing to remove symlink: {member.generated_path}"
                )
            if member.generated_path.exists():
                current = _read_regular_or_empty(member.generated_path)
                if not current.startswith(RENDER_PREFIX):
                    raise ProjectRenderError(
                        f"refusing to remove non-managed output: {member.generated_path}"
                    )
            without_pointer = _without_pointer(agents)
            operations.append((member, None, agents, without_pointer))
            continue

        expected = expected_render(project, member, fragments)
        operations.append((member, expected, agents, _with_pointer(agents)))

    for member, expected, agents, next_agents in operations:
        if expected is None:
            if member.generated_path.exists():
                member.generated_path.unlink()
        else:
            _atomic_write(member.generated_path, expected.content)
        if next_agents != agents:
            _atomic_write(member.agents_path, next_agents)
    return inspect_project(project)


def _print_statuses(statuses: list[MemberStatus]) -> None:
    for status in statuses:
        print(
            f"{status.repo_id} ({status.render}): "
            f"generated={status.generated}; pointer={status.pointer}"
        )
        if status.detail:
            print(f"  {status.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check project render output for drift")
    check.add_argument(
        "--project", required=True, type=Path, help="canonical project.toml"
    )
    check.add_argument(
        "--workspace-root",
        type=Path,
        help="member repository parent (default: parent of the home repository)",
    )
    check.add_argument(
        "--apply", action="store_true", help="write deterministic render output"
    )
    args = parser.parse_args(argv)

    try:
        project = load_project(args.project, workspace_root=args.workspace_root)
        statuses = inspect_project(project)
        if args.apply:
            _print_statuses(statuses)
            statuses = apply_project(project)
            print("after apply:")
        _print_statuses(statuses)
    except ProjectRenderError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1 if any(status.needs_sync for status in statuses) else 0


if __name__ == "__main__":
    raise SystemExit(main())
