#!/usr/bin/env python3
"""Read-only preflight for canonical and materialized project workspaces."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent))
import render_project  # noqa: E402


class PreflightError(ValueError):
    """Raised when requested evidence cannot be inspected safely."""


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "git failed"
        raise PreflightError(f"{repo}: git {' '.join(arguments)}: {detail}")
    return result.stdout.strip()


def _common_git_dir(repo: Path) -> Path:
    value = Path(_git(repo, "rev-parse", "--git-common-dir"))
    return (value if value.is_absolute() else repo / value).resolve()


def _check(checks: list[dict[str, object]], check_id: str, passed: bool, detail: str, **evidence: object) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "pass" if passed else "fail",
            "detail": detail,
            "evidence": evidence,
        }
    )


def _load_json(path: Path, subject: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PreflightError(f"cannot read {subject} {path}: {error}") from error
    if not isinstance(value, dict):
        raise PreflightError(f"{subject} must contain a JSON object: {path}")
    return value


def inspect(
    project: render_project.ProjectBinding,
    *,
    folder: Path | None = None,
    projects_root: Path | None = None,
    exclusion_policy: Path | None = None,
) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    binding_digest = hashlib.sha256(project.project_path.read_bytes()).hexdigest()
    source_commit = _git(project.home_root, "rev-parse", "HEAD")
    source_paths = [project.project_path]
    if project.sources_root.is_dir():
        source_paths.extend(sorted(project.sources_root.glob("*.md")))
    relative_sources = [str(path.relative_to(project.home_root)) for path in source_paths]
    dirty = _git(
        project.home_root,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *relative_sources,
    )
    _check(
        checks,
        "canonical-sources-clean",
        not dirty,
        "canonical binding and guidance sources are clean" if not dirty else "canonical binding or guidance sources are dirty",
        paths=relative_sources,
        porcelain=dirty,
    )
    _check(
        checks,
        "canonical-provenance",
        True,
        "canonical binding provenance recorded",
        source_binding_commit=source_commit,
        source_binding_sha256=binding_digest,
    )

    if folder is not None:
        folder = folder.resolve()
        marker = _load_json(folder / ".agentops-project-folder.json", "marker")
        context = _load_json(folder / "project.context.json", "context")
        identity_fields = (
            "project_id",
            "instance_id",
            "mode",
            "source_binding_commit",
            "source_binding_sha256",
            "context_bundle_sha256",
        )
        consistent = all(marker.get(field) == context.get(field) for field in identity_fields)
        context_sources = context.get("context_sources", [])
        recomputed_bundle = (
            hashlib.sha256(
                json.dumps(context_sources, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if isinstance(context_sources, list)
            else None
        )
        source_records_valid = isinstance(context_sources, list)
        source_failures: list[str] = []
        if source_records_valid:
            for record in context_sources:
                if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                    source_records_valid = False
                    source_failures.append("malformed source record")
                    continue
                source_path = Path(record["path"])
                source_path = source_path if source_path.is_absolute() else folder / source_path
                if source_path.is_symlink() or not source_path.is_file():
                    source_records_valid = False
                    source_failures.append(f"missing or non-regular source: {source_path}")
                    continue
                actual_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
                if actual_digest != record.get("sha256"):
                    source_records_valid = False
                    source_failures.append(f"digest mismatch: {source_path}")
        consistent = (
            consistent
            and source_records_valid
            and recomputed_bundle == context.get("context_bundle_sha256")
        )
        current = (
            marker.get("project_id") == project.project_id
            and marker.get("source_binding_commit") == source_commit
            and marker.get("source_binding_sha256") == binding_digest
        )
        _check(
            checks,
            "materialization-provenance",
            consistent and current,
            "marker and context provenance match canonical sources" if consistent and current else "marker/context provenance is inconsistent or stale",
            marker={field: marker.get(field) for field in identity_fields},
            context={field: context.get(field) for field in identity_fields},
            recomputed_context_bundle_sha256=recomputed_bundle,
            context_source_failures=source_failures,
        )

        member_context = {
            item.get("repo_id"): item
            for item in context.get("members", [])
            if isinstance(item, dict) and isinstance(item.get("repo_id"), str)
        }
        mode = marker.get("mode")
        for member in project.members:
            worktree = folder / "members" / member.repo_id
            registered = worktree.is_dir()
            same_common_dir = False
            if registered:
                try:
                    same_common_dir = _common_git_dir(worktree) == _common_git_dir(member.repo_root)
                    registered_paths = _git(member.repo_root, "worktree", "list", "--porcelain")
                    registered = f"worktree {worktree}" in registered_paths
                except PreflightError:
                    same_common_dir = False
            _check(
                checks,
                f"member-worktree:{member.repo_id}",
                registered and same_common_dir,
                "member is a registered worktree of its canonical repository" if registered and same_common_dir else "member worktree registration or Git common directory does not match",
                worktree=str(worktree),
                canonical_repo=str(member.repo_root),
            )
            resolved = member_context.get(member.repo_id, {})
            metadata_matches = (
                resolved.get("relationship") == member.relationship
                and resolved.get("access") == member.access
            )
            expected_effective_mode = (
                "shared-read"
                if mode == "shared-read" or member.access == "reference"
                else "exclusive-write"
            )
            effective_mode_ok = resolved.get("effective_mode") == expected_effective_mode
            _check(
                checks,
                f"member-policy:{member.repo_id}",
                metadata_matches and effective_mode_ok,
                "member role, access, and effective mode match" if metadata_matches and effective_mode_ok else "member role/access metadata or effective mode conflicts",
                relationship=member.relationship,
                access=member.access,
                instance_mode=mode,
                expected_effective_mode=expected_effective_mode,
                resolved_effective_mode=resolved.get("effective_mode"),
                resolved_relationship=resolved.get("relationship"),
                resolved_access=resolved.get("access"),
            )

        root_env = [name for name in (".envrc", ".direnv") if (folder / name).exists()]
        _check(
            checks,
            "root-direnv-aggregation",
            not root_env,
            "materialization root has no direnv configuration" if not root_env else "materialization root contains direnv configuration",
            found=root_env,
        )

    if exclusion_policy is not None:
        if projects_root is None:
            raise PreflightError("--exclusion-policy requires --projects-root")
        projects_root = projects_root.resolve()
        try:
            lines = [line.strip() for line in exclusion_policy.read_text(encoding="utf-8").splitlines()]
        except (OSError, UnicodeError) as error:
            raise PreflightError(f"cannot read exclusion policy {exclusion_policy}: {error}") from error
        candidates = {str(projects_root), f"{projects_root}/**", projects_root.name, f"{projects_root.name}/**"}
        matches = sorted(set(lines) & candidates)
        _check(
            checks,
            "projects-root-exclusion-policy",
            bool(matches),
            "requested projects root is named in the supplied exclusion policy" if matches else "supplied policy does not explicitly name the requested projects root",
            projects_root=str(projects_root),
            policy=str(exclusion_policy.resolve()),
            matching_entries=matches,
            limitation="This inspects only the supplied policy file; it does not validate backup, synchronization, IDE, or harness behavior.",
        )

    passed = all(item["status"] == "pass" for item in checks)
    return {
        "schema_version": 1,
        "project_id": project.project_id,
        "project": str(project.project_path),
        "folder": str(folder) if folder is not None else None,
        "ok": passed,
        "checks": checks,
        "limitations": [
            "No external harness behavior is validated.",
            "Backup, synchronization, and indexing behavior are not validated unless represented by an explicitly supplied policy file, and even then only its text is inspected.",
        ],
    }


def _print_text(report: dict[str, object]) -> None:
    print(f"project workspace preflight: {'PASS' if report['ok'] else 'FAIL'}")
    for item in report["checks"]:
        print(f"{item['status'].upper():4} {item['id']}: {item['detail']}")
    for limitation in report["limitations"]:
        print(f"NOTE {limitation}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--projects-root", type=Path)
    parser.add_argument("--exclusion-policy", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        project = render_project.load_project(args.project, workspace_root=args.workspace_root)
        report = inspect(
            project,
            folder=args.folder,
            projects_root=args.projects_root,
            exclusion_policy=args.exclusion_policy,
        )
    except (PreflightError, render_project.ProjectRenderError) as error:
        if args.json:
            print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_text(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
