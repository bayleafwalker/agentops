#!/usr/bin/env python3
"""A decision brief may not assert an owner decision without classifying it.

On 2026-08-26 one session escalated four items to the owner. Re-measured, the
true count was zero: Rule 4 already enumerated the owner touchpoints and none of
the four qualified. Every one had the same shape -- a rule's *rationale* was
recalled correctly and its *scope* wrongly, and the recollection was then treated
as the constraint. The governing text was on disk each time.

The most expensive of them argued that section 2a's two-kinds doctrine made
subagent usage an owner decision. Checked against the code instead of the prose,
``release_scorecard.py`` names the field ``usage_equivalent_usd`` and the guarded
invariant is ``total_billed_usd == worker_billed_usd``. Section 2a separates
*imputed from metered*; it says nothing about which imputed usage counts.
Subagent tokens are the same kind as frontier tokens, so including them moves the
frontier figure and leaves billed money untouched -- exactly what the invariant
permits. There was no doctrine to reopen, and an undercount is a defect.

``2026-08-26-open-owner-decisions.md`` had already recorded the same failure the
same day -- "three of the four were not [gated]. They read as owner calls because
the records describing them were stale" -- and the owner's assessment that the
human was "mostly being used as a very expensive Enter key". Prose guidance did
not hold for one working day. So this is a check.

It is deliberately crude. It cannot tell whether a classification is *correct* --
nothing mechanical can. It enforces only that the question was asked in writing,
because in all four cases the classification was never attempted, and attempting
it is what fails.

Run: python templates/dispatch/scripts/check_decision_briefs.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BRIEF_DIR = ROOT / "docs" / "plans" / "agentops"

#: Checked by content, not by directory. The first version looked only at
#: ``docs/plans/agentops/*.md`` on the reasoning that handovers are "a different
#: genre". They are, and it did not matter: handover section 2a is the exact text
#: whose scope was misread in the sharpest of the eight escalations, and widening
#: the sweep immediately found two rows in a standing handover still marked
#: "Open, owner's call" for items ruled and executed. A finite list of genres
#: reopens the hole the moment someone adds a directory, so the rule is now every
#: tracked Markdown file minus what is excluded by name below.
EXCLUDED_PREFIXES = (
    # Documents that *teach* the classification rule rather than exercise it.
    # The escalation-gate skill quotes every phrase this check looks for.
    "templates/dispatch/skills/",
)

#: Language that asserts something is the owner's to decide.
OWNER_LANGUAGE = re.compile(
    r"owner decision|owner's call|awaits? your ruling"
    r"|the owner to decide|your decision|genuinely yours|actually yours"
    # "owner ruling" is an escalation when something *needs* one and a citation
    # when a past one is being quoted. Both forms are in this repository, so the
    # citation forms -- followed by a date, or by "quoted" -- are excluded rather
    # than the phrase being dropped and the real signal with it.
    r"|owner ruling(?!\s*(?:quoted|,?\s*\d{4}-))",
    re.I,
)

#: The three axes from 2026-08-26-open-owner-decisions.md. A brief that asserts
#: an owner decision must name at least one of them, which in practice means it
#: ran the classification rather than assuming the answer.
THREE_AXES = re.compile(r"derivable|ratification|new value choice", re.I)

#: A claim about what a rule permits must point at where the rule is, so the next
#: reader can check the scope rather than inherit the recollection. Any of: a
#: source file reference, a section reference, or a numbered rule.
CITATION = re.compile(
    r"[\w./-]+\.(?:py|json|md|sh|nix)\b"        # a file
    r"|(?:§|section\s)\s?\d"                     # a section
    r"|\bRule\s+\d+",                            # a numbered rule
    re.I,
)

#: Briefs written before this check existed. Deliberately a literal list rather
#: than a date cutoff: a date cutoff silently grandfathers anything backdated,
#: and this set should only ever shrink.
GRANDFATHERED = frozenset({
    "2026-08-23-handoff-loop-and-telemetry.md",
    "2026-08-25-mechanical-bulk-boundary-decision.md",
    "2026-08-26-build-from-spec-probe.md",
    # Added when the rule was tightened and the sweep widened. Tightening a rule
    # is the one event that legitimately *grows* a list this file says should
    # only shrink; nothing else may.
    "vuoro-architecture-findings-2026-07-25.md",
    "vuoro-architecture-implementation-plan-2026-07-25.md",
    "agentops-2062-ratification-dossier-2026-08-02.md",
})


#: Split on ``#`` and ``##`` only, so a ``###`` subsection stays inside its
#: parent. Splitting on every heading makes a bare ``##`` line its own section,
#: which is uncitable by construction and produced false positives.
SECTION = re.compile(r"^#{1,2} ", re.M)


def sections(text: str) -> list[str]:
    """The document as heading-delimited blocks."""
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if SECTION.match(line) and current:
            blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def checked_documents(root: Path = ROOT) -> list[Path]:
    """Every tracked Markdown file this check ranges over."""
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "*.md"],
            check=True, capture_output=True, text=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        listed = [
            str(path.relative_to(root)) for path in sorted(root.rglob("*.md"))
        ]
    return [
        root / name for name in listed
        if not name.startswith(EXCLUDED_PREFIXES)
    ]


def faults(brief_dir: Path | None = None) -> list[str]:
    """Every document that escalates without classifying or citing, as messages.

    Two halves, deliberately scoped differently:

    * **classification** is checked over the whole document, because the house
      format puts the classification table at the top and discusses each item
      below. Requiring it section-locally over-fires on exactly the documents
      that get it right.
    * **citation** is checked in the section that makes the claim. Over the
      whole document it does not discriminate at all -- it fires on any mention
      of any filename, and these documents always name other documents.
    """
    found: list[str] = []
    paths = (
        sorted(brief_dir.glob("*.md")) if brief_dir is not None
        else checked_documents()
    )
    for path in paths:
        if path.name in GRANDFATHERED:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not OWNER_LANGUAGE.search(text):
            continue
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        if not THREE_AXES.search(text):
            found.append(
                f"{rel}: asserts an owner decision but never classifies it. "
                "Say, for each item, whether the answer is derivable, whether it "
                "needs authorization (ratification -- bring a resolved action, "
                "not a question), or whether it is a new value choice. Only the "
                "third is a real escalation."
            )
        for block in sections(text):
            if not OWNER_LANGUAGE.search(block) or CITATION.search(block):
                continue
            heading = block.splitlines()[0].strip() or "(no heading)"
            found.append(
                f"{rel}: asserts an owner decision under {heading!r} without "
                "citing the governing text there. Point at the file, section or "
                "numbered rule that makes it the owner's, in the section that "
                "makes the claim -- a remembered scope is not a constraint, and "
                "a citation elsewhere in the document is not this claim's."
            )
    return found


def main() -> int:
    problems = faults()
    if problems:
        print("decision-brief check failed:\n")
        for line in problems:
            print(f"  - {line}\n")
        return 1
    print("decision briefs: every owner escalation is classified and cited")
    return 0


if __name__ == "__main__":
    sys.exit(main())
