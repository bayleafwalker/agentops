#!/usr/bin/env python3
"""The boundary a decision must cross before it can reach the owner.

``check_decision_briefs.py`` reads Markdown. That is a backstop, and it can only
ever be one: it catches an escalation after someone has written it into a file
the sweep happens to cover. It cannot stop an agent, a CLI, or a handover
generator from emitting one, and section-local citation proves proximity, not
that the citation supports the claimed scope.

This module is the other end. A planning or review cycle emits *records*, and
the three axes are record kinds rather than prose:

* ``resolution`` -- the answer was derivable, and here is the action taken. It
  is not a decision and never reaches the queue. "Unscoped" is not a finding;
  it is an unfinished task, so a resolution must state what was done.
* ``authorization`` -- a permission prompt, a refused tool call, a human
  acceptance event. A gate, not a deliberation. Its own kind precisely so it
  stops being filed as a question: five of the eight escalations of 2026-08-26
  were gates or already-derived answers.
* ``ratification`` -- bring a resolved action for signature.
* ``new-value-choice`` -- the only real escalation, and the only kind that may
  claim the governing text does not settle the matter. It must say what is left
  over; if nothing is, the answer was derivable.

Every kind must cite governing text, and each citation must state **the scope
the rule was read as having**. That field is the whole point. All eight failures
had one shape -- a rule's rationale recalled correctly and its scope recalled
wrongly -- and each would have had to write the wrong scope down, next to the
rule's location, to get past this.

The renderer exists so the Markdown is generated from the record rather than
written alongside it. A rendered queue satisfies ``check_decision_briefs.py`` by
construction, which is the point at which the backstop stops being the thing
holding the line.

Run: python templates/dispatch/scripts/decision_request.py <record.json> [...]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE.parent / "decisions" / "decision-request.schema.json"

_spec = importlib.util.spec_from_file_location(
    "_decision_request_packet_schema", HERE / "packet_schema.py")
packet_schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(packet_schema)  # type: ignore[union-attr]

#: The kinds that are decisions at all. A resolution is an answer and an
#: authorization is a gate; neither is the owner's to deliberate.
QUEUEABLE_KINDS = ("ratification", "new-value-choice")


class DecisionError(ValueError):
    """A record that may not be emitted."""


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def violations(record: Any) -> list[str]:
    """Every reason ``record`` may not be emitted."""
    if not isinstance(record, dict):
        return ["decision record must be a JSON object"]
    schema = load_schema()
    packet_schema.check_schema_is_supported(schema)
    problems = packet_schema.validate(record, schema)

    # Beyond the schema: a new value choice that cites a scope covering the
    # claim has not found a gap, it has found the answer. The schema can require
    # the field; only this can require it to say something.
    if record.get("kind") == "new-value-choice":
        delta = (record.get("unresolved_delta") or "").strip()
        if len(delta) < 12:
            problems.append(
                "$.unresolved_delta: a new value choice must say what the "
                "governing text leaves unsettled; if nothing is left over, the "
                "answer was derivable and this is a resolution")
    for index, ref in enumerate(record.get("governing_refs") or []):
        if not isinstance(ref, dict):
            continue
        scope = (ref.get("stated_scope") or "").strip().lower()
        if scope in {"n/a", "none", "unknown", "unclear", "tbd", "unscoped"}:
            problems.append(
                f"$.governing_refs[{index}].stated_scope: {scope!r} is not a "
                "scope. Read the rule for what it ranges over -- a class, a "
                "route, a kind, a window, a path -- or do not cite it")
    return problems


def check(record: Any) -> dict[str, Any]:
    """Return ``record`` if it may be emitted, else raise."""
    problems = violations(record)
    if problems:
        raise DecisionError("; ".join(problems))
    return record


def owner_queue(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only validated ratifications and new value choices reach the owner.

    Resolutions and authorizations are dropped here rather than filtered by a
    reader, because "every consumer must know to exclude X, forever" is a
    maintained list in someone's head.
    """
    queued: list[dict[str, Any]] = []
    for record in records:
        check(record)
        if record["kind"] in QUEUEABLE_KINDS:
            queued.append(record)
    return queued


