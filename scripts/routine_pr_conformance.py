#!/usr/bin/env python3
"""Routine PR conformance: does a Routine's PR resolve to a reconstructable run? (M1-1)

A cloud Routine that follows ``docs/runbooks/cloud-routine-authoring.md``
registers a run at start, appends evidence for its findings, writes a session
note at the end, and puts ``Vuoro-Run: <run_id>`` in its PR body. This check
takes the PR number and answers, from the trusted side, whether that record
exists and is usable:

1. the PR body carries a ``Vuoro-Run:`` trailer whose value is a run handle;
2. the run exists in the records export (see ``vuoro_run_records.py`` for why
   the export and not a served read);
3. its RunManifest fields (``harness_id``, ``harness_build``, ``model_id``,
   ``recipe_id``, ``observed_profile.instruction_digest``) are non-empty;
4. it has at least one evidence item.

Exit 0 when every trailer passes, 1 when the PR is non-conformant (including
no trailer at all), 2 when the inputs could not be read. The session-note
count is reported but does not fail the check; whether evidence digests match
the files the PR adds is the coverage funnel's resolvable stage, not this check.

Usage::

    agentops routine-pr-conformance 140 --records export.json
    agentops routine-pr-conformance 140 --records-cmd "<bounded psql command>"
    agentops routine-pr-conformance 140 --pr-json pr.json --records export.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vuoro_run_records as vrr  # noqa: E402


def check_pr(pr: dict[str, Any], runs: dict[str, vrr.RunRecord]) -> dict[str, Any]:
    """Evaluate one PR against the records. Pure: no I/O."""
    failures: list[str] = []
    checked: list[dict[str, Any]] = []
    values = vrr.trailer_run_ids(pr.get("body"))
    if not values:
        failures.append("no Vuoro-Run trailer in the PR body")
    for value in values:
        entry: dict[str, Any] = {"run_id": value, "failures": []}
        checked.append(entry)
        if not vrr.RUN_ID_RE.fullmatch(value):
            unavailable = re.fullmatch(r"unavailable\s*(?:\((.*)\))?", value, re.IGNORECASE)
            if unavailable:
                reason = (unavailable.group(1) or "no reason given").strip()
                entry["failures"].append(f"the Routine reported its run unavailable: {reason}")
            else:
                entry["failures"].append(f"trailer value {value!r} is not a run_<ULID> handle")
            continue
        record = runs.get(value)
        if record is None:
            entry["failures"].append("run not found in the records export")
            continue
        gaps = record.manifest_gaps()
        if gaps:
            entry["failures"].append("RunManifest fields null or empty: " + ", ".join(gaps))
        if not record.evidence:
            entry["failures"].append("run has no evidence")
        entry.update(
            repo_id=record.get("repo_id"),
            client_id=record.get("client_id"),
            grant_id=record.get("grant_id"),
            recipe_id=record.get("recipe_id"),
            evidence=len(record.evidence),
            session_notes=len(record.session_notes),
        )
    for entry in checked:
        failures.extend(f"{entry['run_id']}: {msg}" for msg in entry["failures"])
    return {
        "pr": pr.get("number"),
        "url": pr.get("url"),
        "conformant": not failures,
        "runs": checked,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentops routine-pr-conformance",
        description="Check that a Routine PR's Vuoro-Run trailer resolves to a run with a "
                    "complete RunManifest and at least one evidence item.",
    )
    parser.add_argument("pr", type=int, help="PR number")
    parser.add_argument("--repo", default=vrr.DEFAULT_REPO, help="GitHub repo (default %(default)s)")
    parser.add_argument("--pr-json", type=Path, metavar="FILE",
                        help="read the PR (number, url, body) from a file instead of gh")
    vrr.add_records_arguments(parser)
    parser.add_argument("--json", action="store_true", help="print the verdict as JSON")
    args = parser.parse_args(argv)

    try:
        pr = (json.loads(args.pr_json.read_text(encoding="utf-8")) if args.pr_json
              else vrr.fetch_pr(args.repo, args.pr))
        runs = vrr.load_records(args.records, args.records_cmd)
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired,
            json.JSONDecodeError) as exc:
        print(f"routine-pr-conformance: cannot read inputs: {exc}", file=sys.stderr)
        return 2

    verdict = check_pr(pr, runs)
    if args.json:
        print(json.dumps(verdict, indent=2, sort_keys=True))
    else:
        label = "CONFORMANT" if verdict["conformant"] else "NOT CONFORMANT"
        print(f"{args.repo}#{verdict['pr'] or args.pr}: {label}")
        for entry in verdict["runs"]:
            if "evidence" in entry:
                print(f"  {entry['run_id']}: repo={entry['repo_id']} client={entry['client_id']} grant={entry['grant_id']} "
                      f"recipe={entry['recipe_id']} evidence={entry['evidence']} "
                      f"session_notes={entry['session_notes']}")
        for failure in verdict["failures"]:
            print(f"  FAIL {failure}")
    return 0 if verdict["conformant"] else 1


if __name__ == "__main__":
    sys.exit(main())
