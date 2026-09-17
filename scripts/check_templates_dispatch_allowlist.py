"""CI guard for S2 item 6: templates/dispatch was deleted except hooks/.

Fails when ``git grep -n templates/dispatch`` hits a path outside the
allowlist at ``scripts/templates_dispatch_allowlist.txt``. New code and
operative docs must not grow fresh references to the deleted tree; historical
records and the still-real templates/dispatch/hooks/ subtree (PR-B territory)
are named explicitly in that file instead of being exempted by rule.
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / "scripts" / "templates_dispatch_allowlist.txt"


def load_allowlist(path: Path) -> list[str]:
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


def is_allowed(rel_path: str, allowlist: list[str]) -> bool:
    for entry in allowlist:
        if entry.endswith("/"):
            if rel_path == entry.rstrip("/") or rel_path.startswith(entry):
                return True
        elif "*" in entry:
            if fnmatch.fnmatch(rel_path, entry):
                return True
        elif rel_path == entry:
            return True
    return False


def find_hits(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "grep", "-l", "templates/dispatch", "--"],
        cwd=root, capture_output=True, text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git grep failed: {result.stderr}")
    if result.returncode == 1:
        return []
    return [line for line in result.stdout.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--allowlist", type=Path, default=ALLOWLIST_PATH)
    args = parser.parse_args(argv)

    allowlist = load_allowlist(args.allowlist)
    hits = find_hits(args.root)
    offenders = [path for path in hits if not is_allowed(path, allowlist)]

    if offenders:
        print("templates/dispatch reference(s) outside the allowlist:", file=sys.stderr)
        for path in offenders:
            print(f"  {path}", file=sys.stderr)
        print(
            f"\nAdd the path to {args.allowlist.relative_to(args.root)} only if it is a "
            "genuine historical record or still-real templates/dispatch/hooks/ reference; "
            "otherwise fix the stale path.",
            file=sys.stderr,
        )
        return 1

    print(f"ok: {len(hits)} file(s) reference templates/dispatch, all allowlisted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
