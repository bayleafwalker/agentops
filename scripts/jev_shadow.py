#!/usr/bin/env python3
"""Record dispatch routing decisions; score them with Jev offline.

Two halves, deliberately kept apart:

``record`` (online, inside ``vuoro-dispatch-build``)
    One call per workflow run publishes one ``dispatch.route.decision`` auditctl event
    per reasoning unit: the tier dispatch used, where it came from (explicit planner
    tier or Haiku triage), whether triage let it dispatch, and the per-item verify
    verdicts with check-outcome counts. Every field is an identifier, an enum or a
    count -- no prose -- so the relaying agent copies nothing an item author wrote, and
    there is no network call in the dispatch path. It always exits 0.

``score`` (offline, run when wanted)
    Reads recorded decisions back from the audit shards, rebuilds each unit's item text
    from sprintctl, asks Jev a pinned bundle (``jev/bundles/route-v*.json``) and writes
    one JSONL record per unit next to the recorded decision. Nothing reads these
    answers to route anything; ``jev_shadow_report.py`` measures them.

``replay``/``corpus`` run the same scoring over a corpus built from sprintctl items,
for evaluation before any decisions have been recorded.

Data minimisation
-----------------
What reaches api.typesafe.ai is built only by ``route_state`` from an explicit
allowlist: item title and description, and the manifest's risk-surface ids and paths.
No transcript, diff, environment, claim or credential material is ever included.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auditctl_resolve  # noqa: E402
import jev_client  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEV_ROOT = Path("/projects/dev")
SOURCE = "jev-shadow"
DECISION_EVENT = "dispatch.route.decision"
DEFAULT_BUNDLE = "route-v1"
TIERS = ("bounded", "standard", "hard")
SOURCES = ("explicit", "haiku-triage", "explicit+haiku-triage", "triage-missing")
VERDICTS = ("confirmed", "issues_found", "inconclusive")
CHECK_OUTCOMES = ("passed", "failed", "timed_out")
SUITE_OUTCOMES = ("passed", "failed", "timed_out", "not_required", "not_available")
MAX_TEXT = 4000
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
SAFE_ITEM_ID = re.compile(r"[0-9]+")

ItemLoader = Callable[[str, str], dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: Any, maximum: int = MAX_TEXT) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= maximum else f"{text[:maximum]}…[truncated]"


# -- recorded decisions: identifiers, enums and counts only -------------------------


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_decision(unit: Any) -> dict[str, Any]:
    """Return the decision with exactly the allowed fields, or raise ``ValueError``."""
    _need(isinstance(unit, dict), "decision must be an object")
    repo, name = unit.get("repo"), unit.get("unit")
    _need(isinstance(repo, str) and bool(SAFE_NAME.fullmatch(repo)), "repo must be a safe name")
    _need(isinstance(name, str) and bool(SAFE_NAME.fullmatch(name)), "unit must be a safe name")
    item_ids = unit.get("item_ids")
    _need(isinstance(item_ids, list) and bool(item_ids), "item_ids must be a non-empty list")
    item_ids = [str(item_id) for item_id in item_ids]
    _need(all(SAFE_ITEM_ID.fullmatch(item_id) for item_id in item_ids), "item ids must be numeric")
    _need(unit.get("tier") in TIERS, "tier must be bounded, standard or hard")
    _need(isinstance(unit.get("dispatch_ready"), bool), "dispatch_ready must be boolean")
    _need(unit.get("source") in SOURCES, f"source must be one of {SOURCES}")
    decision = {
        "repo": repo,
        "unit": name,
        "item_ids": item_ids,
        "tier": unit["tier"],
        "dispatch_ready": unit["dispatch_ready"],
        "source": unit["source"],
    }
    verify = unit.get("verify")
    if verify is not None:
        _need(isinstance(verify, dict), "verify must be an object")
        verdicts = verify.get("verdicts") or {}
        _need(
            isinstance(verdicts, dict)
            and all(str(key) in item_ids and value in VERDICTS for key, value in verdicts.items()),
            "verify.verdicts must map listed item ids to verdicts",
        )
        checks = verify.get("checks") or {}
        _need(
            isinstance(checks, dict)
            and all(
                key in CHECK_OUTCOMES and isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for key, value in checks.items()
            ),
            "verify.checks must count passed/failed/timed_out",
        )
        _need(verify.get("full_suite") in SUITE_OUTCOMES, "verify.full_suite must be a known outcome")
        decision["verify"] = {
            "verdicts": {str(key): value for key, value in verdicts.items()},
            "checks": dict(checks),
            "full_suite": verify["full_suite"],
        }
    return decision


def route_baseline_label(decision: dict[str, Any] | None) -> str | None:
    """The decision dispatch took, on the ``tier`` question's scale."""
    if not decision or decision.get("source") == "triage-missing":
        # A triage failure is not a planning decision; it has no label to compare.
        return None
    if decision.get("dispatch_ready") is False:
        return "needs_planning"
    tier = "bounded" if decision.get("tier") == "mechanical" else decision.get("tier")
    return tier if tier in TIERS else None


