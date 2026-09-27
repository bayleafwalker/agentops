#!/usr/bin/env python3
"""Reconstructability coverage: TS-16's control question as a cohort funnel (M1-3).

TS-16 asks what proportion of automated activity is reconstructable
(``docs/plans/2026-09-17-target-state.md``). Counting ``mcp_exchange`` rows or
PRs cannot answer it: a session that never contacted Vuoro, or failed
silently, leaves nothing to count, and retries inflate the count. So the
denominator here is what *should* have happened, taken from a committed
cohort definition, and the numerator is what the trusted side can resolve.
The script is a derived, read-only query: it writes nothing.

**Inputs.**

- Cohort (``--cohort``, default ``docs/reconstructability/cohort.yaml``):
  Routines with a 5-field UTC cron schedule or a list of one-off fire times,
  the OAuth ``client_id`` (and optionally ``grant_ids``) their runs must be
  bound to, and the repo their PR lands in.
- Dispatched cloud sessions (``--sessions FILE``, JSONL or a JSON array of
  ``{session_id, dispatched_at, client_id, grant_ids?, slug?, report_repo?}``;
  or the cohort's ``sessions_file``). Empty is valid.
- Run records: the records export of ``vuoro_run_records.py`` (``--records``
  or ``--records-cmd``), bounded by ``--since``.
- PRs whose body mentions ``Vuoro-Run``, per report repo, through ``gh pr
  list`` (or ``--prs FILE`` offline). Report files are read at the PR head
  through ``gh api`` unless the PR entry carries ``files: {path: text}``.

**Join, stage by stage** (each invocation counts once however many runs it has):

1. *Expected invocations*: cron fire times in ``[since, until)`` (within each
   Routine's ``active_from``/``active_until``), one-off fire times in that
   range, and dispatched sessions in that range.
2. *Observed*: an invocation with at least one run bound to its client (and
   grant, when listed). A run is matched first by idempotency key
   ``routine.<slug>.<YYYYMMDDTHHMMSSZ>`` (the session's UTC start time, per
   ``docs/runbooks/cloud-routine-authoring.md``): the invocation of that slug
   whose ``[scheduled, scheduled + window)`` holds the start time (the latest
   such one). A key with a dispatched session's id as one of its
   ``.``/``:``/``/``-separated tokens matches that session. Only a run with
   no idempotency key at all is matched by time: ``created_at`` in
   ``[scheduled, scheduled + window)``; when those windows belong to more than
   one Routine or session the run is reported as ambiguous rather than
   guessed. A run whose key follows neither convention (or names a routine
   slug not in the cohort) is never matched by time, so an unrelated run
   near a skipped fire cannot make it look observed. Runs bound to a cohort
   client that match nothing are listed as ``unexpected`` and are not
   counted; runs created before ``since`` are ignored. Runs
   bound to any other client or grant are not observed. Expected invocations
   with no run are ``unknown``.
3. *Evidence-bearing*: some matched run has at least one evidence item.
4. *Fully resolvable*: some evidence-bearing run R has an outcome whose
   ``Vuoro-Run`` trailer names R, and the evidence digests match:

   - a PR in the invocation's report repo whose body names R: R must have at
     least one file evidence item (``ref`` is a repo path without a
     ``#fragment``), and each such item's digest must equal the sha256 of that
     file at the PR head;
   - otherwise, a session note of R whose trailer names R, and R has no file
     evidence item (a file digest that could be checked only against a PR
     does not get waved through by a note).

Coverage is resolvable / expected.

Usage::

    agentops reconstructability-coverage --since 2026-09-20 --records export.json
    agentops reconstructability-coverage --since 2026-09-20 \\
        --records-cmd "<bounded psql command>" --sessions sessions.jsonl --json

Exit 0 when the funnel was computed (whatever the coverage), 2 when an input
could not be read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vuoro_run_records as vrr  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COHORT = REPO_ROOT / "docs" / "reconstructability" / "cohort.yaml"
COHORT_SCHEMA = "reconstructability-cohort/v1"
DEFAULT_WINDOW_MINUTES = 120

#: Separators of an idempotency key; a session id must be a whole token.
KEY_TOKEN_RE = re.compile(r"[.:/]")
ROUTINE_KEY_RE = re.compile(r"^routine\.(?P<slug>.+)\.(?P<start>\d{8}T\d{6}Z)$")

FileFetcher = Callable[[str, str, str], "bytes | None"]


# --------------------------------------------------------------------------
# Time and cron
# --------------------------------------------------------------------------

def parse_ts(value: Any) -> datetime | None:
    """ISO date or timestamp -> aware UTC datetime (a bare date is midnight UTC)."""
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(
            timezone.utc)
    if isinstance(value, date):  # an unquoted YAML date: midnight UTC
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fmt_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


_CRON_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _cron_field(text: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for part in text.split(","):
        body, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if step < 1:
            raise ValueError(f"cron step must be >= 1 in {part!r}")
        if body == "*":
            start, end = low, high
        elif "-" in body:
            a, b = body.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = int(body)
            end = high if step_text else start
        if not (low <= start <= end <= high):
            raise ValueError(f"cron value {part!r} outside {low}-{high}")
        values.update(range(start, end + 1, step))
    return values


def parse_cron(expr: str) -> tuple[list[set[int]], bool, bool]:
    """5-field cron -> (field sets, dom restricted, dow restricted). Raises ValueError."""
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"cron needs 5 fields (minute hour dom month dow), got {expr!r}")
    try:
        sets = [_cron_field(f, lo, hi) for f, (lo, hi) in zip(fields, _CRON_BOUNDS)]
    except ValueError as exc:
        raise ValueError(f"bad cron {expr!r}: {exc}") from None
    if 7 in sets[4]:
        sets[4] = (sets[4] - {7}) | {0}
    # Vixie cron: a day field starting with "*" (e.g. "*/2") counts as unrestricted.
    return sets, not fields[2].startswith("*"), not fields[4].startswith("*")


def cron_times(expr: str, start: datetime, end: datetime) -> list[datetime]:
    """Fire times of a UTC cron expression in ``[start, end)``.

    Standard cron day rule: when both day-of-month and day-of-week are
    restricted, a day matches if either does.
    """
    (minutes, hours, doms, months, dows), dom_r, dow_r = parse_cron(expr)
    out: list[datetime] = []
    day = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    while day < end:
        dow = (day.weekday() + 1) % 7  # cron: 0 = Sunday
        dom_ok, dow_ok = day.day in doms, dow in dows
        day_ok = (dom_ok or dow_ok) if (dom_r and dow_r) else (dom_ok and dow_ok)
        if day.month in months and day_ok:
            for hour in sorted(hours):
                for minute in sorted(minutes):
                    fire = day.replace(hour=hour, minute=minute)
                    if start <= fire < end:
                        out.append(fire)
        day += timedelta(days=1)
    return out


# --------------------------------------------------------------------------
# Cohort and expected invocations
# --------------------------------------------------------------------------

@dataclass
class Invocation:
    inv_id: str
    kind: str  # "routine" | "session"
    owner: str  # routine slug or session id: one schedule's identity
    slug: str | None
    scheduled: datetime
    client_id: str
    grant_ids: tuple[str, ...]
    report_repo: str
    session_id: str | None = None
    runs: list[str] = field(default_factory=list)

    def binds(self, record: vrr.RunRecord) -> bool:
        if record.get("client_id") != self.client_id:
            return False
        return not self.grant_ids or record.get("grant_id") in self.grant_ids


def load_cohort(path: Path) -> dict[str, Any]:
    """Read and validate the cohort file. Raises ValueError on a malformed one."""
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("schema") != COHORT_SCHEMA:
        raise ValueError(f"{path}: not a {COHORT_SCHEMA} document")
    routines = doc.get("routines") or []
    if not isinstance(routines, list):
        raise ValueError(f"{path}: routines must be a list")
    for entry in routines:
        if not isinstance(entry, dict) or not isinstance(entry.get("slug"), str):
            raise ValueError(f"{path}: every routine needs a slug")
        has_cron, has_once = bool(entry.get("schedule")), bool(entry.get("once"))
        if has_cron == has_once:
            raise ValueError(f"{entry['slug']}: give exactly one of schedule (cron) or once")
        if has_cron:
            parse_cron(entry["schedule"])
        else:
            if not isinstance(entry["once"], list):
                raise ValueError(f"{entry['slug']}: once must be a list of UTC fire times")
            for value in entry["once"]:
                if parse_ts(value) is None:
                    raise ValueError(f"{entry['slug']}: bad fire time {value!r}")
        if not (entry.get("client_id") or doc.get("default_client_id")):
            raise ValueError(f"{entry['slug']}: no client_id and no default_client_id")
    return doc


def load_sessions(path: Path | None) -> list[dict[str, Any]]:
    """Dispatched cloud sessions from JSONL or a JSON array; None -> []."""
    if path is None:
        return []
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return []
    rows = json.loads(text) if text.startswith("[") else [
        json.loads(line) for line in text.splitlines() if line.strip()
    ]
    for row in rows:
        if not isinstance(row, dict) or not row.get("session_id") or \
                parse_ts(row.get("dispatched_at")) is None:
            raise ValueError(f"session rows need session_id and dispatched_at: {row!r}")
    return rows


def expected_invocations(
    cohort: dict[str, Any], sessions: list[dict[str, Any]], since: datetime, until: datetime
) -> list[Invocation]:
    default_client = cohort.get("default_client_id")
    default_repo = cohort.get("default_report_repo")
    out: list[Invocation] = []
    for entry in cohort.get("routines") or []:
        slug = entry["slug"]
        common = dict(
            kind="routine", owner=f"routine:{slug}", slug=slug,
            client_id=entry.get("client_id") or default_client,
            grant_ids=tuple(entry.get("grant_ids") or ()),
            report_repo=entry.get("report_repo") or default_repo,
        )
        if entry.get("schedule"):
            lo = max(since, parse_ts(entry.get("active_from")) or since)
            hi = min(until, parse_ts(entry.get("active_until")) or until)
            times = cron_times(entry["schedule"], lo, hi) if lo < hi else []
        else:
            times = [t for t in (parse_ts(v) for v in entry["once"]) if since <= t < until]
        for when in times:
            out.append(Invocation(inv_id=f"{slug}@{fmt_ts(when)}", scheduled=when, **common))
    for row in sessions:
        when = parse_ts(row["dispatched_at"])
        if not (since <= when < until):
            continue
        sid = str(row["session_id"])
        out.append(Invocation(
            inv_id=f"session:{sid}", kind="session", owner=f"session:{sid}",
            slug=row.get("slug"), scheduled=when, session_id=sid,
            client_id=row.get("client_id") or default_client,
            grant_ids=tuple(row.get("grant_ids") or ()),
            report_repo=row.get("report_repo") or default_repo,
        ))
    out.sort(key=lambda inv: (inv.scheduled, inv.inv_id))
    return out


# --------------------------------------------------------------------------
# Matching runs to invocations
# --------------------------------------------------------------------------

def match_runs(
    invocations: list[Invocation], runs: dict[str, vrr.RunRecord], window: timedelta,
    since: datetime | None = None, until: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Attach runs to invocations (mutates ``Invocation.runs``).

    Returns ``(unexpected, other_bindings)``: runs bound to a cohort client
    that match no invocation (with the reason), and runs bound elsewhere.
    Runs created before ``since`` are outside the period and ignored; a run
    created at or after ``until`` counts only if it matches an invocation
    (its schedule's window reaches past ``until``).
    """
    unexpected: list[dict[str, Any]] = []
    other: list[str] = []
    slugs = {inv.slug for inv in invocations if inv.slug}
    for record in sorted(runs.values(), key=lambda r: (str(r.get("created_at")), r.run_id)):
        created = parse_ts(record.get("created_at"))
        if since is not None and created is not None and created < since:
            continue
        after_period = until is not None and created is not None and created >= until
        bound = [inv for inv in invocations if inv.binds(record)]
        if not bound:
            if not after_period:
                other.append(record.run_id)
            continue
        key = str(record.get("idempotency_key") or "").strip()
        tokens = set(KEY_TOKEN_RE.split(key)) if key else set()
        chosen: Invocation | None = None
        reason = ""
        by_session = [inv for inv in bound if inv.session_id and inv.session_id in tokens]
        key_match = ROUTINE_KEY_RE.match(key)
        if by_session:
            chosen = by_session[0]
        elif key_match and key_match.group("slug") in slugs:
            try:
                start = datetime.strptime(key_match.group("start"), "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc)
            except ValueError:
                start = None
            fits = [inv for inv in bound if inv.slug == key_match.group("slug") and start
                    and inv.scheduled <= start < inv.scheduled + window]
            if fits:
                chosen = max(fits, key=lambda inv: inv.scheduled)
            else:
                reason = (f"idempotency key {key} names no expected invocation of "
                          f"{key_match.group('slug')} (manual or off-schedule fire?)")
        elif key_match:
            reason = f"idempotency key {key} names routine {key_match.group('slug')!r}, " \
                     "which is not in the cohort"
        elif key:
            reason = (f"idempotency key {key!r} follows no cohort convention "
                      "(routine.<slug>.<YYYYMMDDTHHMMSSZ> or a dispatched session id)")
        elif created is None:
            reason = "no idempotency key and no created_at"
        else:
            # Only a run with no key at all is matched by time.
            fits = [inv for inv in bound if inv.scheduled <= created < inv.scheduled + window]
            owners = sorted({inv.owner for inv in fits})
            if len(owners) == 1:
                chosen = max(fits, key=lambda inv: inv.scheduled)
            elif owners:
                reason = ("ambiguous: no idempotency key and created within the window of "
                          + ", ".join(owners))
            else:
                reason = "no idempotency key and no expected invocation within the window"
        if chosen is None and after_period:
            continue
        if chosen is not None:
            chosen.runs.append(record.run_id)
        else:
            unexpected.append({"run_id": record.run_id,
                               "created_at": record.get("created_at"), "reason": reason})
    return unexpected, other


# --------------------------------------------------------------------------
# Outcomes
# --------------------------------------------------------------------------

def pr_file_fetcher(fetch: FileFetcher) -> Callable[[str, dict[str, Any], str], "bytes | None"]:
    """Read ``path`` at a PR's head: from ``pr['files']`` when given, else through ``fetch``."""
    def read(repo: str, pr: dict[str, Any], path: str) -> bytes | None:
        files = pr.get("files")
        if isinstance(files, dict):
            value = files.get(path)
            return value.encode("utf-8") if isinstance(value, str) else value
        return fetch(repo, path, str(pr["headRefOid"]))
    return read


def check_pr_digests(
    record: vrr.RunRecord, repo: str, pr: dict[str, Any],
    read: Callable[[str, dict[str, Any], str], "bytes | None"],
) -> list[str]:
    """Why this PR does not resolve the run's evidence; [] when it does."""
    items = vrr.file_evidence(record)
    label = f"{repo}#{pr.get('number')}"
    if not items:
        return [f"{label} names the run but the run has no file evidence item to check"]
    if not isinstance(pr.get("files"), dict) and not pr.get("headRefOid"):
        return [f"{label} has no head commit (headRefOid) to check the evidence against"]
    problems = []
    for item in items:
        path = item["ref"]
        want = vrr.normalize_digest(item.get("digest"))
        if want is None:
            problems.append(f"{label}: {path} evidence digest is not sha256")
            continue
        data = read(repo, pr, path)
        if data is None:
            problems.append(f"{label}: {path} not present at the PR head")
        elif hashlib.sha256(data).hexdigest() != want:
            problems.append(f"{label}: {path} digest mismatch at the PR head")
    return problems


def resolve_run(
    record: vrr.RunRecord, repo: str, prs: list[dict[str, Any]],
    read: Callable[[str, dict[str, Any], str], "bytes | None"],
) -> tuple[str | None, list[str]]:
    """(outcome label, []) when the run resolves, else (None, reasons)."""
    naming = [pr for pr in prs if record.run_id in vrr.trailer_run_ids(pr.get("body"))]
    reasons: list[str] = []
    for pr in naming:
        problems = check_pr_digests(record, repo, pr, read)
        if not problems:
            return f"{repo}#{pr.get('number')}", []
        reasons.extend(problems)
    if naming:
        return None, reasons
    noted = [n for n in record.session_notes
             if record.run_id in vrr.trailer_run_ids(n.get("note"))]
    if noted:
        if vrr.file_evidence(record):
            return None, [f"session note names the run but its file evidence has no PR in "
                          f"{repo} to be checked against"]
        return f"session-note:{noted[0].get('note_id')}", []
    return None, [f"no PR in {repo} and no session note whose Vuoro-Run trailer names the run"]


# --------------------------------------------------------------------------
# Funnel
# --------------------------------------------------------------------------

def funnel(
    invocations: list[Invocation],
    runs: dict[str, vrr.RunRecord],
    prs_by_repo: dict[str, list[dict[str, Any]]],
    fetch: FileFetcher,
    window: timedelta,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """The four stages over the cohort. Pure apart from ``fetch``."""
    unexpected, other = match_runs(invocations, runs, window, since, until)
    read = pr_file_fetcher(fetch)
    dropped: dict[str, list[dict[str, Any]]] = {"observed": [], "evidence": [], "resolvable": []}
    counts = {"expected": len(invocations), "observed": 0, "evidence": 0, "resolvable": 0}
    rows = []
    for inv in invocations:
        row: dict[str, Any] = {"id": inv.inv_id, "kind": inv.kind,
                               "scheduled": fmt_ts(inv.scheduled), "runs": list(inv.runs),
                               "reached": "expected", "outcome": None}
        rows.append(row)
        if not inv.runs:
            dropped["observed"].append({"id": inv.inv_id, "scheduled": row["scheduled"],
                                        "reason": "no run bound to its client/grant"})
            continue
        counts["observed"] += 1
        row["reached"] = "observed"
        with_evidence = [r for r in inv.runs if runs[r].evidence]
        if not with_evidence:
            dropped["evidence"].append({"id": inv.inv_id, "runs": list(inv.runs),
                                        "reason": "no evidence items on "
                                                  + ", ".join(inv.runs)})
            continue
        counts["evidence"] += 1
        row["reached"] = "evidence"
        reasons: list[str] = []
        for run_id in with_evidence:
            outcome, why = resolve_run(runs[run_id], inv.report_repo,
                                       prs_by_repo.get(inv.report_repo, []), read)
            if outcome:
                row.update(reached="resolvable", outcome=outcome, resolved_run=run_id)
                break
            reasons.extend(f"{run_id}: {w}" for w in why)
        if row["reached"] == "resolvable":
            counts["resolvable"] += 1
        else:
            dropped["resolvable"].append({"id": inv.inv_id, "runs": with_evidence,
                                          "reason": "; ".join(reasons)})
    expected = counts["expected"]
    return {
        "stages": [
            {"stage": "expected invocations", "count": counts["expected"], "dropped": []},
            {"stage": "observed runs", "count": counts["observed"],
             "dropped": dropped["observed"]},
            {"stage": "evidence-bearing runs", "count": counts["evidence"],
             "dropped": dropped["evidence"]},
            {"stage": "fully resolvable outcomes", "count": counts["resolvable"],
             "dropped": dropped["resolvable"]},
        ],
        "unknown": {"count": len(dropped["observed"]),
                    "scheduled": [d["scheduled"] + " " + d["id"] for d in dropped["observed"]]},
        "unexpected": unexpected,
        "other_bindings": other,
        "coverage": (counts["resolvable"] / expected) if expected else None,
        "invocations": rows,
    }


def render_text(result: dict[str, Any]) -> str:
    head = result["header"]
    lines = [f"Reconstructability coverage {head['since']} .. {head['until']} "
             f"(cohort {head['cohort']} v{head['cohort_version']}, "
             f"window {head['window_minutes']}m, sessions {head['sessions']})"]
    for stage in result["stages"]:
        dropped = stage["dropped"]
        suffix = f"   dropped {len(dropped)}" if dropped else ""
        lines.append(f"  {stage['stage']:<27} {stage['count']:>4}{suffix}")
        if stage["stage"] != "observed runs":
            for d in dropped:
                lines.append(f"      - {d['id']}: {d['reason']}")
        if stage["stage"] == "fully resolvable outcomes":
            for row in result["invocations"]:
                if row["reached"] == "resolvable":
                    lines.append(f"      + {row['id']}: {row['outcome']} "
                                 f"({row['resolved_run']}; runs {len(row['runs'])})")
    unknown = result["unknown"]
    lines.append(f"unknown: {unknown['count']}")
    lines.extend(f"  - {entry}" for entry in unknown["scheduled"])
    if result["unexpected"]:
        lines.append(f"unexpected (cohort client, no expected invocation; not counted): "
                     f"{len(result['unexpected'])}")
        lines.extend(f"  - {u['run_id']} created {u['created_at']}: {u['reason']}"
                     for u in result["unexpected"])
    lines.append(f"runs bound to other clients/grants (not observed): "
                 f"{len(result['other_bindings'])}")
    resolvable = result["stages"][3]["count"]
    expected = result["stages"][0]["count"]
    ratio = "n/a" if result["coverage"] is None else f"{100 * result['coverage']:.1f}%"
    lines.append(f"coverage: {resolvable}/{expected} = {ratio}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def load_prs(path: Path) -> dict[str, list[dict[str, Any]]]:
    """``{repo: [pr, ...]}`` or a list of PRs that each carry ``repo``."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(doc, dict):
        return {repo: list(prs) for repo, prs in doc.items()}
    if isinstance(doc, list):
        out: dict[str, list[dict[str, Any]]] = {}
        for pr in doc:
            out.setdefault(pr["repo"], []).append(pr)
        return out
    raise ValueError("--prs must be a {repo: [pr]} object or a list of PRs with 'repo'")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentops reconstructability-coverage",
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--since", required=True, help="start of the window (ISO date/timestamp, UTC)")
    parser.add_argument("--until", help="end of the window (default: now)")
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT,
                        help="cohort definition (default %(default)s)")
    parser.add_argument("--sessions", type=Path, metavar="FILE",
                        help="dispatched cloud sessions (JSONL or JSON array); "
                             "overrides the cohort's sessions_file")
    vrr.add_records_arguments(parser)
    parser.add_argument("--prs", type=Path, metavar="FILE",
                        help="PRs as {repo: [pr]} JSON instead of gh pr list (offline)")
    parser.add_argument("--window-minutes", type=int, default=DEFAULT_WINDOW_MINUTES,
                        help="how long after a scheduled time a run still matches it "
                             "(default %(default)s)")
    parser.add_argument("--json", action="store_true", help="print the funnel as JSON")
    return parser


def main(argv: list[str] | None = None, fetch: FileFetcher | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    since = parse_ts(args.since)
    until = parse_ts(args.until) if args.until else datetime.now(timezone.utc)
    if since is None or until is None or since >= until:
        print("reconstructability-coverage: --since/--until must be ISO dates or timestamps "
              "with since < until", file=sys.stderr)
        return 2
    try:
        cohort = load_cohort(args.cohort)
        sessions_path = args.sessions
        if sessions_path is None and cohort.get("sessions_file"):
            sessions_path = REPO_ROOT / cohort["sessions_file"]
        sessions = load_sessions(sessions_path)
        invocations = expected_invocations(cohort, sessions, since, until)
        runs = vrr.load_records(args.records, args.records_cmd, since=args.since)
        repos = sorted({inv.report_repo for inv in invocations if inv.report_repo})
        if args.prs:
            prs_by_repo = load_prs(args.prs)
        else:
            prs_by_repo = {repo: vrr.list_trailer_prs(repo, since.date().isoformat())
                           for repo in repos}
    except (ValueError, KeyError, RuntimeError, OSError, subprocess.TimeoutExpired,
            yaml.YAMLError) as exc:
        print(f"reconstructability-coverage: cannot read inputs: {exc}", file=sys.stderr)
        return 2

    try:
        result = funnel(invocations, runs, prs_by_repo, fetch or vrr.fetch_file,
                        timedelta(minutes=args.window_minutes), since, until)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"reconstructability-coverage: cannot read a PR file: {exc}", file=sys.stderr)
        return 2
    cohort_label = args.cohort
    try:
        cohort_label = args.cohort.resolve().relative_to(REPO_ROOT)
    except ValueError:
        pass
    result["header"] = {
        "since": fmt_ts(since), "until": fmt_ts(until), "cohort": str(cohort_label),
        "cohort_version": cohort.get("version"), "window_minutes": args.window_minutes,
        "sessions": len(sessions), "runs_in_export": len(runs),
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    else:
        print(render_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
