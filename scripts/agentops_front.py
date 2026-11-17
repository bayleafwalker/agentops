#!/usr/bin/env python3
"""The `agentops` front door: help, topic lists, version and did-you-mean.

Called by bin/agentops; not a topic itself.

  agentops_front.py help               grouped help (bare `agentops`, --help, -h)
  agentops_front.py topics [family]    every topic with its one-line description
  agentops_front.py group <family>     members of a two-word family (estate, dispatch)
  agentops_front.py version            short commit of the agentops checkout
  agentops_front.py unknown <words>    error with did-you-mean, exit 2

Descriptions come from each script's module docstring, read from the first 4 KB
of the file (no imports, no ast), so help stays inside the 300 ms budget.
"""

from __future__ import annotations

import difflib
import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FAMILIES = ("estate", "dispatch")  # `agentops <family> <word>` -> scripts/<family>_<word>.py
HIDDEN = {"agentops_front"}
WIDTH = 78
DESC_MAX = 110
DANGLING = {"a", "an", "the", "in", "of", "and", "to", "for", "with", "on", "one", "by", "or", "that", "from", "as", "is"}

START_HERE = [
    ("estate status", "what is deployed, running and usable, per environment"),
    ("handoff", "write and read session handoffs (writes a bundle)"),
    ("dispatch run", "run a native worker in a worktree (writes a result)"),
    ("cli-contract", "check a CLI against the operator interface contract"),
]
GROUP_ORDER = ["check", "validate", "render", "dispatch", "audit", "estate", "session", "vuoro"]
DOC = re.compile(r"""(?:\s*\#[^\n]*\n|\s*\n)*\s*[rR]?("{3}|'{3})\s*(.*?)(?:\1|\Z)""", re.S)


def _clip(text: str) -> str:
    """Shorten at a clause boundary so the line reads whole, never with `...`."""
    text = text.rstrip(".:; ")
    while len(text) > DESC_MAX:
        cut = max(text.rfind(sep, 0, DESC_MAX) for sep in (", ", "; ", ": ", " - ", " ("))
        if cut < 20:
            cut = text.rfind(" ", 0, DESC_MAX)
        text = text[:cut].rstrip(".,:; ")
    words = text.split(" ")
    while len(words) > 3 and words[-1].lower() in DANGLING:
        words.pop()
    return " ".join(words).rstrip(".,:; ")


def describe(path: Path) -> str:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return ""
    match = DOC.match(head)
    if not match:
        return ""
    flat = " ".join(match.group(2).split("\n\n")[0].split())
    return _clip(re.split(r"\.\s|:\s*`", flat)[0])


def topics() -> dict[str, Path]:
    """Display name -> script. Family members read `estate status`, others `check-hook-wiring`."""
    found: dict[str, Path] = {}
    for script in sorted(SCRIPTS.glob("*.py")):
        if script.stem in HIDDEN:
            continue
        head, _, rest = script.stem.partition("_")
        name = f"{head} {rest.replace('_', '-')}" if rest and head in FAMILIES else script.stem.replace("_", "-")
        found[name] = script
    return found


def _family(name: str) -> str:
    return name.split(" ")[0] if " " in name else name.split("-")[0]


def grouped(found: dict[str, Path]) -> list[tuple[str, list[str]]]:
    by_family: dict[str, list[str]] = {}
    for name in found:
        by_family.setdefault(_family(name), []).append(name)
    groups = {f: sorted(n) for f, n in by_family.items() if len(n) > 1}
    other = sorted(n for names in by_family.values() if len(names) == 1 for n in names)
    ordered = [g for g in GROUP_ORDER if g in groups] + sorted(g for g in groups if g not in GROUP_ORDER)
    return [(g, groups[g]) for g in ordered] + ([("other", other)] if other else [])


def _rows(names: list[str], found: dict[str, Path], *, curated: bool = False) -> list[str]:
    """Aligned `name  description` rows; a name too wide for the column takes its own line."""
    width = min(max(len(n) for n in names), 26) + 2
    descriptions = dict(START_HERE)
    lines = []
    for name in names:
        desc = descriptions[name] if curated else describe(found[name])
        text = textwrap.wrap(desc, WIDTH - 2 - width, break_on_hyphens=False) or [""]
        if len(name) + 2 > width:
            lines.append(f"  {name}")
            lines += [f"  {'':<{width}}{t}" for t in text if t]
        else:
            lines += [f"  {name:<{width}}{text[0]}".rstrip()] + [f"  {'':<{width}}{t}" for t in text[1:]]
    return lines


