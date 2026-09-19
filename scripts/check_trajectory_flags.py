#!/usr/bin/env python3
"""Advisory trajectory signals for the maintenance-lane review step.

Nothing at the verify stage reads the gate log or the branch diff for
*trajectory* signals -- a worker weakening a test or a gate file to make a red
gate go green, or grinding through the same gate command over and over. This
script is one local, advisory check for both.

**Not a gate.** It always exits 0, including when the gate file it was asked
for does not exist. It never rejects, runs no CI job and never asks for an
Opus escalation or a ``sprintctl`` write. A flag buys exactly one extra Sonnet
review-synthesis pass in the coordinator's review step (see
``docs/runbooks/maintenance-lane.md``, "The loop" step 3) -- nothing more.

Two signals:

* **(a) weakening** -- ``git diff base..head`` restricted to test and gate
  paths (``tests/**``, ``hooks/tests/**``, ``scripts/tests/**``,
  ``hooks/*guard*.sh``, ``hooks/gate-check.sh``, ``.github/workflows/**``)
  for a removed/loosened assert, an added skip marker, or a relaxed numeric
  threshold.
* **(b) rework** -- ``rework_rounds >= 3`` (a red gate command later
  retried, three or more times) computed from the gate log with the same
  rule as ``hooks/log-session-cost.sh`` (lines 66-71), skipping rows whose
  ``kind`` is ``"decision"`` -- the row WL-D1 (agentops#2434) adds later, so
  the two checks stay consistent without sharing an implementation.

Output is one JSON object on stdout::

    {"flags": [{"kind": "weakening"|"rework", "path"|"command": .., "detail": ..}],
     "review_passes": 0 or 1}
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Paths eligible for the weakening check. Directory globs match anything
# underneath them; the rest are exact-name or single-segment globs.
WEAKENING_PATTERNS = [
    "tests/**",
    "hooks/tests/**",
    "scripts/tests/**",
    "hooks/*guard*.sh",
    "hooks/gate-check.sh",
    ".github/workflows/**",
]

SKIP_MARKERS = (
    "pytest.mark.skip",
    "pytest.mark.xfail",
    "@pytest.mark.skip",
    "@pytest.mark.xfail",
    "|| true",
    "set +e",
    "continue-on-error: true",
)

ASSERT_RE = re.compile(r"^\s*(assert\b|self\.assert\w+\()")
NUMERIC_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*(==|>=|<=|=|>|<)\s*(-?\d+(?:\.\d+)?)")


def _matches_any(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**"):
            prefix = pattern[: -len("/**")]
            if path == prefix or path.startswith(prefix + "/"):
                return True
            continue
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def changed_paths(base: str, head: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}..{head}"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def _diff_lines(base: str, head: str, path: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", f"{base}..{head}", "--", path],
        capture_output=True, text=True, check=True,
    ).stdout
    return out.splitlines()


def _relaxed(before: str, after: str) -> bool:
    """True when a numeric comparison in ``before`` moved in the loosening
    direction in ``after`` for the same name and operator (e.g. a coverage
    or count threshold lowered, or an upper bound raised)."""
    b = NUMERIC_RE.search(before)
    a = NUMERIC_RE.search(after)
    if not b or not a:
        return False
    if b.group(1) != a.group(1) or b.group(2) != a.group(2):
        return False
    try:
        bv, av = float(b.group(3)), float(a.group(3))
    except ValueError:
        return False
    if bv == av:
        return False
    op = b.group(2)
    if op in (">=", ">"):
        # threshold the code must clear -- lowering it is a relaxation.
        return av < bv
    if op in ("<=", "<"):
        # ceiling the code must stay under -- raising it is a relaxation.
        return av > bv
    # A plain assignment ("MIN_COVERAGE=90", "max_retries = 3") has no
    # operator to say which direction is looser, so the name decides: a
    # "max"/"limit" name raised is a relaxation, anything else (most often
    # a "min"/"threshold" name) lowered is.
    name = b.group(1).lower()
    if "max" in name or "limit" in name:
        return av > bv
    return av < bv


def find_weakenings(base: str, head: str) -> list[dict]:
    flags: list[dict] = []
    for path in changed_paths(base, head):
        if not _matches_any(path, WEAKENING_PATTERNS):
            continue
        removed: list[str] = []
        added: list[str] = []
        for line in _diff_lines(base, head, path):
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("-") and not line.startswith("--"):
                removed.append(line[1:])
            elif line.startswith("+") and not line.startswith("++"):
                added.append(line[1:])

        for line in removed:
            if ASSERT_RE.match(line):
                flags.append({
                    "kind": "weakening", "path": path,
                    "detail": f"assert line removed: {line.strip()}",
                })

        for line in added:
            hit = next((m for m in SKIP_MARKERS if m in line), None)
            if hit:
                flags.append({
                    "kind": "weakening", "path": path,
                    "detail": f"skip marker added ({hit}): {line.strip()}",
                })

        for before_line in removed:
            for after_line in added:
                if _relaxed(before_line, after_line):
                    flags.append({
                        "kind": "weakening", "path": path,
                        "detail": (
                            f"numeric threshold relaxed: "
                            f"{before_line.strip()!r} -> {after_line.strip()!r}"
                        ),
                    })
    return flags


def default_gate_dir() -> str:
    """Mirrors ``hooks/gate-log.sh``'s ``GATE_DIR`` resolution."""
    return os.environ.get("AGENTOPS_GATE_LOG_DIR", "/projects/dev/.claude/state")


