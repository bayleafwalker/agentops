#!/usr/bin/env python3
"""Validate dispatch manifests against ``schemas/dispatch-manifest.schema.json``.

Every repository in this fleet carries a ``<name>.dispatch.json`` and the
agentops test suite can only reach the ones inside agentops. This is the
standalone checker the sibling repositories run for themselves: ``main(argv)``
returns an int exit code and the ``__main__`` block raises ``SystemExit`` on
it, so the tool works as a command from any checkout.

Two names are pinned surface, exercised by the oracle:

* ``resolve_template_root(manifest, manifest_path) -> Path`` -- where one
  manifest's skills directory listing is expected to live. Absent from the
  manifest, the schema's own ``default`` is used (read out of the schema file,
  not hard-coded); present and absolute, it is used verbatim; present and
  relative, it resolves against the directory holding the manifest, not the
  process CWD, so the same manifest validates the same way from any shell.
* ``validate`` -- a module-level alias for ``schema_check.validate``, kept
  substitutable so ``UnsupportedKeyword`` handling can be exercised.

Reporting. Every manifest named on the command line is checked and every
violation is printed, each naming the file it came from; the exit code reflects
'any failed', never the last file. Missing file, unparseable file, and schema
violation are distinguished by message: only a schema violation carries
``schema_check`` breadcrumbs. Beyond the schema, ``skills.selected`` is
cross-checked against the directories that exist under the resolved template
root -- the schema enum is a copy of that listing, so the directory is the
source of truth. A template root that does not exist on this machine is a
warning, not a violation: it is the normal cross-repo case, and the enum is
still enforced so the run is not silently weakened.

Digest currency. ``instruction_set.sources[].digest`` is sha256 over the raw
bytes of the source file (path relative to the manifest's directory), and
``instruction_set.skill_lock[<skill>]`` is sha256 over the raw bytes of
``<template_root>/<skill>/SKILL.md``; these are the methods the retired
``instruction_doctor.py`` and skill-lock tooling used. They are observed
digests (TS-3, product direction 2026-10-15), not a pin. A digest that no
longer matches the file is a violation, so the record cannot drift silently.
``--refresh`` rewrites stale digests in place (and each source's
``source_rev`` to the last commit that touched it, when git can say) and then
validates; ``source_rev`` is left alone when the file has uncommitted edits.
A missing source file is a violation. ``skill_lock`` is compared only when the
template root lies inside the manifest's own repository: an absolute root
elsewhere (a fleet manifest pointing at the host's agentops checkout) is
skipped with a warning, because that checkout says nothing about the copies
the repo installed. ``--digests-warn`` reports stale digests as warnings
instead of errors. CI uses it, so a refresh rides along with the next manifest
change and an AGENTS.md or skill edit never needs a protected-path pass of its
own.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema_check  # noqa: E402

validate = schema_check.validate
UnsupportedKeyword = schema_check.UnsupportedKeyword

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "dispatch-manifest.schema.json"
#: Formats asserted when checking a manifest against its schema. Passing this
#: to validate() is what makes the declared list the enforced list.
ASSERTED_SCHEMA_FORMATS = ("uuid",)
_SCHEMA_DOC = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_default_template_root() -> str:
    return _SCHEMA_DOC["properties"]["skills"]["properties"]["template_root"][
        "default"
    ]


def resolve_template_root(manifest, manifest_path):
    """Return the directory where this manifest's skills are expected to live."""
    root = None
    skills = manifest.get("skills") if isinstance(manifest, dict) else None
    if isinstance(skills, dict):
        root = skills.get("template_root")
    if root is None:
        root = _schema_default_template_root()
    candidate = Path(root)
    if not candidate.is_absolute():
        candidate = Path(manifest_path).parent / candidate
    return candidate


