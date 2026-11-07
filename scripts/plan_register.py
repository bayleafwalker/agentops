#!/usr/bin/env python3
"""Plan register: `agentops plan-register [--check | --write | --add-missing]`.

One row per plan document under docs/plans, docs/plans/agentops,
docs/plans/archive and docs/dispatch/programmes (recursively). The curated data
lives in docs/plans/register.json; docs/plans/REGISTER.md is generated from it
plus the status string each file declares about itself.

Status vocabulary (one, estate-wide):

    proposed | accepted | active | superseded | rejected | archived | reference

The ~20 ad hoc status strings found in plan files map into it through
``normalise``. A row needs a ``justification`` whenever its status is derived
rather than declared: the file carries no status line, or the curated status
differs from what the declared string normalises to. ``superseded`` needs a
``successor``.

``--check`` (the default) exits 1 when a plan file is missing from the register,
a register row names a file that no longer exists, a row breaks the rules
above, or REGISTER.md is not the current rendering. ``--write`` regenerates
REGISTER.md. ``--add-missing`` appends a derived row for every unregistered file
(for a human to review) and regenerates. Read-only apart from those two files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path("docs/plans/register.json")
OUTPUT = Path("docs/plans/REGISTER.md")
SCOPE_FLAT = ("docs/plans", "docs/plans/agentops", "docs/plans/archive")
SCOPE_RECURSIVE = ("docs/dispatch/programmes",)
EXCLUDE = {OUTPUT.as_posix()}
VOCABULARY = ("proposed", "accepted", "active", "superseded", "rejected", "archived", "reference")
DEFAULT_VERIFIED = "2026-11-07"

# A status line: "Status:" at the start of a line, after list, quote or
# emphasis markers (``- **Status:**``, ``> Status:``) or after a sentence or
# ``·`` separator on a metadata line, not mid-sentence.
STATUS_LINE = re.compile(r"(?i)(?:^|[\u00b7.;]\s)[\s>*_-]*status\W{0,4}:\s*\**\s*(.+)$")
FRONT_STATUS = re.compile(r"(?im)^status:\s*(.+)$")
SUPERSEDED_BY = re.compile(r"(?im)^\W*superseded[-_ ]by\W*:?\**\s*(.+)$")
WORK_REF = re.compile(r"\b((?:agentops|vuoro-cloud|vuoro|sprintctl|sovite|appservice|actionq|cred-broker)#\d{2,5})\b")

# Ordered: the first matching rule wins. Negations ("nothing here is adopted",
# "not a ruling") come before the words they negate.
RULES: tuple[tuple[str, str], ...] = (
    (r"\brejected\b", "rejected"),
    (r"supersed", "superseded"),
    (r"source[- ]material|observation|measurement|design aid|reference", "reference"),
    (r"not adopted|nothing here is adopted|not a ruling|nothing has been applied", "proposed"),
    (r"propos|draft|candidate|thesis|design only|plan only", "proposed"),
    (r"ratif|accept|adopt|approv|ruled|decided|reviewed|requested|revised after", "accepted"),
    (r"\bready\b|\bactive\b|in progress|(?<!not )\bimplement|\blanded\b|(?<![a-z])current", "active"),
    (r"historical|archived|retired", "archived"),
)


def plan_files(root: Path) -> list[str]:
    found: set[str] = set()
    for rel in SCOPE_FLAT:
        directory = root / rel
        if directory.is_dir():
            found.update(p.relative_to(root).as_posix() for p in directory.glob("*.md"))
    for rel in SCOPE_RECURSIVE:
        directory = root / rel
        if directory.is_dir():
            found.update(p.relative_to(root).as_posix() for p in directory.rglob("*.md"))
    return sorted(found - EXCLUDE)


def _head(path: Path, lines: int = 25) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            return "".join(next(handle, "") for _ in range(lines))
    except OSError:
        return ""


def declared_status(path: Path) -> str | None:
    head = _head(path)
    if head.startswith("---"):
        end = head.find("\n---", 3)
        match = FRONT_STATUS.search(head[: end if end > 0 else len(head)])
        if match:
            return _clean(match.group(1))
    for line in head.splitlines():
        if SUPERSEDED_BY.match(line):
            return "superseded"
        match = STATUS_LINE.search(line)
        if match:
            return _clean(match.group(1))
    return None


def _clean(text: str) -> str:
    text = re.sub(r"[*`]", "", text).strip().strip('"').strip()
    return text[:90] + ("…" if len(text) > 90 else "")


def normalise(raw: str | None) -> str | None:
    if not raw:
        return None
    lowered = raw.lower()
    for pattern, status in RULES:
        if re.search(pattern, lowered):
            return status
    return None


def derived_successor(path: Path) -> str | None:
    for line in _head(path, 15).splitlines():
        match = SUPERSEDED_BY.match(line)
        if match:
            return _clean(match.group(1))
    return None


def derived_work_ref(path: Path) -> str | None:
    head = _head(path, 30)
    match = WORK_REF.search(head)
    return match.group(1) if match else None


def load(root: Path) -> dict[str, dict]:
    path = root / DATA
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def derive_row(root: Path, rel: str) -> dict:
    path = root / rel
    raw = declared_status(path)
    status = normalise(raw) or "reference"
    row = {
        "status": status,
        "owner": "agentops (default-assigned 2026-11-07)",
        "work_ref": derived_work_ref(path),
        "successor": derived_successor(path),
        "last_verified": DEFAULT_VERIFIED,
    }
    if raw is None:
        row["justification"] = "no declared status; derived as reference pending review"
    return row


def validate(root: Path, data: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    files = plan_files(root)
    for rel in files:
        if rel not in data:
            errors.append(f"{rel}: plan file missing from {DATA}")
    for rel, row in sorted(data.items()):
        path = root / rel
        if not path.is_file():
            errors.append(f"{rel}: registered but the file does not exist")
            continue
        if rel not in files:
            errors.append(f"{rel}: registered but outside the register scope")
        status = row.get("status")
        if status not in VOCABULARY:
            errors.append(f"{rel}: status {status!r} is not in the vocabulary")
            continue
        if not row.get("owner"):
            errors.append(f"{rel}: owner is required")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("last_verified", ""))):
            errors.append(f"{rel}: last_verified must be YYYY-MM-DD")
        raw = declared_status(path)
        if (raw is None or normalise(raw) != status) and not row.get("justification"):
            errors.append(
                f"{rel}: status {status!r} is derived (declared {raw!r} -> "
                f"{normalise(raw)!r}); a justification is required")
        if status == "superseded" and not row.get("successor"):
            errors.append(f"{rel}: superseded needs a successor")
        for value in row.values():
            if isinstance(value, str) and re.search(r"\bTODO\b|\bTBD\b", value):
                errors.append(f"{rel}: placeholders (TODO/TBD) are not allowed")
    return errors


def _cell(value: object) -> str:
    if value in (None, ""):
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render(root: Path, data: dict[str, dict]) -> str:
    counts = {status: 0 for status in VOCABULARY}
    for row in data.values():
        if row.get("status") in counts:
            counts[row["status"]] += 1
    lines = [
        "# Plan register",
        "",
        "<!-- Generated by scripts/plan_register.py from docs/plans/register.json."
        " Do not hand-edit: change register.json and run"
        " `python3 scripts/plan_register.py --write`. -->",
        "",
        "One row per plan document under `docs/plans`, `docs/plans/agentops`,",
        "`docs/plans/archive` and `docs/dispatch/programmes`. Status uses one",
        "vocabulary: " + ", ".join(f"`{s}`" for s in VOCABULARY) + ".",
        "*Declared* is the status string the file states about itself; when the",
        "register's status is derived instead, *Justification* says why. Owner is",
        "the owning repository role; `default-assigned 2026-11-07` marks an owner the",
        "document did not name. Read this before treating any plan as direction;",
        "`python3 scripts/plan_register.py --check` fails when a plan file is",
        "missing from it.",
        "",
        "Counts: " + ", ".join(f"{s} {n}" for s, n in counts.items()) + ".",
        "",
        "| Plan | Status | Declared | Owner | Work ref | Successor | Last verified | Justification |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for rel in sorted(data):
        row = data[rel]
        link = Path(rel).relative_to("docs/plans") if rel.startswith("docs/plans/") else Path("..", "..", rel)
        raw = declared_status(root / rel)
        lines.append(
            f"| [{_cell(rel)}]({link.as_posix()}) | {_cell(row.get('status'))} | {_cell(raw)} | "
            f"{_cell(row.get('owner'))} | {_cell(row.get('work_ref'))} | {_cell(row.get('successor'))} | "
            f"{_cell(row.get('last_verified'))} | {_cell(row.get('justification'))} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate (default)")
    mode.add_argument("--write", action="store_true", help="regenerate REGISTER.md")
    mode.add_argument("--add-missing", action="store_true",
                      help="append derived rows for unregistered plan files, then regenerate")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root
    data = load(root)
    if args.add_missing:
        for rel in plan_files(root):
            data.setdefault(rel, derive_row(root, rel))
        (root / DATA).write_text(json.dumps(dict(sorted(data.items())), indent=2) + "\n", encoding="utf-8")
    if args.write or args.add_missing:
        (root / OUTPUT).write_text(render(root, data), encoding="utf-8")
    errors = validate(root, data)
    if not (args.write or args.add_missing):
        output = root / OUTPUT
        if not output.is_file() or output.read_text(encoding="utf-8") != render(root, data):
            errors.append(f"{OUTPUT}: stale; run python3 scripts/plan_register.py --write")
    for error in errors:
        print(error)
    if errors:
        print(f"plan register: {len(errors)} problem(s)", file=sys.stderr)
        return 1
    print(f"plan register: {len(data)} plans ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