def default_session_id() -> str:
    """Best-effort session id for the default gate-file path.

    ``hooks/gate-log.sh`` reads ``session_id`` off the hook event; there is no
    event here, so this falls back to ``$CLAUDE_SESSION_ID`` and otherwise the
    same ``"unknown"`` placeholder the hook itself uses when the event has none.
    """
    return os.environ.get("CLAUDE_SESSION_ID") or "unknown"


def default_gate_file() -> str:
    return f"{default_gate_dir()}/gates-{default_session_id()}.jsonl"


def load_gate_rows(gate_file: str) -> list[dict]:
    path = Path(gate_file)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def rework_findings(rows: list[dict]) -> tuple[int, list[dict]]:
    """``rework_rounds`` and the per-command retry counts behind it.

    Same rule as ``hooks/log-session-cost.sh`` lines 66-71: a row counts when
    its ``ok`` is exactly ``false`` (not ``null``/unattributable) and some
    later row shares its ``cmd``. Rows with ``kind == "decision"`` -- the
    row agentops#2434 adds -- are skipped first, so the count is identical
    with or without them.
    """
    rows = [r for r in rows if r.get("kind") != "decision"]
    rework_rounds = 0
    per_command: dict[str, int] = {}
    for i, row in enumerate(rows):
        if row.get("ok") is not False:
            continue
        cmd = row.get("cmd")
        if any(later.get("cmd") == cmd for later in rows[i + 1:]):
            rework_rounds += 1
            per_command[cmd] = per_command.get(cmd, 0) + 1
    return rework_rounds, [
        {"command": cmd, "count": count}
        for cmd, count in per_command.items()
        if count >= 3
    ]


def find_rework_flags(gate_file: str) -> list[dict]:
    rows = load_gate_rows(gate_file)
    rework_rounds, repeat_failures = rework_findings(rows)
    flags: list[dict] = []
    if rework_rounds >= 3:
        flags.append({
            "kind": "rework",
            "detail": f"rework_rounds={rework_rounds} (>= 3)",
        })
    for repeat in repeat_failures:
        flags.append({
            "kind": "rework",
            "command": repeat["command"],
            "detail": f"failed then retried {repeat['count']} times",
        })
    return flags


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-file", default=None,
                         help="defaults to $GATE_DIR/gates-$SESSION.jsonl, "
                              "resolved as hooks/gate-log.sh does")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args(argv)

    gate_file = args.gate_file or default_gate_file()

    flags: list[dict] = []
    try:
        flags.extend(find_weakenings(args.base, args.head))
    except subprocess.CalledProcessError:
        pass
    flags.extend(find_rework_flags(gate_file))

    review_passes = 1 if flags else 0
    print(json.dumps({"flags": flags, "review_passes": review_passes}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
