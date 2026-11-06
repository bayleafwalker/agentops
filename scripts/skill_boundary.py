#!/usr/bin/env python3
"""Read-only supply-chain inventory and grant comparison for one skill directory.

`inventory` records a skill's source origin and revision, raw-byte digests of
every file, frontmatter metadata, declared path dependencies and source-side
load-path links. `compare` checks a prior grant envelope against a current
inventory and refuses inheritance when bytes, metadata, origin, dependencies or
coverage changed or cannot be verified.

Both commands are source-side observations. They never observe a live provider
load, never treat frontmatter as authority and never upgrade an inventory to a
qualification: unknown coverage stays unknown (W41-R4, AO-K04).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

INVENTORY_SCHEMA = "agentops-skill-boundary-inventory/v1"
GRANT_SCHEMA = "agentops-skill-boundary-grant/v1"
COMPARISON_SCHEMA = "agentops-skill-boundary-comparison/v1"
INVENTORY_STATUS = "source-observed-not-qualified"
COMPARISON_STATUS = "source-comparison-not-qualified"

# Frontmatter keys that cannot carry execution authority on any known harness.
# Every other key, including unknown ones, is treated as permission-relevant:
# a change to it is handled as a possible widening (stricter reading).
INERT_FRONTMATTER_KEYS = frozenset({"name", "description", "license", "version", "argument-hint"})

# Native load paths from the #2488 coverage design. The inventory cannot observe
# any of them; each stays "unknown" until a native observation records a load.
NATIVE_LOAD_PATHS = ("skill-tool", "native-slash", "preloaded", "codex")

# Dependency classes this tool does not discover. Recorded as unknown, never as unused.
UNDISCOVERED_DEPENDENCY_CLASSES = (
    "executables-invoked-by-instructions",
    "transitive-imports-of-referenced-scripts",
    "environment-variables-and-credentials",
    "network-and-mcp-endpoints",
)

# Repository-relative references written in skill prose, e.g. `scripts/x.py`.
_PATH_REF = re.compile(
    r"(?<![\w./-])((?:\.\./|\./)*(?:scripts|docs|templates|skills|schemas|config|_artifacts)/[A-Za-z0-9_.<>*{}$/-]+)"
)
_LINK_REF = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
_DYNAMIC = re.compile(r"[<>*{}$]")
_FRONTMATTER_KEY = re.compile(r"^([A-Za-z0-9_-]+):(?:\s+(.*)|\s*)$")


class SkillBoundaryError(ValueError):
    """The skill tree or grant is unsafe or malformed; no report is produced."""


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise SkillBoundaryError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- source


def _git(repo_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=True, check=False, timeout=20,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _source(repo_root: Path, skill_rel: str) -> dict[str, Any]:
    if _git(repo_root, "rev-parse", "--is-inside-work-tree") != "true":
        return {"origin": "unknown", "revision": "unknown", "tree_state": "unknown",
                "repository_tree_state": "unknown", "vcs": "none-observed"}
    origin = _git(repo_root, "config", "--get", "remote.origin.url") or "unknown"
    revision = _git(repo_root, "rev-parse", "HEAD") or "unknown"
    skill_status = _git(repo_root, "status", "--porcelain", "--untracked-files=all", "--", skill_rel)
    repo_status = _git(repo_root, "status", "--porcelain", "--untracked-files=all")

    def state(value: str | None) -> str:
        return "unknown" if value is None else ("clean" if value == "" else "modified")

    return {"origin": origin, "revision": revision, "tree_state": state(skill_status),
            "repository_tree_state": state(repo_status), "vcs": "git"}


# --------------------------------------------------------------------------- files


def _files(skill_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for current, dirs, names in os.walk(skill_dir, topdown=True, followlinks=False):
        here = Path(current)
        for name in list(dirs):
            _need(not (here / name).is_symlink(),
                  f"symlink refused inside skill tree: {(here / name).relative_to(skill_dir).as_posix()}")
        dirs.sort()
        for name in sorted(names):
            path = here / name
            rel = path.relative_to(skill_dir).as_posix()
            info = path.lstat()
            _need(not stat.S_ISLNK(info.st_mode), f"symlink refused inside skill tree: {rel}")
            _need(stat.S_ISREG(info.st_mode), f"non-regular file refused inside skill tree: {rel}")
            data = path.read_bytes()
            entries.append({
                "path": rel,
                "sha256": _sha256(data),
                "size": len(data),
                "executable": bool(info.st_mode & 0o111),
            })
    return sorted(entries, key=lambda e: e["path"])


def _tree_digest(files: list[dict[str, Any]]) -> str:
    lines = [f"{f['path']}\0{f['sha256']}\0{int(f['executable'])}" for f in files]
    return _sha256("\n".join(lines).encode("utf-8"))


# --------------------------------------------------------------------------- frontmatter


def _frontmatter(text: str) -> tuple[dict[str, Any], str, str]:
    """Return (frontmatter, status, body). Status is parsed | absent | unparsed."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "absent", text
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return {}, "unparsed", text
    body = "\n".join(lines[end + 1:])
    parsed: dict[str, Any] = {}
    key: str | None = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _FRONTMATTER_KEY.match(line)
        if match:
            key = match.group(1)
            if key in parsed:
                return {}, "unparsed", body
            value = (match.group(2) or "").strip()
            parsed[key] = value if value not in {"", ">", "|", ">-", "|-"} else None
            continue
        stripped = line.strip()
        if key is None or not line[:1].isspace():
            return {}, "unparsed", body
        if stripped.startswith("- "):
            current = parsed[key]
            if current is None:
                parsed[key] = [stripped[2:].strip()]
            elif isinstance(current, list):
                current.append(stripped[2:].strip())
            else:
                return {}, "unparsed", body
        elif isinstance(parsed[key], list):
            return {}, "unparsed", body
        else:
            parsed[key] = f"{parsed[key]} {stripped}".strip() if parsed[key] else stripped
    return parsed, "parsed", body