def _family_line(group: str, names: list[str]) -> str:
    """`check  9  hook-wiring, producers, ... +4` that fits one line."""
    prefix = f"  {group:<10}{len(names):>3}  "
    shown = []
    for i, name in enumerate(names):
        short = name.split(" ", 1)[-1]
        short = short[len(group) + 1:] if short.startswith(group + "-") else short
        more = f", +{len(names) - i - 1}" if i < len(names) - 1 else ""
        if len(prefix) + len(", ".join(shown + [short])) + len(more) > WIDTH:
            return prefix + ", ".join(shown) + f", +{len(names) - i}"
        shown.append(short)
    return prefix + ", ".join(shown)


def show_help() -> int:
    found = topics()
    lines = ["agentops: estate tooling for coordinating agent work, one topic per capability.",
             "", "usage: agentops <topic> [args...]", "", "Start here:"]
    lines += _rows([n for n, _ in START_HERE], found, curated=True)
    lines += ["", "More topics, by family (`agentops topics <family>` describes each):"]
    for group, names in grouped(found):
        if group == "other":
            continue
        lines.append(_family_line(group, names))
    rest = sum(len(n) for g, n in grouped(found) if g == "other")
    lines.append(f"  {'other':<10}{rest:>3}  (see `agentops topics --all`)")
    lines += ["", "Examples:",
              "  agentops estate status --env vuoro-shared    # verdict and next commands",
              "  agentops handoff create --help               # write a handoff bundle",
              "  agentops dispatch run --dry-run ...          # resolve a worker, start nothing",
              "",
              f"{len(found)} topics: `agentops topics --all` describes them all,",
              "`agentops help <topic>` or `agentops <topic> --help` shows one; `agentops --version`."]
    print("\n".join(lines))
    return 0


def show_topics(argv: list[str]) -> int:
    found = topics()
    want = [a for a in argv if not a.startswith("-")]
    groups = [(g, n) for g, n in grouped(found) if not want or g in want]
    if not groups:
        return unknown(want)
    out = []
    if not want:
        out += ["Start here:"] + _rows([n for n, _ in START_HERE], found, curated=True) + [""]
    for group, names in groups:
        out += [f"{group} ({len(names)}):"] + _rows(names, found) + [""]
    print("\n".join(out).rstrip())
    print("\nnext: agentops <topic> --help")
    return 0


def show_group(family: str) -> int:
    found = topics()
    names = sorted(n for n in found if n.startswith(family + " "))
    print(f"usage: agentops {family} <command> [args...]\n\nCommands:")
    print("\n".join(_rows(names, found)))
    print(f"\nnext: agentops {family} <command> --help")
    return 0


def version() -> int:
    try:
        done = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5, check=False)
        sha = done.stdout.strip() if done.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        sha = ""
    print(f"agentops {sha or 'unknown (not a git checkout)'}")
    return 0


def unknown(words: list[str]) -> int:
    found = topics()
    first = words[0] if words else ""
    family = first if first in FAMILIES and len(words) > 1 else ""
    if family:
        pool = [n.split(" ", 1)[1] for n in found if n.startswith(family + " ")]
        bad, label, fix = words[1], f"{family} command", f"agentops {family}"
    else:
        pool = [n.replace(" ", "-") for n in found] + list(FAMILIES) + ["help", "topics"]
        bad, label, fix = first, "topic", "agentops topics"
    near = difflib.get_close_matches(bad.replace("_", "-"), pool, n=2, cutoff=0.6)
    print(f"error: no such {label} '{bad}'", file=sys.stderr)
    if near:
        spelled = [f"{family} {n}" if family else n for n in near]
        print(f"  did you mean {' or '.join(spelled)}?", file=sys.stderr)
    print(f"  fix: {fix}     # lists what exists", file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    mode, rest = (argv[0], argv[1:]) if argv else ("help", [])
    if mode == "help":
        return show_help()
    if mode == "topics":
        return show_topics(rest)
    if mode == "group":
        return show_group(rest[0])
    if mode == "version":
        return version()
    if mode == "unknown":
        return unknown(rest)
    print(f"agentops_front: unknown mode {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