def _render_refs(record: dict[str, Any]) -> list[str]:
    lines = []
    for ref in record["governing_refs"]:
        revision = f" @ `{ref['revision']}`" if ref.get("revision") else ""
        lines.append(
            f"- `{ref['location']}`{revision} — ranges over: {ref['stated_scope']}")
    return lines


def render(records: Iterable[dict[str, Any]], title: str = "Open owner decisions") -> str:
    """Render the queue as Markdown that satisfies the decision-brief check.

    The classification vocabulary and a governing-text citation land in the same
    section as the claim, because that is what the check requires and because a
    citation elsewhere in a document is not this claim's.
    """
    records = list(records)
    queued = owner_queue(records)
    resolutions = [r for r in records if r["kind"] == "resolution"]
    authorizations = [r for r in records if r["kind"] == "authorization"]

    out = [f"# {title}", ""]
    # The preamble makes an owner claim of its own -- "these N are the owner's"
    # -- so it cites the text that classifies, exactly as every other section
    # must. Without this the renderer emitted a document its own backstop
    # rejected, which the test caught.
    out.append(
        f"{len(queued)} of {len(records)} outcomes are the owner's, classified "
        f"by the three axes in "
        f"`templates/dispatch/skills/escalation-gate/SKILL.md` against Rule 4's "
        f"enumeration of the owner touchpoints. {len(resolutions)} "
        f"{'was' if len(resolutions) == 1 else 'were'} **derivable** and "
        f"{'is' if len(resolutions) == 1 else 'are'} recorded as "
        f"{'a resolution' if len(resolutions) == 1 else 'resolutions'}; "
        f"{len(authorizations)} "
        f"{'is an authorization gate' if len(authorizations) == 1 else 'are authorization gates'} "
        f"brought for **ratification**, not deliberation. Rendered from "
        f"decision records; do not edit by hand.")
    out.append("")

    if not queued:
        out += ["## Nothing is open", "",
                "Every outcome was derivable or is a gate. See the resolutions "
                "below and the governing text each cites.", ""]
    for record in queued:
        kind = "new value choice" if record["kind"] == "new-value-choice" else "ratification"
        out.append(f"## {record['id']} — {kind}")
        out.append("")
        out.append(record["claim"])
        out.append("")
        out.append("**Governing text**")
        out += _render_refs(record)
        out.append("")
        if record.get("unresolved_delta"):
            out += [f"**What it does not settle.** {record['unresolved_delta']}", ""]
        if record.get("authority_required"):
            out += [f"**Authority required.** {record['authority_required']}", ""]
        if record.get("recommendation"):
            out += [f"**Recommendation.** {record['recommendation']}", ""]

    for heading, group, field in (
        ("Resolved, not escalated — derivable", resolutions, "resolved_action"),
        ("Authorization gates — ratification, not deliberation", authorizations, "authority_required"),
    ):
        if not group:
            continue
        out += [f"## {heading}", ""]
        for record in group:
            out.append(f"### {record['id']}")
            out.append("")
            out.append(record["claim"])
            out.append("")
            out.append(f"**{field.replace('_', ' ').capitalize()}.** {record[field]}")
            out.append("")
            out.append("**Governing text**")
            out += _render_refs(record)
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and render decision records.")
    parser.add_argument("records", nargs="+", type=Path)
    parser.add_argument("--render", action="store_true", help="print the owner queue as Markdown")
    parser.add_argument("--title", default="Open owner decisions")
    args = parser.parse_args(argv)

    loaded: list[dict[str, Any]] = []
    failed = False
    for path in args.records:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            print(f"{path}: unreadable: {error}", file=sys.stderr)
            failed = True
            continue
        problems = violations(record)
        if problems:
            failed = True
            print(f"{path}: may not be emitted:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            continue
        loaded.append(record)
    if failed:
        return 1
    if args.render:
        print(render(loaded, args.title), end="")
    else:
        queued = owner_queue(loaded)
        print(f"{len(loaded)} records valid; {len(queued)} reach the owner queue")
        for record in queued:
            print(f"  {record['kind']}: {record['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