# -- state builder: the only code that decides what leaves this host ----------------


def _repo_dir(repo: str) -> Path:
    if not SAFE_NAME.fullmatch(repo):
        raise ValueError(f"unsafe repository name {repo[:80]!r}")
    return DEV_ROOT / repo


def load_item(repo: str, item_id: str) -> dict[str, Any]:
    """``sprintctl item show`` for one item, run from the owning repository."""
    if not SAFE_ITEM_ID.fullmatch(str(item_id)):
        raise ValueError(f"item id must be numeric, got {str(item_id)[:40]!r}")
    result = subprocess.run(
        ["sprintctl", "item", "show", "--id", str(item_id), "--json"],
        cwd=_repo_dir(repo),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"sprintctl item show {item_id} failed in {repo}")
    document = json.loads(result.stdout)
    return document.get("item", document)


def load_risk_surfaces(repo: str) -> list[dict[str, Any]]:
    manifests = sorted(_repo_dir(repo).glob("*.dispatch.json"))
    if not manifests:
        return []
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    return [
        {
            "id": surface.get("id"),
            "paths": list(surface.get("paths") or []),
            "required_on_change": bool(surface.get("required_on_change")),
        }
        for surface in manifest.get("risk_surfaces") or []
        if isinstance(surface, dict)
    ]


def route_state(
    repo: str,
    unit: str,
    items: list[dict[str, Any]],
    risk_surfaces: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "repo": repo,
        "unit": unit,
        "items": [
            {
                "item_id": str(item.get("id", item.get("item_id"))),
                "title": _text(item.get("title"), 300),
                "description": _text(item.get("description")),
            }
            for item in items
        ],
        "manifest": {"risk_surfaces": risk_surfaces},
    }


# -- scoring ------------------------------------------------------------------------