# --------------------------------------------------------------------------- dependencies


def _references(body: str) -> list[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    for match in _PATH_REF.finditer(body):
        refs.add((match.group(1).rstrip(".,;:'\"`"), "repository"))
    for match in _LINK_REF.finditer(body):
        target = match.group(1)
        if "://" in target or target.startswith("mailto:"):
            continue
        refs.add((target.rstrip(".,;:'\"`"), "skill-relative"))
    return sorted(refs)


def _dependency(ref: str, base: str, repo_root: Path, skill_dir: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {"reference": ref, "resolved_from": base, "path": None,
                             "sha256": None, "status": "unknown"}
    if _DYNAMIC.search(ref):
        entry["status"] = "dynamic"
        return entry
    anchor = repo_root if base == "repository" else skill_dir
    lexical = Path(os.path.normpath(anchor / ref))
    if Path(ref).is_absolute() or not _inside(lexical, repo_root):
        entry["status"] = "refused-path-escape"
        return entry
    entry["path"] = lexical.relative_to(repo_root).as_posix()
    probe = repo_root
    for part in lexical.relative_to(repo_root).parts:
        probe = probe / part
        if probe.is_symlink():
            entry["status"] = "refused-symlink"
            return entry
    if not lexical.exists():
        entry["status"] = "missing"
    elif lexical.is_dir():
        entry["status"] = "directory-not-digested"
    elif lexical.is_file():
        entry["sha256"] = _sha256(lexical.read_bytes())
        entry["status"] = "within-skill-tree" if _inside(lexical, skill_dir) else "observed"
    return entry


# --------------------------------------------------------------------------- load paths


def _load_path(link: str, repo_root: Path, skill_dir: Path) -> dict[str, Any]:
    path = Path(os.path.normpath(repo_root / link))
    entry: dict[str, Any] = {"path": link, "kind": "absent", "target": None,
                             "resolves_to_skill": False,
                             "observation": "source-link-only"}
    if not _inside(path, repo_root):
        entry["kind"] = "refused-path-escape"
        return entry
    if path.is_symlink():
        entry["kind"] = "symlink"
        entry["target"] = os.readlink(path)
        resolved = path.resolve()
        entry["resolves_to_skill"] = resolved == skill_dir
        if not _inside(resolved, repo_root):
            entry["kind"] = "refused-symlink-escape"
            entry["resolves_to_skill"] = False
    elif path.exists():
        entry["kind"] = "directory-copy" if path.is_dir() else "file"
        entry["resolves_to_skill"] = path.resolve() == skill_dir
    return entry


# --------------------------------------------------------------------------- inventory


def inventory(skill_dir: Path, *, repo_root: Path | None = None,
              load_paths: list[str] | None = None) -> dict[str, Any]:
    """Return a deterministic source-side inventory. Raises on unsafe trees."""
    _need(not skill_dir.is_symlink(),
          "skill directory is a symlink; inventory the canonical source and pass the link as --load-path")
    skill_dir = skill_dir.resolve()
    _need(skill_dir.is_dir(), f"skill directory not found: {skill_dir}")
    if repo_root is None:
        top = _git(skill_dir, "rev-parse", "--show-toplevel")
        _need(top is not None, "repository root unknown; pass --repo-root")
        repo_root = Path(top)
    repo_root = repo_root.resolve()
    _need(_inside(skill_dir, repo_root) and skill_dir != repo_root,
          "skill directory escapes the repository root")
    skill_md = skill_dir / "SKILL.md"
    _need(skill_md.is_file() and not skill_md.is_symlink(), "SKILL.md is required as a regular file")

    files = _files(skill_dir)
    text = skill_md.read_bytes().decode("utf-8", errors="replace")
    frontmatter, fm_status, body = _frontmatter(text)
    name = frontmatter.get("name") if isinstance(frontmatter.get("name"), str) else None
    permission_metadata = {k: v for k, v in sorted(frontmatter.items()) if k not in INERT_FRONTMATTER_KEYS}

    dependencies = [_dependency(ref, base, repo_root, skill_dir) for ref, base in _references(body)]
    dependencies.sort(key=lambda d: (d["reference"], d["resolved_from"]))

    links = set(load_paths or [])
    for prefix in (".claude/skills", ".agents/skills"):
        candidate = repo_root / prefix / skill_dir.name
        if candidate.is_symlink() or candidate.exists():
            links.add(f"{prefix}/{skill_dir.name}")
    load = [_load_path(link, repo_root, skill_dir) for link in sorted(links)]

    adapter_files = [f["path"] for f in files if f["path"].startswith("agents/")]
    skill_rel = skill_dir.relative_to(repo_root).as_posix()
    unresolved = sorted({d["status"] for d in dependencies} - {"observed", "within-skill-tree"})
    return {
        "schema_version": INVENTORY_SCHEMA,
        "qualification_status": INVENTORY_STATUS,
        "skill": {"name": name or "unknown", "directory": skill_rel},
        "source": _source(repo_root, skill_rel),
        "provenance": {"publisher": "unknown", "trust_class": "unknown",
                       "note": "not inferred from repository location; an owner record must supply it"},
        "files": files,
        "tree_sha256": _tree_digest(files),
        "frontmatter": {
            "status": fm_status,
            "values": frontmatter,
            "sha256": _sha256(_canonical(frontmatter)),
            "permission_metadata": permission_metadata,
            "permission_metadata_sha256": _sha256(_canonical(permission_metadata)),
            "authority": "none: metadata is recorded, never granted",
        },
        "adapter_files": adapter_files,
        "dependencies": dependencies,
        "dependency_coverage": {
            "declared_path_references": "complete" if not unresolved else "incomplete",
            "unresolved_statuses": unresolved,
            "undiscovered_classes": {cls: "unknown" for cls in UNDISCOVERED_DEPENDENCY_CLASSES},
        },
        "load_paths": load,
        "provider_load_coverage": {path: "unknown" for path in NATIVE_LOAD_PATHS},
        "host_execution_policy": {
            "recorded": False,
            "note": "host execution policy and its revision live in the grant, not in distribution metadata",
        },
    }


# --------------------------------------------------------------------------- comparison


def _validate_inventory(report: Any, field: str) -> dict[str, Any]:
    _need(isinstance(report, dict), f"{field} must be an object")
    _need(report.get("schema_version") == INVENTORY_SCHEMA, f"{field} has unsupported schema_version")
    _need(report.get("qualification_status") == INVENTORY_STATUS,
          f"{field}.qualification_status must remain {INVENTORY_STATUS}")
    for key in ("skill", "source", "frontmatter", "dependency_coverage"):
        _need(isinstance(report.get(key), dict), f"{field}.{key} must be an object")
    for key in ("files", "dependencies", "load_paths"):
        _need(isinstance(report.get(key), list), f"{field}.{key} must be an array")
    _need(isinstance(report.get("tree_sha256"), str), f"{field}.tree_sha256 must be a string")
    _need(_tree_digest(report["files"]) == report["tree_sha256"],
          f"{field}.tree_sha256 does not match its files")
    return report


def validate_grant(grant: Any) -> dict[str, Any]:
    _need(isinstance(grant, dict), "grant must be an object")
    _need(grant.get("schema_version") == GRANT_SCHEMA, "grant has unsupported schema_version")
    for key in ("host_policy_ref", "host_policy_revision", "granted_by"):
        _need(isinstance(grant.get(key), str) and bool(grant[key].strip()), f"grant.{key} must be a non-empty string")
    accepted = grant.get("accepted_dynamic_references", [])
    _need(isinstance(accepted, list) and all(isinstance(r, str) and _DYNAMIC.search(r) for r in accepted),
          "grant.accepted_dynamic_references must list dynamic reference strings")
    _validate_inventory(grant.get("inventory"), "grant.inventory")
    return grant


def compare(grant: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Decide whether `current` may inherit `grant`. Any doubt denies inheritance."""
    validate_grant(grant)
    _validate_inventory(current, "current")
    prior = grant["inventory"]
    reasons: list[dict[str, str]] = []

    def deny(code: str, detail: str) -> None:
        reasons.append({"code": code, "detail": detail})

    if prior["skill"].get("name") != current["skill"].get("name") or prior["skill"].get("name") == "unknown":
        deny("skill-identity", f"{prior['skill'].get('name')} -> {current['skill'].get('name')}")
    if prior["skill"].get("directory") != current["skill"].get("directory"):
        deny("skill-directory-changed", f"{prior['skill'].get('directory')} -> {current['skill'].get('directory')}")

    src = current["source"]
    if src.get("origin") == "unknown":
        deny("origin-unknown", "current source origin is unknown")
    elif src.get("origin") != prior["source"].get("origin"):
        deny("origin-changed", f"{prior['source'].get('origin')} -> {src.get('origin')}")
    if src.get("revision") == "unknown":
        deny("revision-unknown", "current source revision is unknown")
    if src.get("tree_state") != "clean":
        deny("tree-not-clean", f"skill tree state is {src.get('tree_state')}; bytes are not attested by a revision")

    prior_files = {f["path"]: f for f in prior["files"]}
    current_files = {f["path"]: f for f in current["files"]}
    for path in sorted(prior_files.keys() | current_files.keys()):
        before, after = prior_files.get(path), current_files.get(path)
        if before is None:
            deny("file-added", path)
        elif after is None:
            deny("file-removed", path)
        elif before["sha256"] != after["sha256"]:
            deny("file-bytes-changed", path)
        elif before.get("executable") != after.get("executable"):
            deny("file-mode-changed", path)
    if prior["tree_sha256"] != current["tree_sha256"] and not any(
            r["code"].startswith("file-") for r in reasons):
        deny("tree-digest-mismatch", f"{prior['tree_sha256']} -> {current['tree_sha256']}")

    fm_prior, fm_now = prior["frontmatter"], current["frontmatter"]
    if fm_now.get("status") != "parsed":
        deny("frontmatter-unverified", f"frontmatter status is {fm_now.get('status')}")
    prior_perm = fm_prior.get("permission_metadata") or {}
    now_perm = fm_now.get("permission_metadata") or {}
    for key in sorted(prior_perm.keys() | now_perm.keys()):
        if key not in prior_perm:
            deny("permission-metadata-added", key)
        elif key not in now_perm:
            deny("permission-metadata-removed", key)
        elif prior_perm[key] != now_perm[key]:
            deny("permission-metadata-changed", key)

    external = sorted(d["reference"] for d in current["dependencies"] if d["status"] == "observed")
    if external and src.get("revision") != prior["source"].get("revision"):
        # Referenced scripts may import or invoke files this tool does not digest; that
        # transitive closure is unknown, so a new revision cannot carry the grant over.
        deny("revision-changed-with-external-dependencies", ", ".join(external))
    if external and src.get("repository_tree_state") != "clean":
        deny("repository-not-clean-with-external-dependencies",
             f"repository tree state is {src.get('repository_tree_state')}")

    prior_deps ={(d["reference"], d["resolved_from"]): d for d in prior["dependencies"]}
    accepted_dynamic = set(grant.get("accepted_dynamic_references", []))
    for dep in current["dependencies"]:
        key = (dep["reference"], dep["resolved_from"])
        if dep["status"] == "dynamic" and dep["reference"] in accepted_dynamic and key in prior_deps:
            continue  # the grant owner, not metadata, accepted this exact runtime reference
        if dep["status"] not in {"observed", "within-skill-tree"}:
            deny(f"dependency-{dep['status']}", dep["reference"])
            continue
        before = prior_deps.get(key)
        if before is None:
            deny("dependency-added", dep["reference"])
        elif before.get("sha256") != dep["sha256"] or before.get("status") != dep["status"]:
            deny("dependency-bytes-changed", dep["reference"])
    for key in sorted(prior_deps.keys() - {(d["reference"], d["resolved_from"]) for d in current["dependencies"]}):
        deny("dependency-reference-removed", key[0])

    reasons.sort(key=lambda r: (r["code"], r["detail"]))
    inherit = not reasons
    return {
        "schema_version": COMPARISON_SCHEMA,
        "qualification_status": COMPARISON_STATUS,
        "skill": current["skill"].get("name"),
        "inherit": inherit,
        "inherited_host_policy_ref": grant["host_policy_ref"] if inherit else None,
        "inherited_host_policy_revision": grant["host_policy_revision"] if inherit else None,
        "reasons": reasons,
        "authority_source": "grant host policy only; frontmatter and adapter metadata never grant authority",
        "provider_load_coverage": {path: "unknown" for path in NATIVE_LOAD_PATHS},
        "undiscovered_dependency_classes": {cls: "unknown" for cls in UNDISCOVERED_DEPENDENCY_CLASSES},
    }


# --------------------------------------------------------------------------- CLI


def _dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("inventory", help="print a source-side inventory of one skill directory")
    inv.add_argument("skill_dir", type=Path)
    inv.add_argument("--repo-root", type=Path)
    inv.add_argument("--load-path", action="append", default=[],
                     help="repository-relative link or copy the harness may load from (repeatable)")
    cmp_ = sub.add_parser("compare", help="decide whether a current inventory may inherit a prior grant")
    cmp_.add_argument("--grant", type=Path, required=True, help=f"{GRANT_SCHEMA} envelope")
    group = cmp_.add_mutually_exclusive_group(required=True)
    group.add_argument("--current", type=Path, help="current inventory JSON")
    group.add_argument("--skill-dir", type=Path, help="inventory this directory now")
    cmp_.add_argument("--repo-root", type=Path)
    cmp_.add_argument("--load-path", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.cmd == "inventory":
            sys.stdout.write(_dump(inventory(args.skill_dir, repo_root=args.repo_root,
                                             load_paths=args.load_path)))
            return 0
        grant = json.loads(args.grant.read_text(encoding="utf-8"))
        if args.current is not None:
            current = json.loads(args.current.read_text(encoding="utf-8"))
        else:
            current = inventory(args.skill_dir, repo_root=args.repo_root, load_paths=args.load_path)
        result = compare(grant, current)
    except (OSError, json.JSONDecodeError, SkillBoundaryError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    sys.stdout.write(_dump(result))
    return 0 if result["inherit"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
