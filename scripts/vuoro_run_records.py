#!/usr/bin/env python3
"""Vuoro run records as the trusted side reads them (read-only, shared helper).

A hosted caller (a claude.ai Routine, a cloud session) records its work through
the Vuoro connector's record tools: ``register_run`` mints a run bound to the
caller's principal, workspace, OAuth client and grant; ``append_evidence``
extends the run's hash-chained evidence; ``write_session_note`` adds free-text
notes. sprintctl stores them in the tenant runtime's ``run``,
``evidence_item`` and ``session_note`` tables (sprintctl schema 17,
agentops#2466).

**Why an export and not a served read.** The served read path resolves a run
only for the exact binding that minted it (``work.run.resolve-v1`` answers
``run-not-found`` to anyone else; E2/E3 shared contract section 4). A
Routine's run is bound to the claude-connector client and its grant, so no
workstation identity can resolve it through the public operations, and no
``describe_run`` operation exists yet. Checking a Routine's record is
acceptance, and acceptance is on the trusted side (TS-16), so the checks read a
**records export**: the JSON that :data:`EXPORT_SQL` produces from the tenant
runtime's database, run by the operator through the sanctioned backend
inspection path (a bounded query over the private Kubernetes API; vuoro-cloud
``docs/runbooks/operator-access.md``). When a cross-binding read operation
exists, only :func:`load_records` needs a second source.

Export shape (``--records FILE``, or ``--records-cmd`` which runs a command
that reads the SQL on stdin and prints this JSON on stdout)::

    {"runs": [{"run_id": "run_<ULID>", "repo_id": ..., "principal_id": ...,
               "workspace_id": ..., "client_id": ..., "grant_id": ...,
               "idempotency_key": ..., "harness_id": ..., "harness_build": ...,
               "model_id": ..., "recipe_id": ..., "observed_profile": {...},
               "created_at": "<iso8601>",
               "evidence": [{"item_id", "chain_seq", "kind", "ref", "digest",
                             "collector", "created_at"}, ...],
               "session_notes": [{"note_id", "note", "created_at"}, ...]}]}

This module writes nothing and calls nothing but the one command it is given.

Usage::

    agentops vuoro-run-records --sql [--since 2026-09-27]   # print the export query
    agentops vuoro-run-records --records export.json --run run_...  # show one run
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

#: sprintctl's run handle: ``run_`` + a Crockford-base32 ULID (pg.py CHECK).
RUN_ID_RE = re.compile(r"run_[0-9A-HJKMNP-TV-Z]{26}")

#: The PR-body / session-note trailer linking an outcome to its run.
TRAILER_RE = re.compile(r"^[ \t>*_-]*Vuoro-Run:[ \t]*(.*?)[ \t]*$", re.MULTILINE)

#: The RunManifest fields register_run requires (vuoro_mcp_edge.record_tools).
MANIFEST_FIELDS = ("harness_id", "harness_build", "model_id", "recipe_id", "observed_profile")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?)?$")

EXPORT_SQL_TEMPLATE = """\
SELECT json_build_object(
  'exported_at', now(),
  'since', {since_literal},
  'runs', coalesce(json_agg(r ORDER BY r.created_at), '[]'::json)
)
FROM (
  SELECT run.run_id, run.repo_id, run.principal_id, run.workspace_id,
         run.client_id, run.grant_id, run.idempotency_key,
         run.harness_id, run.harness_build, run.model_id, run.recipe_id,
         run.observed_profile, run.created_at,
         (SELECT coalesce(json_agg(json_build_object(
                    'item_id', e.item_id, 'chain_seq', e.chain_seq, 'kind', e.kind,
                    'ref', e.ref, 'digest', e.digest, 'collector', e.collector,
                    'created_at', e.created_at) ORDER BY e.chain_seq), '[]'::json)
            FROM evidence_item e
           WHERE e.repo_id = run.repo_id AND e.run_id = run.run_id) AS evidence,
         (SELECT coalesce(json_agg(json_build_object(
                    'note_id', n.note_id, 'note', n.note, 'created_at', n.created_at)
                    ORDER BY n.note_id), '[]'::json)
            FROM session_note n
           WHERE n.repo_id = run.repo_id AND n.run_id = run.run_id) AS session_notes
    FROM run
   WHERE {since_clause}
) r;
"""


def export_sql(since: str | None = None) -> str:
    """The read-only export query; ``since`` (a date or timestamp) bounds run.created_at."""
    if since is None:
        return EXPORT_SQL_TEMPLATE.format(since_literal="NULL", since_clause="true")
    if not _DATE_RE.match(since):
        raise ValueError(f"--since must be an ISO date or timestamp, got {since!r}")
    literal = "'" + since + "'"
    return EXPORT_SQL_TEMPLATE.format(
        since_literal=literal, since_clause=f"run.created_at >= {literal}::timestamptz"
    )


@dataclass
class RunRecord:
    run_id: str
    raw: dict[str, Any]
    evidence: list[dict[str, Any]] = field(default_factory=list)
    session_notes: list[dict[str, Any]] = field(default_factory=list)

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def manifest_gaps(self) -> list[str]:
        """RunManifest fields that are missing, null or empty."""
        gaps = []
        for name in MANIFEST_FIELDS:
            value = self.raw.get(name)
            if name == "observed_profile":
                if not isinstance(value, dict) or not value.get("instruction_digest"):
                    gaps.append("observed_profile.instruction_digest")
            elif not isinstance(value, str) or not value.strip():
                gaps.append(name)
        return gaps


def parse_records(document: Any) -> dict[str, RunRecord]:
    """Index an export document by run_id. Raises ValueError on a malformed export."""
    if not isinstance(document, dict) or not isinstance(document.get("runs"), list):
        raise ValueError("records export must be a JSON object with a 'runs' array")
    runs: dict[str, RunRecord] = {}
    for row in document["runs"]:
        if not isinstance(row, dict) or not isinstance(row.get("run_id"), str):
            raise ValueError("every run in the export needs a string run_id")
        evidence = row.get("evidence") or []
        notes = row.get("session_notes") or []
        if not isinstance(evidence, list) or not isinstance(notes, list):
            raise ValueError(f"{row['run_id']}: evidence and session_notes must be arrays")
        runs[row["run_id"]] = RunRecord(row["run_id"], row, list(evidence), list(notes))
    return runs


def load_records(
    records_path: Path | None = None,
    records_cmd: str | None = None,
    *,
    since: str | None = None,
    timeout: float = 120.0,
) -> dict[str, RunRecord]:
    """Load run records from an export file, or from a command fed the export SQL."""
    if (records_path is None) == (records_cmd is None):
        raise ValueError("give exactly one of --records FILE or --records-cmd CMD")
    if records_path is not None:
        return parse_records(json.loads(Path(records_path).read_text(encoding="utf-8")))
    proc = subprocess.run(
        shlex.split(records_cmd or ""),
        input=export_sql(since),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"--records-cmd exited {proc.returncode}: {proc.stderr.strip()[:500]}"
        )
    return parse_records(json.loads(proc.stdout))


def trailer_run_ids(text: str | None) -> list[str]:
    """Distinct ``Vuoro-Run:`` values in a PR body or note, in order of appearance.

    Values are returned as written; callers check them against :data:`RUN_ID_RE`
    so a malformed trailer is reported rather than silently ignored.
    """
    seen: list[str] = []
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    for match in TRAILER_RE.finditer(normalized):
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] == "`":
            value = value[1:-1].strip()
        if value and value not in seen:
            seen.append(value)
    return seen


DEFAULT_REPO = "bayleafwalker/vuoro"
_PR_FIELDS = "number,url,body,headRefOid,headRefName,state,createdAt"


def _gh(args: list[str], timeout: float = 60.0) -> str:
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=timeout, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} exited {proc.returncode}: "
                           f"{proc.stderr.strip()[:300]}")
    return proc.stdout


def fetch_pr(repo: str, number: int) -> dict[str, Any]:
    """One PR's body and head through ``gh`` (read-only)."""
    return json.loads(_gh(["pr", "view", str(number), "--repo", repo, "--json", _PR_FIELDS]))