def _answer_summary(answers: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, answer in answers.items():
        if not isinstance(answer, dict):
            continue
        if "choice" in answer:
            summary[key] = {"choice": answer["choice"], "confidence": answer.get("confidence")}
        elif "noul" in answer:
            summary[key] = {"noul": answer["noul"]}
        elif "score" in answer:
            summary[key] = {"score": answer["score"], "confidence": answer.get("confidence")}
    return summary


def judge_route(
    document: dict[str, Any],
    *,
    bundle: dict[str, Any],
    item_loader: ItemLoader | None = None,
    risk_loader: Callable[[str], list[dict[str, Any]]] | None = None,
    **ask_kwargs: Any,
) -> dict[str, Any]:
    """Ask Jev about one unit; ``document`` is a recorded decision or a corpus row."""
    item_loader = item_loader or load_item
    risk_loader = risk_loader or load_risk_surfaces
    repo = str(document["repo"])
    unit = str(document.get("unit") or repo)
    item_ids = [str(item.get("item_id", item) if isinstance(item, dict) else item) for item in document.get("item_ids") or document["items"]]
    state = route_state(repo, unit, [item_loader(repo, item_id) for item_id in item_ids], risk_loader(repo))
    result = jev_client.ask(bundle, state, **ask_kwargs)
    baseline = document.get("baseline", document if "tier" in document else None)
    label = route_baseline_label(baseline)
    answer = result["answers"].get("tier")
    jev_tier = answer.get("choice") if isinstance(answer, dict) else None
    return {
        "gate": "route",
        "repo": repo,
        "unit": unit,
        "item_ids": item_ids,
        "baseline": baseline,
        "baseline_label": label,
        "jev_label": jev_tier,
        "agree": None if label is None or jev_tier is None else label == jev_tier,
        "jev_mode": result["mode"],
        "model": result["model"],
        "bundle_id": result["bundle_id"],
        "bundle_sha256": result["bundle_sha256"],
        "answers": result["answers"],
        "answer_summary": _answer_summary(result["answers"]),
        "usage": result.get("usage") or {},
        "latency_ms": result.get("latency_ms"),
        "recorded_at": _now(),
    }


def error_record(document: Any, error: BaseException) -> dict[str, Any]:
    document = document if isinstance(document, dict) else {}
    return {
        "gate": "route",
        "repo": document.get("repo"),
        "unit": document.get("unit"),
        "item_ids": document.get("item_ids") or document.get("items"),
        "jev_mode": "error",
        "error": f"{type(error).__name__}: {_text(error, 500)}",
        "recorded_at": _now(),
    }


def score_documents(documents: Iterable[dict[str, Any]], bundle: dict[str, Any], out: Path, **ask_kwargs: Any) -> dict[str, Any]:
    out.parent.mkdir(parents=True, exist_ok=True)
    counts = {"rows": 0, "records": 0, "errors": 0}
    with out.open("a", encoding="utf-8") as sink:
        for document in documents:
            counts["rows"] += 1
            try:
                record = judge_route(document, bundle=bundle, **ask_kwargs)
            except Exception as error:  # noqa: BLE001 - one bad row must not end a run
                record = error_record(document, error)
                counts["errors"] += 1
            sink.write(json.dumps(record) + "\n")
            sink.flush()
            counts["records"] += 1
    return {**counts, "out": str(out)}


def recorded_decisions(shard_dir: Path, since: str | None = None) -> list[dict[str, Any]]:
    """``dispatch.route.decision`` payloads from the audit shards, oldest first."""
    decisions = []
    for shard in sorted(shard_dir.glob("*.ndjson")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (event.get("event_type") or event.get("type")) != DECISION_EVENT or event.get("source") != SOURCE:
                continue
            occurred = str(event.get("occurred_at") or event.get("ts") or "")
            if since and occurred < since:
                continue
            try:
                decision = validate_decision(event.get("metadata"))
            except ValueError:
                continue
            decisions.append({**decision, "event_id": event.get("event_id"), "occurred_at": occurred})
    return decisions


# -- publication --------------------------------------------------------------------


def publish(event_type: str, summary: str, metadata: dict[str, Any]) -> bool:
    """Write one auditctl event. Never fatal; a missing publisher is said on stderr."""
    binary = auditctl_resolve.resolve()
    if binary is None:
        return False
    try:
        result = subprocess.run(
            [binary, "add", "--type", event_type, "--source", SOURCE, "--actor", getpass.getuser(),
             "--summary", summary, "--metadata", json.dumps(metadata)],
            cwd=ROOT,
            capture_output=True,
            env=auditctl_resolve.child_env(),
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"jev_shadow: auditctl add failed: {type(error).__name__}", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(f"jev_shadow: auditctl add exited {result.returncode}", file=sys.stderr)
    return result.returncode == 0


# -- commands -----------------------------------------------------------------------


def cmd_record(args: argparse.Namespace) -> int:
    """Publish one decision event per unit. Always exits 0."""
    published, rejected = 0, []
    try:
        document = json.loads(args.input_json)
        units = document.get("units") if isinstance(document, dict) else None
        if not isinstance(units, list):
            raise ValueError("input must be {workflow, units: [...]}")
        workflow = document.get("workflow") if document.get("workflow") in ("vuoro-dispatch-build",) else None
        for index, unit in enumerate(units):
            try:
                decision = validate_decision(unit)
            except ValueError as error:
                rejected.append({"index": index, "error": str(error)})
                continue
            decision["workflow"] = workflow
            summary = (
                f"dispatch decision {decision['repo']}/{decision['unit']}: tier={decision['tier']} "
                f"ready={decision['dispatch_ready']} source={decision['source']}"
            )
            published += publish(DECISION_EVENT, summary, decision)
    except Exception as error:  # noqa: BLE001 - recording must never fail its host
        rejected.append({"error": f"{type(error).__name__}: {_text(error, 300)}"})
    print(json.dumps({"published": published, "rejected": rejected}))
    return 0


def _default_out(stem: str) -> Path:
    return ROOT / "_artifacts" / "agentops" / "jev-shadow" / f"{stem}-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"


def cmd_score(args: argparse.Namespace) -> int:
    decisions = recorded_decisions(Path(args.shards), args.since)
    bundle = jev_client.load_bundle(args.bundle)
    out = Path(args.out) if args.out else _default_out(f"score-{bundle['bundle_id']}")
    print(json.dumps({"decisions": len(decisions), **score_documents(decisions, bundle, out, timeout=args.timeout)}))
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    bundle = jev_client.load_bundle(args.bundle)
    out = Path(args.out) if args.out else _default_out(f"replay-{bundle['bundle_id']}")
    with Path(args.corpus).open(encoding="utf-8") as corpus:
        documents = [json.loads(line) for line in corpus if line.strip()]
    print(json.dumps(score_documents(documents, bundle, out, timeout=args.timeout)))
    return 0


def cmd_corpus(args: argparse.Namespace) -> int:
    """One corpus row per sprintctl item; no baseline exists for historical items.

    Nothing recorded the tier an item was dispatched at before ``dispatch.route.decision``,
    so replay rows carry no baseline. Labels come from recorded decisions or from a
    hindsight evaluation (``jev/eval/``).
    """
    result = subprocess.run(
        ["sprintctl", "item", "list", "--json"],
        cwd=_repo_dir(args.repo),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        print(f"jev_shadow: sprintctl item list failed in {args.repo}", file=sys.stderr)
        return 1
    items = [item for item in json.loads(result.stdout) if not args.status or item.get("status") in args.status]
    items = items[: args.limit] if args.limit else items
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as sink:
        for item in items:
            sink.write(json.dumps({"repo": args.repo, "unit": f"item-{item['id']}", "items": [str(item["id"])], "baseline": None}) + "\n")
    print(json.dumps({"rows": len(items), "out": str(out)}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="publish one run's routing decisions (no network)")
    record.add_argument("--input-json", required=True, help="{workflow, units: [...]} with ids, enums and counts only")
    record.set_defaults(func=cmd_record)

    score = sub.add_parser("score", help="ask Jev about recorded decisions, offline")
    score.add_argument("--shards", default=str(ROOT / "_artifacts" / "agentops" / "audit"))
    score.add_argument("--since", help="ISO timestamp; only decisions at or after it")
    score.set_defaults(func=cmd_score)

    replay = sub.add_parser("replay", help="ask Jev about a JSONL corpus")
    replay.add_argument("--corpus", required=True)
    replay.set_defaults(func=cmd_replay)

    for command in (score, replay):
        command.add_argument("--bundle", default=DEFAULT_BUNDLE)
        command.add_argument("--out")
        command.add_argument("--timeout", type=float, default=30.0, help="per-request seconds")

    corpus = sub.add_parser("corpus", help="build a replay corpus from sprintctl items")
    corpus.add_argument("--repo", required=True)
    corpus.add_argument("--status", action="append", help="keep only these statuses (repeatable)")
    corpus.add_argument("--limit", type=int)
    corpus.add_argument("--out", required=True)
    corpus.set_defaults(func=cmd_corpus)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    recording = bool(argv) and argv[0] == "record"
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_:
        # A mangled relay must not fail the host; argparse has said why on stderr.
        return 0 if recording and exit_.code else int(exit_.code or 0)
    try:
        return args.func(args)
    except Exception:  # noqa: BLE001 - last line of defence for record
        if recording:
            traceback.print_exc(file=sys.stderr)
            return 0
        raise


if __name__ == "__main__":
    raise SystemExit(main())