def _check_manifest(path, digests_warn=False):
    """Return (errors, warnings) for one manifest file."""
    path = Path(path)
    if not path.is_file():
        return [f"no such file or directory: {path}"], []

    try:
        instance = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid JSON: {exc}"], []

    errors = []
    warnings = []
    try:
        # assert_formats, not bare validate: manifest.schema.json declares
        # "format": "uuid" and this is the repository's dedicated manifest
        # schema checker, so leaving format as an annotation here would mean the
        # residual V6-I identified is closed in one validator and open in the
        # one most callers actually reach.
        violations = validate(instance, _SCHEMA_DOC, assert_formats=ASSERTED_SCHEMA_FORMATS)
    except UnsupportedKeyword as exc:
        errors.append(
            f"schema cannot be fully enforced: {exc}")
        return errors, warnings
    errors.extend(violations)

    if isinstance(instance, dict):
        skills = instance.get("skills")
        if isinstance(skills, dict) and isinstance(skills.get("selected"), list):
            root = resolve_template_root(instance, path)
            if not root.is_dir():
                warnings.append(
                    f"skills template root {root} does not exist; skipping "
                    f"the directory cross-check")
            else:
                for skill in skills["selected"]:
                    if not (root / skill).is_dir():
                        errors.append(
                            f"selected skill {skill!r} has no directory under "
                            f"{root}")

    if isinstance(instance, dict):
        stale, skipped = stale_digests(instance, path)
        errors.extend(m for m in stale if m.endswith("does not exist"))
        stale = [m for m in stale if not m.endswith("does not exist")]
        (warnings if digests_warn else errors).extend(stale)
        warnings.extend(skipped)

    return errors, warnings


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _repo_root(path):
    try:
        out = subprocess.run(["git", "-C", str(Path(path).resolve().parent), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(out.stdout.strip()).resolve() if out.returncode == 0 and out.stdout.strip() else None


def _skill_root_is_local(root, manifest_path):
    base = _repo_root(manifest_path) or Path(manifest_path).resolve().parent
    try:
        root.resolve().relative_to(base)
    except ValueError:
        return False
    return True


def _digest_targets(manifest, manifest_path, skipped=None):
    """Yield (label, recorded, file, setter) for every digest the manifest records."""
    instruction_set = manifest.get("instruction_set")
    if not isinstance(instruction_set, dict):
        return
    base = Path(manifest_path).parent
    for source in instruction_set.get("sources") or []:
        if isinstance(source, dict) and isinstance(source.get("path"), str):
            yield (f"instruction_set.sources[{source.get('id')}]", source.get("digest"),
                   base / source["path"], source)
    lock = instruction_set.get("skill_lock")
    if isinstance(lock, dict):
        root = resolve_template_root(manifest, manifest_path)
        if root.is_dir() and not _skill_root_is_local(root, manifest_path):
            if skipped is not None:
                skipped.append(
                    f"skill_lock not compared: template root {root} is outside this "
                    f"manifest's repository")
        elif root.is_dir():
            for name in sorted(lock):
                yield (f"instruction_set.skill_lock[{name}]", lock[name],
                       root / name / "SKILL.md", (lock, name))


def stale_digests(manifest, manifest_path):
    """Return (stale, skipped): one message per digest that no longer matches its file."""
    problems, skipped = [], []
    for label, recorded, target, _ in _digest_targets(manifest, manifest_path, skipped):
        if not target.is_file():
            problems.append(f"{label}: {target} does not exist")
            continue
        actual = _sha256_file(target)
        if actual != recorded:
            problems.append(
                f"{label}: stale digest {str(recorded)[:12]}..., file is now "
                f"{actual[:12]}...; run with --refresh")
    return problems, skipped


def _last_commit(path):
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(path).parent), "log", "-1", "--format=%H", "--", Path(path).name],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    sha = out.stdout.strip()
    if out.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        return None
    try:
        dirty = subprocess.run(
            ["git", "-C", str(Path(path).parent), "status", "--porcelain", "--", Path(path).name],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None if dirty.returncode != 0 or dirty.stdout.strip() else sha


def refresh(path):
    """Rewrite stale digests of one manifest in place; return the labels changed."""
    path = Path(path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []  # _check_manifest reports it
    if not isinstance(manifest, dict):
        return []
    changed = []
    for label, recorded, target, holder in list(_digest_targets(manifest, path)):
        if not target.is_file():
            continue
        actual = _sha256_file(target)
        if isinstance(holder, tuple):
            lock, name = holder
            if lock[name] != actual:
                lock[name] = actual
                changed.append(label)
        else:
            if holder.get("digest") != actual:
                holder["digest"] = actual
                changed.append(label)
            sha = _last_commit(target)
            if sha and holder.get("source_rev") != f"git:{sha}":
                holder["source_rev"] = f"git:{sha}"
                if label not in changed:
                    changed.append(label)
    if changed:
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(
            f"usage: {Path(sys.argv[0]).name} [--refresh] [--digests-warn] <manifest.dispatch.json> [...]\n\n"
            "Validate one or more dispatch manifests against "
            "schemas/dispatch-manifest.schema.json and check that recorded "
            "instruction and skill digests match the files. --refresh rewrites "
            "stale digests in place first; --digests-warn reports stale digests as "
            "warnings.",
        )
        return 0
    do_refresh = "--refresh" in argv
    digests_warn = "--digests-warn" in argv
    paths = [Path(arg) for arg in argv if arg not in ("--refresh", "--digests-warn")]
    if not paths:
        print(
            f"usage: {Path(sys.argv[0]).name} <manifest.dispatch.json> [...]",
            file=sys.stderr,
        )
        return 2

    any_failed = False
    for path in paths:
        if do_refresh and path.is_file():
            for label in refresh(path):
                print(f"refreshed {path}: {label}")
        errors, warnings = _check_manifest(path, digests_warn=digests_warn)
        for warning in warnings:
            print(f"warning: {path}: {warning}")
        if errors:
            any_failed = True
            for error in errors:
                print(f"error: {path}: {error}")
        else:
            print(f"ok {path}")
    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
