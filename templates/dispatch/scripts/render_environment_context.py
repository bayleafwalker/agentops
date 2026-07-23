#!/usr/bin/env python3
"""Render a bounded, non-secret session-context block from a Vuoro environment record.

Reuses `validate_vuoro_profiles.validate_environment` so the rendered block can
never diverge from the schema's own validation. Only `id`, `environment_class`,
`constraints`, and `runbook_refs` are rendered -- `roles`, `capabilities`, and
`identity_bindings` are never surfaced into session context.

This produces the injectable block; wiring it into the render_project.py
project-render pipeline automatically is a follow-up decision left open in
agentops sprintctl item #1190 (that pipeline has its own dirty-check/hash
machinery this script deliberately does not touch).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_vuoro_profiles import ProfileError, validate_environment  # noqa: E402


START_MARKER = "<!-- vuoro-environment-context:start -->"
END_MARKER = "<!-- vuoro-environment-context:end -->"


def render_environment_context(path: Path) -> str:
    """Render the bounded session-context block for one environment record."""
    environment = validate_environment(path)
    lines = [
        START_MARKER,
        f"Active Vuoro environment: {environment['id']} ({environment['environment_class']})",
    ]
    constraints = environment["constraints"]
    if constraints:
        lines.append("Constraints: " + ", ".join(constraints))
    runbook_refs = environment["runbook_refs"]
    if runbook_refs:
        lines.append("Runbooks:")
        lines.extend(f"- {ref}" for ref in runbook_refs)
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, type=Path)
    args = parser.parse_args()
    try:
        sys.stdout.write(render_environment_context(args.environment))
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
