#!/usr/bin/env python3
"""Deterministic publication preflight and post-publish confirmation (#2562).

vuoro-dispatch-build runs this through exact-command clerical agents and decides in
workflow code what the publish agent may do, instead of leaving the rules to a prompt.

    dispatch_publish_check.py preflight --repo R --tip T [--expected SHA ...]
    dispatch_publish_check.py confirm   --repo R --tip T --action A

``preflight`` prints JSON: tip, range (origin/main..T), expected, covered (by a valid
``refs/dispatch/verified/<b>-<t>`` ref), unexpected, missing_expected, invalid_refs,
protected_hits (paths changed in the range that match ``hybrid.protected_paths`` of
the root ``*.dispatch.json``) and origin_url. A verified ref covers a commit only when
it points at <t>, <b> is an ancestor of <t>, <t> is an ancestor of the tip, and the
commit is in ``<b>..<t>``: the name alone is not evidence.

``confirm`` checks a reported publish action against the origin remote itself (never
the local remote-tracking ref) and prints ``{"confirmed": bool, ...}``.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_protected_paths import _matches_any  # noqa: E402

VERIFIED_PREFIX = "refs/dispatch/verified/"
PUSHED_ACTIONS = {"pushed", "already-on-origin"}
PR_ACTIONS = {"pr-opened", "needs-hand-pass-pr"}


def git(repo: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=check)


def resolve(repo: str, rev: str) -> str | None:
    if not re.fullmatch(r"[0-9a-fA-F]{4,64}", rev):
        return None
    result = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", check=False)
    return result.stdout.strip() or None if result.returncode == 0 else None


def is_ancestor(repo: str, ancestor: str, descendant: str) -> bool:
    return git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0


def rev_list(repo: str, spec: str) -> list[str]:
    return git(repo, "rev-list", spec).stdout.split()


def protected_patterns(repo: str, tip: str) -> list[str]:
    """Globs from root manifests as on origin/main and at the tip, so a tip cannot loosen its own rules."""
    patterns: list[str] = []
    for rev in ("origin/main", tip):
        listing = git(repo, "ls-tree", "--name-only", rev, check=False)
        if listing.returncode != 0:
            continue
        for name in listing.stdout.split("\n"):
            if not name.endswith(".dispatch.json"):
                continue
            blob = git(repo, "show", f"{rev}:{name}", check=False)
            if blob.returncode != 0:
                continue
            try:
                found = json.loads(blob.stdout)["hybrid"]["protected_paths"]
            except (ValueError, KeyError, TypeError):
                continue
            patterns.extend(p for p in found if isinstance(p, str) and p not in patterns)
    return patterns


def preflight(repo: str, tip_arg: str, expected_args: list[str]) -> dict:
    tip = resolve(repo, tip_arg)
    if tip is None:
        raise SystemExit(f"tip does not resolve: {tip_arg}")
    # Best effort: a stale origin/main would make the range look larger than it is. A failed fetch
    # (offline) falls back to the existing remote-tracking ref.
    git(repo, "fetch", "--quiet", "origin", "main", check=False)
    in_range = rev_list(repo, f"origin/main..{tip}")
    range_set = set(in_range)

    expected_full: set[str] = set()
    missing: list[str] = []
    for arg in expected_args:
        full = resolve(repo, arg)
        if full is None or not is_ancestor(repo, full, tip):
            missing.append(full or arg)
        else:
            expected_full.add(full)

    covered: set[str] = set()
    invalid: list[str] = []
    refs = git(repo, "for-each-ref", "--format=%(refname) %(objectname)", VERIFIED_PREFIX).stdout.splitlines()
    for line in refs:
        name, _, value = line.partition(" ")
        match = re.fullmatch(r"([0-9a-fA-F]{4,64})-([0-9a-fA-F]{4,64})", name[len(VERIFIED_PREFIX):])
        base = resolve(repo, match.group(1)) if match else None
        head = resolve(repo, match.group(2)) if match else None
        if not (base and head and head == value and is_ancestor(repo, base, head)):
            invalid.append(name)
            continue
        if is_ancestor(repo, head, tip):
            covered.update(range_set & set(rev_list(repo, f"{base}..{head}")))

    patterns = protected_patterns(repo, tip)
    names = git(repo, "log", "--name-only", "--format=", "--no-renames", f"origin/main..{tip}").stdout.splitlines()
    hits = sorted({n for n in names if n.strip() and _matches_any(n, patterns)})

    origin = git(repo, "remote", "get-url", "origin", check=False).stdout.strip()
    expected_in_range = expected_full & range_set
    return {
        "tip": tip,
        "range": in_range,
        "expected": sorted(expected_in_range),
        "covered": sorted(covered - expected_in_range),
        "unexpected": sorted(range_set - expected_in_range - covered),
        "missing_expected": sorted(set(missing)),
        "invalid_refs": sorted(invalid),
        "protected_hits": hits,
        "origin_url": origin,
    }


def remote_ref(repo: str, ref: str) -> tuple[str | None, str | None]:
    result = git(repo, "ls-remote", "origin", ref, check=False)
    if result.returncode != 0:
        return None, (result.stderr.strip() or "git ls-remote failed")
    for line in result.stdout.splitlines():
        sha, _, name = line.partition("\t")
        if name == ref:
            return sha, None
    return None, None


def confirm(repo: str, tip_arg: str, action: str) -> dict:
    tip = resolve(repo, tip_arg)
    if tip is None:
        raise SystemExit(f"tip does not resolve: {tip_arg}")
    report: dict = {"confirmed": False, "tip": tip, "action": action}
    if action in PUSHED_ACTIONS:
        ref = "refs/heads/main"
    elif action in PR_ACTIONS:
        ref = f"refs/heads/dispatch/publish-{tip[:12]}"
    else:
        report["error"] = f"unknown action {action!r}"
        return report
    sha, error = remote_ref(repo, ref)
    report["remote_ref"] = ref
    report["remote_sha"] = sha
    if error:
        report["error"] = error
    elif sha is None:
        pass
    elif action in PR_ACTIONS:
        report["confirmed"] = sha == tip
    else:
        if sha != tip and git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode != 0:
            git(repo, "fetch", "--quiet", "origin", ref, check=False)
        report["confirmed"] = sha == tip or is_ancestor(repo, tip, sha)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("preflight")
    pre.add_argument("--repo", required=True)
    pre.add_argument("--tip", required=True)
    pre.add_argument("--expected", action="append", default=[])
    con = sub.add_parser("confirm")
    con.add_argument("--repo", required=True)
    con.add_argument("--tip", required=True)
    con.add_argument("--action", required=True)
    args = parser.parse_args(argv)
    report = (
        preflight(args.repo, args.tip, args.expected)
        if args.command == "preflight"
        else confirm(args.repo, args.tip, args.action)
    )
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
