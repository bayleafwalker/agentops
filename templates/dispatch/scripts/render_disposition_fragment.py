#!/usr/bin/env python3
"""Render the portfolio disposition register into a project source fragment.

The register is the authority on what each repository is for and whether it is
live. Guidance that restates it by hand drifts from it -- which is the failure
this whole exercise exists to remove -- so the fragment is generated, and
`--check` fails when the checked-in copy no longer matches the register.

Only statuses that constrain what an agent may do are rendered. `active` items
are omitted deliberately: "you may work on this" is the default, and listing
forty-nine rows would spend a member's whole line budget saying nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

#: Statuses an agent must not silently work against, in the order they are rendered.
CONSTRAINING = ("retired", "frozen", "deferred", "spec-only", "hold", "promote", "unknown")

HEADER = """---
render_levels: [baseline, full]
---

## Portfolio disposition

Generated from `vuoro:docs/direction/disposition-register.yaml` by
`agentops:templates/dispatch/scripts/render_disposition_fragment.py`. Do not edit
here; change the register and re-render.

The register records status separately from intention: intention is what a plan
wants, status is what the artifact supports. Where a document and the register
disagree about whether something exists, the register was checked at the artifact.
Each entry's waking condition, evidence and supersession live in the register.
"""


def _clause(role: str, limit: int = 95) -> str:
    """The first sentence of a role, short enough to sit in a line budget.

    Waking conditions are deliberately not inlined. They run to paragraphs, and a
    fragment that reproduces them is a second copy to keep in step -- read them in
    the register, which is one lookup away and always current.
    """
    first = role.strip().split(". ")[0].strip().rstrip(".")
    if len(first) > limit:
        return first[: limit - 1].rsplit(" ", 1)[0] + "…"
    return first + "."


def render(register: dict) -> str:
    by_status: dict[str, list[dict]] = {}
    for item in register.get("items", []):
        by_status.setdefault(item.get("status", "unknown"), []).append(item)

    out = [HEADER]
    for status in CONSTRAINING:
        items = sorted(by_status.get(status, []), key=lambda i: i["key"])
        if not items:
            continue
        out.append(f"### {status}\n")
        for item in items:
            out.append(f"- `{item['key']}` — {_clause(item.get('role', ''))}")
        out.append("")

    claims = register.get("open_claims", [])
    if claims:
        out.append("### Open claims\n")
        out.append(
            "Each was re-derived from the artifact and did not reproduce as stated. "
            "Do not cite the original figure or sequence work against it.\n"
        )
        for claim in claims:
            out.append(f"- **{_clause(str(claim.get('claim')), 90)}** {_clause(str(claim.get('finding')), 150)}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="fail if --out is stale")
    args = parser.parse_args(argv)

    register = yaml.safe_load(args.register.read_text(encoding="utf-8"))
    rendered = render(register)

    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if current != rendered:
            print(f"stale: {args.out} does not match {args.register}", file=sys.stderr)
            return 1
        return 0

    args.out.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