def list_trailer_prs(repo: str, since_date: str, limit: int = 500) -> list[dict[str, Any]]:
    """PRs (any state) created on or after ``since_date`` whose body mentions Vuoro-Run."""
    return json.loads(_gh([
        "pr", "list", "--repo", repo, "--state", "all", "--limit", str(limit),
        "--search", f"Vuoro-Run in:body created:>={since_date}", "--json", _PR_FIELDS,
    ]))


def fetch_file(repo: str, path: str, ref: str) -> bytes | None:
    """A file's bytes at ``ref`` through ``gh api``; None when it does not exist there."""
    proc = subprocess.run(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw",
         f"repos/{repo}/contents/{quote(path)}?ref={quote(ref, safe='')}"],
        capture_output=True, timeout=60.0, check=False,
    )
    if proc.returncode != 0:
        if b"404" in proc.stderr or b"Not Found" in proc.stderr:
            return None
        raise RuntimeError(f"gh api contents {path}@{ref} exited {proc.returncode}: "
                           f"{proc.stderr.decode(errors='replace').strip()[:300]}")
    return proc.stdout


def normalize_digest(value: Any) -> str | None:
    """``sha256:<hex>`` or bare 64-hex -> lowercase hex; anything else -> None."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text.startswith("sha256:"):
        text = text[len("sha256:"):]
    return text if re.fullmatch(r"[0-9a-f]{64}", text) else None


def file_evidence(record: RunRecord) -> list[dict[str, Any]]:
    """Evidence items that name a whole repository file by path (checkable by digest).

    The runbook's convention: the report file the PR adds is recorded as an
    item whose ``ref`` is its repository-relative path (no scheme, no
    ``#fragment``) and whose ``digest`` is ``sha256:<hex>`` of its bytes.
    Per-finding items reference ``<path>#<finding-id>`` and are not
    file-checkable.
    """
    items = []
    for item in record.evidence:
        ref = item.get("ref")
        if (isinstance(ref, str) and ref and "#" not in ref and "://" not in ref
                and not ref.startswith("/") and ":" not in ref.split("/")[0]):
            items.append(item)
    return items


def add_records_arguments(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--records", type=Path, metavar="FILE",
        help="records export JSON (the output of `agentops vuoro-run-records --sql`)",
    )
    source.add_argument(
        "--records-cmd", metavar="CMD",
        help="command that reads the export SQL on stdin and prints the export JSON, "
             "e.g. a bounded psql over the private Kubernetes API (split with shlex, no shell)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentops vuoro-run-records",
        description="Print the read-only run-records export query, or show runs from an export.",
    )
    parser.add_argument("--sql", action="store_true", help="print the export SQL and exit")
    parser.add_argument("--since", help="bound run.created_at (ISO date or timestamp)")
    parser.add_argument("--records", type=Path, metavar="FILE", help="records export JSON")
    parser.add_argument("--records-cmd", metavar="CMD", help="command producing the export")
    parser.add_argument("--run", action="append", default=[], help="run_id to show (repeatable)")
    args = parser.parse_args(argv)
    try:
        if args.sql:
            sys.stdout.write(export_sql(args.since))
            return 0
        runs = load_records(args.records, args.records_cmd, since=args.since)
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"vuoro-run-records: {exc}", file=sys.stderr)
        return 2
    selected = [runs[r] for r in args.run if r in runs] if args.run else list(runs.values())
    missing = [r for r in args.run if r not in runs]
    for record in selected:
        print(json.dumps(
            {
                "run_id": record.run_id,
                "client_id": record.get("client_id"),
                "grant_id": record.get("grant_id"),
                "created_at": record.get("created_at"),
                "manifest_gaps": record.manifest_gaps(),
                "evidence": len(record.evidence),
                "session_notes": len(record.session_notes),
            },
            sort_keys=True,
        ))
    for run_id in missing:
        print(f"{run_id}: not in the export", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
