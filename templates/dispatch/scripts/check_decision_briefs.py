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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BRIEF_DIR = ROOT / "docs" / "plans" / "agentops"

#: Language that asserts something is the owner's to decide.
OWNER_LANGUAGE = re.compile(
    r"owner decision|owner's call|owner ruling|awaits? your ruling"
    r"|the owner to decide|your decision|genuinely yours|actually yours",
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
})


def faults(brief_dir: Path = BRIEF_DIR) -> list[str]:
    """Every decision brief that escalates without classifying, as messages."""
    found: list[str] = []
    for path in sorted(brief_dir.glob("*.md")):
        if path.name in GRANDFATHERED:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not OWNER_LANGUAGE.search(text):
            continue
        # Tests point this at a temp directory, which is not under ROOT.
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
        if not CITATION.search(text):
            found.append(
                f"{rel}: asserts an owner decision without citing the governing "
                "text. Point at the file, section or numbered rule that makes it "
                "the owner's -- a remembered scope is not a constraint."
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
