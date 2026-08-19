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
from urllib.parse import urlsplit
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent))
from render_environment_context import render_environment_context  # noqa: E402
from resolve_environment_record import (  # noqa: E402
    EnvironmentResolutionError,
    resolve_environment_record,
)
from validate_vuoro_profiles import ProfileError  # noqa: E402


REPO_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
FRONTMATTER_RE = re.compile(
    rb"\A---(?:\r\n|\n)(?P<header>.*?)(?:\r\n|\n)---(?:\r\n|\n)",
    re.DOTALL,
)
RENDER_LEVELS_RE = re.compile(r"^render_levels\s*:\s*\[(?P<levels>[^]]*)\]\s*$")
SOURCE_HASH_RE = re.compile(rb"source_bundle_sha256: (?P<digest>[0-9a-f]{64})")
RENDER_LEVELS = {"baseline", "full"}
RENDER_MODES = RENDER_LEVELS | {"none"}
MEMBER_RELATIONSHIPS = {
    "implementation",
    "planning-authority",
    "execution-authority",
    "deployment-owner",
    "governance",
    "tooling",
    "reference",
}
MEMBER_ACCESS_MODES = {"write", "reference"}
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

ENV_POINTER_START = b"<!-- agentops-environment-pointer:start -->"
ENV_POINTER_END = b"<!-- agentops-environment-pointer:end -->"
ENV_POINTER_BLOCK = b"\n".join(
    (
        ENV_POINTER_START,
        b"See `.agents/environment.generated.md` for the active Vuoro "
        b"environment's constraints and runbooks (agentops-managed; do not "
        b"hand-edit).",
        ENV_POINTER_END,
    )
)
ENV_RENDER_PREFIX = b"<!-- agentops-render: DO NOT HAND-EDIT\n"
ENV_HASH_RE = re.compile(rb"environment_record_sha256: (?P<digest>[0-9a-f]{64})")
ENVIRONMENT_RECORDS_DIR = Path(__file__).resolve().parent.parent / "environment-record"
RENDER_MANAGED_DOCUMENTS = frozenset({
    ".agents/project.generated.md",
    ".agents/environment.generated.md",
})
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
DEFAULT_REF_RE = re.compile(r"^refs/heads/[A-Za-z0-9._/-]+$")


class ProjectRenderError(ValueError):
    """Raised when a project cannot be checked or rendered safely."""


class DirtyProjectError(ProjectRenderError):
    """Raised when render inputs or managed outputs are dirty."""


@dataclass(frozen=True)
class MemberBinding:
    repo_id: str
    backlog: bool
    render: str
    relationship: str
    access: str
    path_notes: tuple[str, ...]
    required_documents: tuple[str, ...]
    optional_documents: tuple[str, ...]
    forbidden_documents: tuple[str, ...]
    repo_root: Path
    repository: str | None = None
    default_ref: str | None = None

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

    @property
    def environment_path(self) -> Path:
        return self.repo_root / ".agents" / "environment.generated.md"


@dataclass(frozen=True)
class ProjectBinding:
    project_path: Path
    workspace_root: Path
    project_id: str
    display_name: str
    home_repo: str
    members: tuple[MemberBinding, ...]
    role_presets: tuple[tuple[str, str, str, str], ...] = ()

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
    environment: str = "not-applicable"
    environment_pointer: str = "not-applicable"
    environment_detail: str = ""
    documents: tuple[tuple[str, str], ...] = ()

    @property
    def needs_sync(self) -> bool:
        clean = {"in-sync", "not-applicable", "absent", "present"}
        return (
            self.generated not in clean
            or self.pointer not in clean
            or self.environment not in clean
            or self.environment_pointer not in clean
            or any(state not in clean for _path, state in self.documents)
        )


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


def _document_path(value: object, field: str) -> str:
    """Validate a normalized, relative path within one member repository."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProjectRenderError(f"{field} must be a non-empty normalized relative path")
    if value.startswith(("/", "\\")) or WINDOWS_DRIVE_RE.match(value):
        raise ProjectRenderError(f"{field} must be a relative in-repository path")
    if "\\" in value:
        raise ProjectRenderError(f"{field} must use normalized '/' separators")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ProjectRenderError(f"{field} must not contain empty, '.', or '..' path components")
    return value


def canonical_repository_url(value: object, field: str = "repository") -> str:
    """Validate a credential-free canonical HTTPS Git repository URL."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProjectRenderError(f"{field} must be a canonical HTTPS Git URL")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise ProjectRenderError(f"{field} must be a canonical credential-free HTTPS Git URL") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None
        or parsed.path in {"", "/"}
        or parsed.path.endswith("/")
        or "//" in parsed.path
        or any(part in {"", ".", ".."} for part in parsed.path.removeprefix("/").split("/"))
        or parsed.hostname != parsed.hostname.lower()
    ):
        raise ProjectRenderError(f"{field} must be a canonical credential-free HTTPS Git URL")
    return value


