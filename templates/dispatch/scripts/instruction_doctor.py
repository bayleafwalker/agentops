#!/usr/bin/env python3
"""Read-only instruction provenance and hygiene diagnostics.

The doctor deliberately does not compose, rank, or otherwise replace a
harness's instruction precedence.  It only records the native root-to-CWD
source walk and compares that observation with a v2 dispatch manifest's
source catalog.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


REF_RE = re.compile(r"\b(?:wi|sprint|sha|pr):[A-Za-z0-9._/-]+\b")
RULE_RE = re.compile(
    r"<!--\s*agentops:\s*rule\s+rule_id=(?P<rule_id>[A-Za-z0-9._-]+)\s+scope=(?P<scope>[^\s]+)(?:\s+kind=(?P<kind>mechanical|advisory))?\s*-->"
)
HOOK_RE = re.compile(r"<!--\s*agentops:\s*hook\s+(?P<hook>[A-Za-z0-9._:-]+)\s*-->")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
HANDLINGS = ("none", "degraded", "repair-only", "fatal")


class DoctorError(ValueError):
    """A malformed contract, which is a fatal diagnostic finding."""


def _source_kind(path: Path) -> str:
    if path.name in {"AGENTS.md", "CLAUDE.md"}:
        return path.name
    if ".agents" in path.parts:
        return "overlay"
    if "generated" in path.name:
        return "generated"
    return "other"


def discover_native_sources(root: Path, cwd: Path | None = None) -> list[Path]:
    """Return native instruction files in native root-to-CWD order.

    Claude's ``CLAUDE.md`` and Codex's ``AGENTS.md`` are intentionally kept as
    separate sources.  The doctor reports both; it never decides which
    provider wins.  A nested CWD outside ``root`` is rejected rather than
    silently broadening the scan.
    """
    root = root.resolve()
    cwd = (cwd or Path.cwd()).resolve()
    try:
        relative = cwd.relative_to(root)
    except ValueError as exc:
        raise DoctorError("CWD must be inside --root") from exc
    directories = [root]
    current = root
    for part in relative.parts:
        current = current / part
        directories.append(current)
    found: list[Path] = []
    for directory in directories:
        for name in ("AGENTS.md", "CLAUDE.md"):
            path = directory / name
            if path.is_file() and not path.is_symlink():
                found.append(path)
    return found


def _git_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else None


def _git_source_digest(root: Path, revision: str, path: str) -> str | None:
    """Return the digest of ``path`` at an immutable Git revision."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "show", f"{revision}:{path}"],
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return hashlib.sha256(result.stdout).hexdigest() if result.returncode == 0 else None