def canonical_default_ref(value: object, field: str = "default_ref") -> str:
    if not isinstance(value, str) or not DEFAULT_REF_RE.fullmatch(value):
        raise ProjectRenderError(f"{field} must be a canonical refs/heads/... ref")
    branch = value.removeprefix("refs/heads/")
    if (
        branch.startswith("/")
        or branch.endswith("/")
        or branch.endswith(".")
        or branch.endswith(".lock")
        or "//" in branch
        or "@{" in branch
        or any(ord(char) < 0x20 or char.isspace() for char in branch)
        or any(
        part in {"", ".", ".."} for part in branch.split("/")
        )
    ):
        raise ProjectRenderError(f"{field} must be a canonical refs/heads/... ref")
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
    project_path: Path, *, workspace_root: Path | None = None,
    allow_missing_members: bool = False,
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
        optional={"role_presets"},
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
            optional={"path_notes", "relationship", "access", "documents", "repository", "default_ref"},
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
        relationship = raw_member.get("relationship", "implementation")
        if not isinstance(relationship, str) or relationship not in MEMBER_RELATIONSHIPS:
            allowed = ", ".join(sorted(MEMBER_RELATIONSHIPS))
            raise ProjectRenderError(
                f"{subject}.relationship must be one of: {allowed}"
            )
        access = raw_member.get("access", "write")
        if not isinstance(access, str) or access not in MEMBER_ACCESS_MODES:
            allowed = ", ".join(sorted(MEMBER_ACCESS_MODES))
            raise ProjectRenderError(f"{subject}.access must be one of: {allowed}")
        repository = raw_member.get("repository")
        if repository is not None:
            repository = canonical_repository_url(repository, f"{subject}.repository")
        default_ref = raw_member.get("default_ref")
        if default_ref is not None:
            default_ref = canonical_default_ref(default_ref, f"{subject}.default_ref")
        raw_notes = raw_member.get("path_notes", [])
        if not isinstance(raw_notes, list) or not all(
            isinstance(note, str) and note.strip() for note in raw_notes
        ):
            raise ProjectRenderError(
                f"{subject}.path_notes must be an array of non-empty strings"
            )
        required_documents = ["AGENTS.md"]
        optional_documents: list[str] = []
        forbidden_documents: list[str] = []
        if render == "none" or access == "reference":
            forbidden_documents.append(".agents/project.generated.md")
        else:
            required_documents.append(".agents/project.generated.md")
        raw_documents = raw_member.get("documents", {})
        if isinstance(raw_documents, list):
            explicit_required = raw_documents
            raw_documents = {"required": explicit_required}
        if not isinstance(raw_documents, dict):
            raise ProjectRenderError(f"{subject}.documents must be a table or array")
        allowed_document_keys = {"required", "optional", "forbidden", "authored", "generated"}
        unknown_document_keys = set(raw_documents) - allowed_document_keys
        if unknown_document_keys:
            raise ProjectRenderError(
                f"{subject}.documents has unsupported field(s): {', '.join(sorted(unknown_document_keys))}"
            )
        def document_list(key: str) -> list[str]:
            value = raw_documents.get(key, [])
            if not isinstance(value, list):
                raise ProjectRenderError(f"{subject}.documents.{key} must be an array of paths")
            return [_document_path(item, f"{subject}.documents.{key}[{index}]") for index, item in enumerate(value)]
        generic_required = document_list("required")
        authored_documents = document_list("authored")
        generated_documents = document_list("generated")
        optional_documents.extend(document_list("optional"))
        forbidden_documents.extend(document_list("forbidden"))
        if any(path in RENDER_MANAGED_DOCUMENTS for path in authored_documents):
            raise ProjectRenderError(f"{subject}.documents.authored may only name authored documents")
        if any(path not in RENDER_MANAGED_DOCUMENTS for path in generated_documents):
            raise ProjectRenderError(f"{subject}.documents.generated may only name renderer-managed documents")
        required_documents.extend(generic_required)
        required_documents.extend(authored_documents)
        required_documents.extend(generated_documents)
        groups = {
            "required": required_documents,
            "optional": optional_documents,
            "forbidden": forbidden_documents,
        }
        for left_name, left in groups.items():
            for right_name, right in groups.items():
                if left_name >= right_name:
                    continue
                overlap = sorted(set(left) & set(right))
                if overlap:
                    raise ProjectRenderError(
                        f"{subject}.documents contradicts {left_name}/{right_name}: {', '.join(overlap)}"
                    )
        required_documents = list(dict.fromkeys(required_documents))
        optional_documents = list(dict.fromkeys(optional_documents))
        forbidden_documents = list(dict.fromkeys(forbidden_documents))
        repo_root = (workspace / repo_id).resolve()
        if not repo_root.is_dir() and not allow_missing_members:
            raise ProjectRenderError(f"member repository does not exist: {repo_root}")
        members.append(
            MemberBinding(
                repo_id=repo_id,
                backlog=raw_member["backlog"],
                render=render,
                relationship=relationship,
                access=access,
                path_notes=tuple(raw_notes),
                required_documents=tuple(required_documents),
                optional_documents=tuple(optional_documents),
                forbidden_documents=tuple(forbidden_documents),
                repo_root=repo_root,
                repository=repository,
                default_ref=default_ref,
            )
        )

    role_presets: list[tuple[str, str, str, str]] = []
    raw_roles = raw.get("role_presets", {})
    if not isinstance(raw_roles, dict):
        raise ProjectRenderError("role_presets must be a table")
    for role, preset in raw_roles.items():
        if role not in {"planner", "worker", "reviewer"}:
            raise ProjectRenderError(f"role_presets has unsupported role: {role}")
        if not isinstance(preset, dict):
            raise ProjectRenderError(f"role_presets.{role} must be a table")
        _exact_keys(
            preset,
            required={"model", "behavior", "tool_mode"},
            subject=f"role_presets.{role}",
        )
        model = preset["model"]
        behavior = preset["behavior"]
        tool_mode = preset["tool_mode"]
        if model not in {"Sol", "Luna"}:
            raise ProjectRenderError(f"role_presets.{role}.model must be Sol or Luna")
        if behavior not in {"high", "xhigh"}:
            raise ProjectRenderError(f"role_presets.{role}.behavior must be high or xhigh")
        if tool_mode not in {"read-only", "write"}:
            raise ProjectRenderError(f"role_presets.{role}.tool_mode must be read-only or write")
        role_presets.append((role, model, behavior, tool_mode))

    if home_repo not in seen:
        raise ProjectRenderError("home_repo must also appear exactly once in members")
    project = ProjectBinding(
        project_path=project_path,
        workspace_root=workspace,
        project_id=project_id,
        display_name=display_name,
        home_repo=home_repo,
        members=tuple(members),
        role_presets=tuple(role_presets),
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


def _marker_counts(content: bytes, start: bytes, end: bytes) -> tuple[int, int]:
    return content.count(start), content.count(end)


def _marker_span(
    content: bytes, start: bytes, end: bytes, *, label: str
) -> tuple[int, int]:
    starts, ends = _marker_counts(content, start, end)
    if starts != 1 or ends != 1:
        raise ProjectRenderError(
            f"AGENTS.md has duplicate or unbalanced {label} sentinels"
        )
    span_start = content.index(start)
    try:
        span_end = content.index(end, span_start) + len(end)
    except ValueError as error:
        raise ProjectRenderError(
            f"AGENTS.md {label} sentinels are out of order"
        ) from error
    return span_start, span_end


def _with_marker(
    content: bytes, start: bytes, end: bytes, block: bytes, *, label: str
) -> bytes:
    starts, ends = _marker_counts(content, start, end)
    if starts == 0 and ends == 0:
        if not content:
            return block + b"\n"
        if content.endswith(b"\n\n"):
            separator = b""
        elif content.endswith(b"\n"):
            separator = b"\n"
        else:
            separator = b"\n\n"
        return content + separator + block + b"\n"
    span_start, span_end = _marker_span(content, start, end, label=label)
    return content[:span_start] + block + content[span_end:]


def _without_marker(content: bytes, start: bytes, end: bytes, *, label: str) -> bytes:
    starts, ends = _marker_counts(content, start, end)
    if starts == 0 and ends == 0:
        return content
    span_start, span_end = _marker_span(content, start, end, label=label)
    return content[:span_start] + content[span_end:]


def _pointer_counts(content: bytes) -> tuple[int, int]:
    return _marker_counts(content, POINTER_START, POINTER_END)


def _pointer_span(content: bytes) -> tuple[int, int]:
    return _marker_span(content, POINTER_START, POINTER_END, label="project pointer")


def _with_pointer(content: bytes) -> bytes:
    return _with_marker(
        content, POINTER_START, POINTER_END, POINTER_BLOCK, label="project pointer"
    )


def _without_pointer(content: bytes) -> bytes:
    return _without_marker(content, POINTER_START, POINTER_END, label="project pointer")


def _with_env_pointer(content: bytes) -> bytes:
    return _with_marker(
        content,
        ENV_POINTER_START,
        ENV_POINTER_END,
        ENV_POINTER_BLOCK,
        label="environment pointer",
    )


def _without_env_pointer(content: bytes) -> bytes:
    return _without_marker(
        content, ENV_POINTER_START, ENV_POINTER_END, label="environment pointer"
    )


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
    if member.render == "none" or member.access == "reference":
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


def _resolve_environment_record(records_dir: Path) -> Path | None:
    """Best-effort resolution; no matching record for this host is not an error."""
    try:
        return resolve_environment_record(records_dir)
    except EnvironmentResolutionError:
        return None


def expected_environment_section(record_path: Path) -> bytes:
    """Render the active environment's bounded context block plus a small,
    independently-hashed provenance header. This is deliberately a separate
    file and hash chain from `expected_render`'s project-source bundle: the
    environment record is host/session state, not a per-repo git-versioned
    source fragment, and mixing the two would make the existing project-render
    dirty-check machinery responsible for state it wasn't designed to track.
    """
    block = render_environment_context(record_path).encode("utf-8")
    digest = hashlib.sha256(record_path.read_bytes()).hexdigest()
    header = (
        "<!-- agentops-render: DO NOT HAND-EDIT\n"
        f"     environment_record: {record_path.name}\n"
        f"     environment_record_sha256: {digest}\n"
        "     tool: agentops-environment-context/v1\n"
        "-->\n"
    ).encode("utf-8")
    return header + block


def _environment_status(
    member: MemberBinding, expected: bytes | None
) -> tuple[str, str]:
    path = member.environment_path
    if expected is None:
        if path.exists():
            return "stale", "no environment record resolves for this host anymore"
        return "not-applicable", ""
    if path.is_symlink():
        return "invalid", "environment path must not be a symlink"
    if not path.exists():
        return "missing", ""
    if not path.is_file():
        return "invalid", "environment path is not a regular file"
    actual = path.read_bytes()
    header_end = actual.find(b"-->\n")
    if header_end == -1 or not actual.startswith(ENV_RENDER_PREFIX):
        return "invalid", "environment output has no valid agentops provenance header"
    header_end += len(b"-->\n")
    if ENV_HASH_RE.search(actual[:header_end]) is None:
        return "invalid", "environment output has no valid record hash"
    expected_header_end = expected.find(b"-->\n") + len(b"-->\n")
    if actual[:header_end] != expected[:expected_header_end]:
        return "stale", "active environment record changed since the last render"
    if actual[header_end:] != expected[expected_header_end:]:
        return (
            "hand-edited",
            "environment body differs while its source hash is current",
        )
    return "in-sync", ""


def _env_pointer_status(member: MemberBinding, *, applicable: bool) -> str:
    content = _read_regular_or_empty(member.agents_path)
    starts, ends = _marker_counts(content, ENV_POINTER_START, ENV_POINTER_END)
    if not applicable:
        if starts == 0 and ends == 0:
            return "not-applicable"
        try:
            return (
                "unexpected"
                if _without_env_pointer(content) != content
                else "not-applicable"
            )
        except ProjectRenderError:
            return "invalid"
    try:
        expected = _with_env_pointer(content)
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
        return ("not-applicable", "") if member.render == "none" or member.access == "reference" else ("missing", "")
    if not path.is_file():
        return "invalid", "generated path is not a regular file"
    actual = path.read_bytes()
    if member.render == "none" or member.access == "reference":
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


def inspect_project(
    project: ProjectBinding,
    *,
    environment_records_dir: Path = ENVIRONMENT_RECORDS_DIR,
) -> list[MemberStatus]:
    fragments = load_fragments(project)
    environment_record = _resolve_environment_record(environment_records_dir)
    expected_environment = (
        expected_environment_section(environment_record)
        if environment_record is not None
        else None
    )
    statuses: list[MemberStatus] = []
    for member in project.members:
        expected = (
            None
            if member.render == "none"
            else expected_render(project, member, fragments)
        )
        generated, detail = _generated_status(member, expected)
        if member.access == "reference":
            # Reference members are observable inputs only.  Their authored
            # files are inspected, but renderer-owned environment output and
            # pointers are never expected or changed.
            environment, environment_detail = "not-applicable", ""
        else:
            environment, environment_detail = _environment_status(member, expected_environment)
        documents: list[tuple[str, str]] = []
        for path in member.required_documents:
            candidate = member.repo_root / path
            if path == ".agents/project.generated.md":
                state = generated
            elif path == ".agents/environment.generated.md":
                state = environment
            elif not candidate.exists():
                state = "missing"
            elif candidate.is_symlink() or not candidate.is_file():
                state = "invalid"
            else:
                state = "in-sync"
            documents.append((path, state))
        for path in member.optional_documents:
            candidate = member.repo_root / path
            documents.append((path, "absent" if not candidate.exists() else "present"))
        for path in member.forbidden_documents:
            candidate = member.repo_root / path
            if not candidate.exists():
                state = "not-applicable"
            elif candidate.is_symlink() or not candidate.is_file():
                state = "invalid"
            else:
                state = "unexpected"
            documents.append((path, state))
        statuses.append(
            MemberStatus(
                repo_id=member.repo_id,
                render=member.render,
                generated=generated,
                pointer=_pointer_status(member),
                detail=detail,
                environment=environment,
                environment_pointer=_env_pointer_status(
                    member,
                    applicable=(expected_environment is not None and member.access != "reference"),
                ),
                environment_detail=environment_detail,
                documents=tuple(documents),
            )
        )
    return statuses


def _git_dirty(repo_root: Path, pathspecs: set[str]) -> str:
    git_environment = os.environ.copy()
    git_environment["GIT_OPTIONAL_LOCKS"] = "0"
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
        env=git_environment,
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
        if member.access == "reference":
            continue
        pathspecs.setdefault(member.repo_root, set()).update(
            {
                "AGENTS.md",
                ".agents/project.generated.md",
                ".agents/environment.generated.md",
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


def document_contract_violations(
    project: ProjectBinding,
    statuses: list[MemberStatus] | None = None,
    *,
    check_renderer_state: bool = False,
) -> list[str]:
    """Return hard document-contract violations with ownership-aware wording."""
    violations: list[str] = []
    for member in project.members:
        # Authored documents are never synthesized by the renderer.  A regular
        # pre-existing file is required before any generated output is touched.
        for path in member.required_documents:
            if path in RENDER_MANAGED_DOCUMENTS:
                continue
            candidate = member.repo_root / path
            if candidate.is_symlink() or not candidate.is_file():
                violations.append(
                    f"{member.repo_id}/{path}: missing required authored document"
                )
        for path in member.forbidden_documents:
            candidate = member.repo_root / path
            if candidate.exists():
                if (
                    path == ".agents/project.generated.md"
                    and member.render == "none"
                    and member.access != "reference"
                    and candidate.is_file()
                    and not candidate.is_symlink()
                    and candidate.read_bytes().startswith(RENDER_PREFIX)
                ):
                    # A writable render:none transition may remove a stale
                    # renderer-owned output; all other forbidden files fail
                    # closed and reference members are never mutated.
                    continue
                violations.append(
                    f"{member.repo_id}/{path}: forbidden document is present"
                )
            elif candidate.is_symlink():
                violations.append(f"{member.repo_id}/{path}: forbidden document is a symlink")
    if statuses is not None and check_renderer_state:
        members_by_id = {member.repo_id: member for member in project.members}
        for status in statuses:
            member = members_by_id[status.repo_id]
            for path, state in status.documents:
                if path in RENDER_MANAGED_DOCUMENTS and path in member.required_documents:
                    if state not in {"in-sync", "not-applicable"}:
                        violations.append(
                            f"{status.repo_id}/{path}: renderer-managed output is {state}"
                        )
            if member.render == "none" or member.access == "reference":
                if status.pointer not in {"not-applicable", "in-sync"}:
                    violations.append(
                        f"{status.repo_id}/AGENTS.md: forbidden project pointer is {status.pointer}"
                    )
            elif status.pointer not in {"in-sync"}:
                violations.append(
                    f"{status.repo_id}/AGENTS.md: renderer-managed project pointer is {status.pointer}"
                )
    return violations


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


def apply_project(
    project: ProjectBinding,
    *,
    environment_records_dir: Path = ENVIRONMENT_RECORDS_DIR,
) -> list[MemberStatus]:
    """Apply deterministic renders after refusing dirty inputs and managed paths."""
    before = inspect_project(project, environment_records_dir=environment_records_dir)
    contract_violations = document_contract_violations(project, before)
    if contract_violations:
        raise ProjectRenderError(
            "refusing --apply because document contracts are violated:\n"
            + "\n".join(f"- {item}" for item in contract_violations)
        )
    if not any(status.needs_sync for status in before):
        return before
    dirty = _dirty_render_paths(project)
    if dirty:
        raise DirtyProjectError(
            "refusing --apply because project render inputs or managed outputs are dirty:\n"
            f"{dirty}"
        )

    fragments = load_fragments(project)
    environment_record = _resolve_environment_record(environment_records_dir)
    expected_environment = (
        expected_environment_section(environment_record)
        if environment_record is not None
        else None
    )
    operations: list[tuple[MemberBinding, ExpectedRender | None, bytes, bytes]] = []
    renderable_members = tuple(member for member in project.members if member.access != "reference")
    for member in renderable_members:
        # AGENTS.md is authored input.  The renderer may update its managed
        # pointer blocks, but it must never create an absent authored file.
        agents = _read_regular_or_empty(member.agents_path)
        if member.render == "none" or member.access == "reference":
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
            expected = None
            next_agents = _without_pointer(agents)
        else:
            expected = expected_render(project, member, fragments)
            next_agents = _with_pointer(agents)

        next_agents = (
            _with_env_pointer(next_agents)
            if expected_environment is not None
            else _without_env_pointer(next_agents)
        )
        operations.append((member, expected, agents, next_agents))

    for member, expected, agents, next_agents in operations:
        if expected is None:
            if member.generated_path.exists():
                member.generated_path.unlink()
        else:
            _atomic_write(member.generated_path, expected.content)
        if expected_environment is not None:
            _atomic_write(member.environment_path, expected_environment)
        elif member.environment_path.exists():
            current_env = _read_regular_or_empty(member.environment_path)
            if current_env.startswith(ENV_RENDER_PREFIX):
                member.environment_path.unlink()
        if next_agents != agents:
            _atomic_write(member.agents_path, next_agents)
    after = inspect_project(project, environment_records_dir=environment_records_dir)
    remaining = document_contract_violations(project, after, check_renderer_state=True)
    for status in after:
        for path, state in status.documents:
            if path in RENDER_MANAGED_DOCUMENTS and state not in {"in-sync", "not-applicable"}:
                remaining.append(f"{status.repo_id}/{path}: renderer-managed output is {state}")
    if remaining:
        raise ProjectRenderError(
            "render completed with document contract violations:\n"
            + "\n".join(f"- {item}" for item in remaining)
        )
    return after


def _print_statuses(statuses: list[MemberStatus]) -> None:
    for status in statuses:
        print(
            f"{status.repo_id} ({status.render}): "
            f"generated={status.generated}; pointer={status.pointer}; "
            f"environment={status.environment}; "
            f"environment_pointer={status.environment_pointer}"
        )
        if status.detail:
            print(f"  {status.detail}")
        if status.environment_detail:
            print(f"  {status.environment_detail}")
        for path, state in status.documents:
            print(f"  document {path}: {state}")


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
    check.add_argument(
        "--environment-records-dir",
        type=Path,
        default=ENVIRONMENT_RECORDS_DIR,
        help="directory to search for environment-record/v1 files (default: templates/dispatch/environment-record)",
    )
    args = parser.parse_args(argv)

    try:
        project = load_project(args.project, workspace_root=args.workspace_root)
        statuses = inspect_project(
            project, environment_records_dir=args.environment_records_dir
        )
        if args.apply:
            _print_statuses(statuses)
            statuses = apply_project(
                project, environment_records_dir=args.environment_records_dir
            )
            print("after apply:")
        _print_statuses(statuses)
    except ProjectRenderError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1 if any(status.needs_sync for status in statuses) else 0


if __name__ == "__main__":
    raise SystemExit(main())