def inspect_source(path: Path, root: Path, source_rev: str | None = None) -> dict[str, Any]:
    """Collect bounded mechanical facts about one instruction source."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    rules = [
        {
            "rule_id": match.group("rule_id"),
            "scope": match.group("scope"),
            "kind": match.group("kind") or "mechanical",
        }
        for match in RULE_RE.finditer(text)
    ]
    hooks = sorted({match.group("hook") for match in HOOK_RE.finditer(text)})
    return {
        "path": relative,
        "kind": _source_kind(path),
        "digest": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "source_rev": f"git:{source_rev}" if source_rev else None,
        "refs": sorted(set(REF_RE.findall(text))),
        "rules": rules,
        "hooks": hooks,
        "line_count": len(text.splitlines()),
    }


def _manifest_path(root: Path) -> Path | None:
    paths = sorted(path for path in root.iterdir() if path.is_file() and path.name.endswith(".dispatch.json"))
    return paths[0] if len(paths) == 1 else None


def _finding(code: str, handling: str, message: str, *, path: str | None = None) -> dict[str, Any]:
    return {"code": code, "handling": handling, "message": message, **({"path": path} if path else {})}


def _validate_catalog(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") not in {1, 2}:
        raise DoctorError("schema_version must be 1 or 2")
    if manifest.get("schema_version") == 1:
        return [_finding("instruction-set-unbound", "degraded", "manifest is v1 and has no instruction_set source catalog")]
    instruction_set = manifest.get("instruction_set")
    if not isinstance(instruction_set, dict) or instruction_set.get("discovery") != "native":
        raise DoctorError("instruction_set must declare native discovery")
    sources = instruction_set.get("sources")
    if not isinstance(sources, list):
        raise DoctorError("instruction_set.sources must be an array")
    findings: list[dict[str, Any]] = []
    presets = instruction_set.get("role_presets", {})
    if not isinstance(presets, dict) or any(
        role not in {"planner", "worker", "reviewer"} for role in presets
    ):
        raise DoctorError("instruction_set.role_presets has unsupported roles")
    for role, preset in presets.items():
        if not isinstance(preset, dict) or set(preset) != {"model", "behavior", "tool_mode"}:
            raise DoctorError(f"role preset {role} must contain only model, behavior, and tool_mode")
        if preset["model"] not in {"Sol", "Luna"} or preset["behavior"] not in {"high", "xhigh"} or preset["tool_mode"] not in {"read-only", "write"}:
            raise DoctorError(f"role preset {role} has invalid values")
    ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise DoctorError("each instruction source must be an object")
        source_id = source.get("id")
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", source_id) or source_id in ids:
            raise DoctorError("instruction source ids must be unique identifiers")
        ids.add(source_id)
        if not isinstance(source.get("path"), str) or Path(source["path"]).is_absolute() or ".." in Path(source["path"]).parts:
            raise DoctorError(f"instruction source {source_id} path must be relative")
        if not isinstance(source.get("digest"), str) or not SHA_RE.fullmatch(source["digest"]):
            raise DoctorError(f"instruction source {source_id} digest must be sha256")
        if not isinstance(source.get("source_rev"), str) or not source["source_rev"]:
            raise DoctorError(f"instruction source {source_id} source_rev is required")
    return findings



# Match on the load-bearing FACT, not a heading: a repo may title the section
# however it likes, but it must tell a session how to escape the sandbox.
FORGE_MARKERS = ("dangerouslyDisableSandbox", "sandbox escalation")


def _check_forge_contract(root: Path) -> list[dict[str, Any]]:
    """Forge/sandbox guidance must reach a session, and gating must be declared.

    Both are propagation checks rather than style checks. `AGENTS.md` is NOT
    auto-loaded by Claude Code unless `@`-imported, so guidance living only there
    reaches a session by luck. And a repo with no gates.json is asserting that
    everything in it is routine -- which is the correct default, but it should be
    an explicit statement rather than an accident.
    """
    findings: list[dict[str, Any]] = []
    claude_md = root / "CLAUDE.md"
    if not claude_md.is_file():
        findings.append(_finding(
            "forge-contract-missing",
            "degraded",
            "no CLAUDE.md: the auto-loaded surface is absent, so forge/sandbox guidance cannot reach a session",
        ))
    else:
        try:
            body = claude_md.read_text(encoding="utf-8")
            if not any(marker in body for marker in FORGE_MARKERS):
                findings.append(_finding(
                    "forge-contract-missing",
                    "degraded",
                    "CLAUDE.md lacks the forge/sandbox block; sandboxed network calls return exit 0 with empty output and get read as fact",
                    path="CLAUDE.md",
                ))
        except (OSError, UnicodeError) as exc:
            findings.append(_finding("forge-contract-unreadable", "degraded", str(exc), path="CLAUDE.md"))

    gates = root / ".claude" / "gates.json"
    if not gates.is_file():
        findings.append(_finding(
            "gates-undeclared",
            "degraded",
            "no .claude/gates.json: gating is opt-in and absence means routine, but that should be stated rather than assumed",
        ))
    else:
        try:
            data = json.loads(gates.read_text(encoding="utf-8"))
            if data.get("default") != "routine":
                findings.append(_finding(
                    "gates-default-not-routine",
                    "repair-only",
                    "gates.json default must be 'routine' -- standard workflow must not prompt the operator",
                    path=".claude/gates.json",
                ))
            valid = {"operator-approved", "operator-actioned"}
            for entry in data.get("gated") or []:
                if not isinstance(entry, dict) or entry.get("tier") not in valid:
                    findings.append(_finding(
                        "gates-tier-invalid",
                        "repair-only",
                        f"each gated entry needs a tier in {sorted(valid)}",
                        path=".claude/gates.json",
                    ))
                    break
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            findings.append(_finding("gates-invalid", "repair-only", str(exc), path=".claude/gates.json"))
    return findings


def inspect(root: Path, cwd: Path | None = None) -> dict[str, Any]:
    """Produce a deterministic, JSON-safe instruction doctor report."""
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    manifest_path = _manifest_path(root)
    manifest: dict[str, Any] | None = None
    if manifest_path is None:
        findings.append(_finding("instruction-set-unbound", "repair-only", "exactly one dispatch manifest is required for a managed instruction set"))
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            findings.extend(_validate_catalog(manifest))
        except (OSError, UnicodeError, json.JSONDecodeError, DoctorError) as exc:
            findings.append(_finding("manifest-invalid", "fatal", str(exc), path=manifest_path.name))

    findings.extend(_check_forge_contract(root))

    discovered = discover_native_sources(root, cwd)
    revision = _git_revision(root)
    observed = [inspect_source(path, root, revision) for path in discovered]
    catalog = ((manifest or {}).get("instruction_set") or {}).get("sources", []) if manifest else []
    by_path = {item["path"]: item for item in observed}
    instruction_set = ((manifest or {}).get("instruction_set") or {}) if manifest else {}
    catalog_paths = {
        source.get("path")
        for source in catalog if isinstance(source, dict) and isinstance(source.get("path"), str)
    }
    for actual in observed:
        if actual["path"] not in catalog_paths and manifest and manifest.get("schema_version") == 2:
            findings.append(_finding(
                "source-not-catalogued",
                "degraded",
                "native instruction source is effective but absent from the v2 catalog",
                path=actual["path"],
            ))
    # A catalog path is data, not permission to inspect outside the repository.
    for source in catalog if isinstance(catalog, list) else []:
        if not isinstance(source, dict) or not isinstance(source.get("path"), str):
            continue
        relative_path = Path(source["path"])
        candidate = root / relative_path
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            findings.append(_finding("source-path-escape", "fatal", "catalogued source escapes --root", path=source["path"]))
        if candidate.is_symlink():
            findings.append(_finding("source-symlink", "fatal", "catalogued source must not be a symlink", path=source["path"]))
    for source in catalog if isinstance(catalog, list) else []:
        if not isinstance(source, dict):
            continue
        path = source.get("path")
        if not isinstance(path, str):
            continue
        actual = by_path.get(path)
        if actual is None:
            findings.append(_finding("source-not-discovered", "degraded", "catalogued source was not found by native root-to-CWD discovery", path=path))
            continue
        if actual["digest"] != source.get("digest"):
            findings.append(_finding("source-digest-mismatch", "degraded", "source digest differs from catalog", path=path))
        expected_rev = source.get("source_rev")
        if expected_rev and expected_rev.startswith("git:"):
            pinned_digest = _git_source_digest(root, expected_rev.removeprefix("git:"), path)
            if pinned_digest != source.get("digest"):
                findings.append(_finding(
                    "source-revision-mismatch",
                    "degraded",
                    "source revision does not contain the catalogued source bytes",
                    path=path,
                ))
        if "line_budget" in source and actual["line_count"] > source["line_budget"]:
            findings.append({**_finding("line-budget-exceeded", "none", f"source has {actual['line_count']} lines; budget is {source['line_budget']}", path=path), "advisory": True})
        for field in ("refs", "hooks", "rules"):
            if field in source and source[field] != actual[field]:
                findings.append(_finding(f"source-{field}-mismatch", "degraded", f"source {field} differ from catalog", path=path))

    # Mechanical duplicate checks operate on declared rule identity and scope;
    # prose that merely sounds contradictory is deliberately not classified.
    scoped_rules: dict[tuple[str, str], dict[str, Any]] = {}
    for item in observed:
        for rule in item["rules"]:
            key = (rule["rule_id"], rule["scope"])
            prior = scoped_rules.get(key)
            if prior is not None and prior != rule:
                findings.append(_finding("conflicting-scoped-rule", "degraded", "duplicate scoped rule_id has conflicting mechanical definitions", path=item["path"]))
            scoped_rules[key] = rule

    adapters = instruction_set.get("provider_adapters", []) if isinstance(instruction_set, dict) else []
    providers: dict[str, str] = {}
    if isinstance(adapters, list):
        for adapter in adapters:
            if not isinstance(adapter, dict):
                continue
            provider = adapter.get("provider")
            if not isinstance(provider, str):
                continue
            if provider in providers:
                findings.append(_finding("duplicate-provider-adapter", "degraded", "provider has more than one instruction adapter", path=str(adapter.get("path", provider))))
            providers[provider] = str(adapter.get("path", ""))

    skill_lock_ref = instruction_set.get("skill_lock_ref") if isinstance(instruction_set, dict) else None
    locked_skills: dict[str, str] = {}
    if skill_lock_ref is not None:
        if not isinstance(skill_lock_ref, dict) or set(skill_lock_ref) != {"path", "digest", "mandatory"}:
            findings.append(_finding("skill-lock-ref-invalid", "fatal", "skill_lock_ref shape is invalid"))
        else:
            lock_path = Path(str(skill_lock_ref["path"]))
            candidate = root / lock_path
            try:
                candidate.resolve().relative_to(root)
            except ValueError:
                findings.append(_finding("skill-lock-path-escape", "fatal", "skill lock escapes --root", path=str(lock_path)))
            if not candidate.is_file():
                handling_level = "repair-only" if skill_lock_ref["mandatory"] else "degraded"
                findings.append(_finding("skill-lock-missing", handling_level, "referenced skill lock is missing", path=str(lock_path)))
            elif hashlib.sha256(candidate.read_bytes()).hexdigest() != skill_lock_ref["digest"]:
                findings.append(_finding("skill-lock-digest-mismatch", "fatal", "referenced skill lock was tampered", path=str(lock_path)))
            else:
                try:
                    lock_value = json.loads(candidate.read_text(encoding="utf-8"))
                    locked_skills = {item["id"]: item["digest"] for item in lock_value.get("selected", []) if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("digest"), str)}
                except (OSError, UnicodeError, json.JSONDecodeError):
                    findings.append(_finding("skill-lock-invalid", "fatal", "referenced skill lock is invalid", path=str(lock_path)))

    broken_refs: list[dict[str, str]] = []
    for source in catalog if isinstance(catalog, list) else []:
        if not isinstance(source, dict):
            continue
        actual = by_path.get(source.get("path"))
        if actual is None:
            continue
        for ref in source.get("refs", []) if isinstance(source.get("refs", []), list) else []:
            if ref not in actual["refs"]:
                broken_refs.append({"path": source["path"], "ref": ref})
    if broken_refs:
        findings.append(_finding("broken-reference", "degraded", "catalogued instruction reference was not observed", path=broken_refs[0]["path"]))

    rule_ids = sorted({rule["rule_id"] for item in observed for rule in item["rules"]})
    hook_sources = {
        hook: item["path"]
        for item in observed
        for hook in item["hooks"]
    }
    skill_digests = locked_skills or (instruction_set.get("skill_lock", {}) if isinstance(instruction_set, dict) else {})
    if isinstance(skill_digests, list):
        skill_digests = {item.get("id"): item.get("digest") for item in skill_digests if isinstance(item, dict) and item.get("id")}
    elif not isinstance(skill_digests, dict):
        skill_digests = {}

    fatal = any(item["handling"] == "fatal" for item in findings)
    if fatal:
        status = "degraded"
    elif manifest is None:
        status = "unbound"
    elif not manifest.get("instruction_set"):
        # v1 remains dispatch-compatible, but its instruction binding is degraded.
        status = "degraded"
    else:
        blocking = [item for item in findings if item.get("handling") != "none"]
        status = "degraded" if blocking else "validated"
    handling = "fatal" if fatal else ("degraded" if any(item["handling"] == "degraded" for item in findings) else ("repair-only" if any(item["handling"] == "repair-only" for item in findings) else "none"))
    binding_status = status
    return {
        "binding_status": binding_status,
        "status": status,
        "handling": handling,
        "managed_eligible": binding_status == "validated" and handling == "none",
        "root": str(root),
        "cwd": str((cwd or Path.cwd()).resolve()),
        "manifest": str(manifest_path) if manifest_path else None,
        "discovery": "native",
        "sources": observed,
        "bytes": sum(item["bytes"] for item in observed),
        "effective_files": [item["path"] for item in observed],
        "rule_ids": rule_ids,
        "hook_sources": hook_sources,
        "skill_digests": skill_digests,
        "source_revisions": {item["path"]: item["source_rev"] for item in observed if item["source_rev"]},
        "broken_refs": broken_refs,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        report = inspect(args.root)
    except (OSError, UnicodeError, DoctorError) as exc:
        report = {"binding_status": "degraded", "status": "degraded", "handling": "fatal", "managed_eligible": False, "findings": [_finding("doctor-fatal", "fatal", str(exc))]}
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"instruction doctor: {report['status']} ({report['handling']})")
        for item in report["findings"]:
            print(f"{item['handling']}: {item['code']}: {item['message']}")
    return 0 if report["status"] == "validated" and report["handling"] == "none" else 1


if __name__ == "__main__":
    raise SystemExit(main())
