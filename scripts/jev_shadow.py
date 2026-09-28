#!/usr/bin/env python3
"""Shadow Jev judgments beside the decisions vuoro-dispatch-* already makes.

Nothing here changes dispatch. Each subcommand asks Jev a pinned bundle of bounded
questions (``jev/bundles/*.json``), records the answers next to the decision the
workflow actually took, and exits 0 whatever happens -- a shadow must never be able
to fail the run it is observing.

Subcommands
-----------
``route``   one reasoning unit's triage outcome (explicit planner tier or Haiku
            triage) -> ``dispatch.route.shadow`` event.
``verify``  one verified unit's final, code-clamped verdicts -> one
            ``dispatch.verify.shadow`` event per item.
``replay``  the same calls over a JSONL corpus, written to a JSONL file instead of
            auditctl.
``corpus``  build a ``route`` replay corpus from a repository's sprintctl items.

Input for ``route``/``verify`` is one JSON document, either on ``--input`` (a path, or
``-`` for stdin) or as ``--input-b64``. The workflows use base64: the relaying agent
then copies an opaque token rather than retyping verifier prose, which could otherwise
steer it, and no free text is ever quoted into shell syntax.

Data minimisation
-----------------
What reaches api.typesafe.ai is built only by ``route_state``/``verify_state``, from an
explicit allowlist: item title and description, the manifest's risk-surface ids and
paths, and the verifier's item summary, concerns, check commands and outcomes. No
transcript, diff, environment, claim or credential material is ever included.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auditctl_resolve  # noqa: E402
import jev_client  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEV_ROOT = Path("/projects/dev")
SOURCE = "jev-shadow"
ROUTE_EVENT = "dispatch.route.shadow"
VERIFY_EVENT = "dispatch.verify.shadow"
TIERS = ("bounded", "standard", "hard")
VERDICTS = ("confirmed", "issues_found", "inconclusive")
MAX_TEXT = 4000
SAFE_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
#: Overall budget for one ``verify`` run. The relaying agent's shell has its own
#: timeout; items not judged within this budget are recorded as skipped rather than
#: letting a kill discard every record.
VERIFY_DEADLINE_SECONDS = 75.0

ItemLoader = Callable[[str, str], dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: Any, maximum: int = MAX_TEXT) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= maximum else f"{text[:maximum]}…[truncated]"


# -- state builders: the only code that decides what leaves this host ---------------


def _repo_dir(repo: str) -> Path:
    if not SAFE_REPO.fullmatch(repo):
        raise ValueError(f"unsafe repository name {repo[:80]!r}")
    return DEV_ROOT / repo


def load_item(repo: str, item_id: str) -> dict[str, Any]:
    """``sprintctl item show`` for one item, run from the owning repository."""
    if not str(item_id).isdigit():
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


def verify_state(repo: str, unit: str, result: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    full_suite = evidence.get("full_suite") or {}
    return {
        "repo": repo,
        "unit": unit,
        "item": {
            "item_id": str(result.get("item_id")),
            "summary": _text(result.get("summary")),
            "concerns": [_text(concern, 1000) for concern in result.get("concerns") or []],
        },
        "checks_run": [
            {"command": _text(check.get("command"), 1000), "outcome": check.get("outcome")}
            for check in evidence.get("checks_run") or []
            if isinstance(check, dict)
        ],
        "full_suite": {"outcome": full_suite.get("outcome"), "reason": _text(full_suite.get("reason"), 1000)},
    }


# -- baselines and agreement --------------------------------------------------------


def route_baseline_label(baseline: dict[str, Any] | None) -> str | None:
    """The decision the workflow took, on the ``tier`` question's scale."""
    if not baseline or baseline.get("source") == "triage-missing":
        # A triage failure is not a planning decision; it has no label to compare.
        return None
    if baseline.get("dispatch_ready") is False:
        return "needs_planning"
    tier = "bounded" if baseline.get("tier") == "mechanical" else baseline.get("tier")
    return tier if tier in TIERS else None


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


def _choice(answers: dict[str, Any], key: str) -> str | None:
    answer = answers.get(key)
    return answer.get("choice") if isinstance(answer, dict) else None


# -- judgments ----------------------------------------------------------------------


def judge_route(
    document: dict[str, Any],
    *,
    bundle: dict[str, Any],
    item_loader: ItemLoader | None = None,
    risk_loader: Callable[[str], list[dict[str, Any]]] | None = None,
    **ask_kwargs: Any,
) -> dict[str, Any]:
    item_loader = item_loader or load_item
    risk_loader = risk_loader or load_risk_surfaces
    repo = str(document["repo"])
    unit = str(document.get("unit") or repo)
    item_ids = [str(item.get("item_id", item) if isinstance(item, dict) else item) for item in document["items"]]
    items = [item_loader(repo, item_id) for item_id in item_ids]
    state = route_state(repo, unit, items, risk_loader(repo))
    result = jev_client.ask(bundle, state, **ask_kwargs)
    baseline = document.get("baseline")
    label = route_baseline_label(baseline)
    jev_tier = _choice(result["answers"], "tier")
    return {
        "gate": "route",
        "repo": repo,
        "unit": unit,
        "item_ids": item_ids,
        "baseline": baseline,
        "baseline_label": label,
        "jev_label": jev_tier,
        "agree": None if label is None or jev_tier is None else label == jev_tier,
        **_result_fields(result),
    }


def judge_verify(
    document: dict[str, Any],
    *,
    bundle: dict[str, Any],
    deadline: float | None = None,
    **ask_kwargs: Any,
):
    """Yield one record per item, so a caller can publish each as it completes."""
    repo = str(document["repo"])
    unit = str(document.get("unit") or repo)
    for result in document.get("results") or []:
        if deadline is not None and time.monotonic() > deadline:
            yield {
                **error_record("verify", document, TimeoutError("verify deadline reached before this item")),
                "item_ids": [str(result.get("item_id"))],
            }
            continue
        state = verify_state(repo, unit, result, document)
        call_kwargs = dict(ask_kwargs)
        if deadline is not None:
            remaining = max(1.0, deadline - time.monotonic())
            call_kwargs["timeout"] = min(call_kwargs.get("timeout", remaining), remaining)
        answer = jev_client.ask(bundle, state, **call_kwargs)
        verdict = result.get("verdict") if result.get("verdict") in VERDICTS else None
        jev_verdict = _choice(answer["answers"], "evidence_supports")
        yield {
            "gate": "verify",
            "repo": repo,
            "unit": unit,
            "verify_mode": document.get("mode"),
            "item_ids": [str(result.get("item_id"))],
            "baseline": {"verdict": verdict, "source": document.get("source", "code-clamped-verifier")},
            "baseline_label": verdict,
            "jev_label": jev_verdict,
            "agree": None if verdict is None or jev_verdict is None else verdict == jev_verdict,
            **_result_fields(answer),
        }


def _result_fields(result: dict[str, Any]) -> dict[str, Any]:
    return {
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


def error_record(gate: str, document: Any, error: BaseException) -> dict[str, Any]:
    repo = document.get("repo") if isinstance(document, dict) else None
    return {
        "gate": gate,
        "repo": repo,
        "unit": document.get("unit") if isinstance(document, dict) else None,
        "jev_mode": "error",
        "error": f"{type(error).__name__}: {_text(error, 500)}",
        "baseline": document.get("baseline") if isinstance(document, dict) else None,
        "recorded_at": _now(),
    }


# -- publication --------------------------------------------------------------------


def publish(event_type: str, record: dict[str, Any]) -> bool:
    """Write one auditctl event. Never fatal; a missing publisher is said on stderr."""
    binary = auditctl_resolve.resolve()
    if binary is None:
        return False
    agree = record.get("agree")
    summary = (
        f"jev {record.get('gate')} shadow {record.get('jev_mode')} for "
        f"{record.get('repo')}/{record.get('unit')}: jev={record.get('jev_label')} "
        f"baseline={record.get('baseline_label')} agree={agree}"
    )
    try:
        result = subprocess.run(
            [binary, "add", "--type", event_type, "--source", SOURCE, "--actor", getpass.getuser(),
             "--summary", summary, "--metadata", json.dumps(record)],
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


def _read_document(args: argparse.Namespace) -> Any:
    if args.input_b64 is not None:
        text = base64.b64decode("".join(args.input_b64.split()), validate=True).decode("utf-8")
    elif args.input == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.input).read_text(encoding="utf-8")
    document = json.loads(text)
    if not isinstance(document, dict):
        raise ValueError("input must be a JSON object")
    return document


def _emit(records: list[dict[str, Any]]) -> None:
    compact = [
        {key: record.get(key) for key in ("gate", "repo", "unit", "item_ids", "jev_mode", "jev_label", "baseline_label", "agree", "error")}
        for record in records
    ]
    print(json.dumps(compact))


# -- commands -----------------------------------------------------------------------


def cmd_route(args: argparse.Namespace) -> int:
    document: Any = None
    try:
        document = _read_document(args)
        records = [judge_route(document, bundle=jev_client.load_bundle(args.bundle), timeout=args.timeout)]
    except Exception as error:  # noqa: BLE001 - a shadow must not fail its host
        records = [error_record("route", document, error)]
    for record in records:
        publish(ROUTE_EVENT, record)
    _emit(records)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    document: Any = None
    records: list[dict[str, Any]] = []
    try:
        document = _read_document(args)
        deadline = time.monotonic() + args.deadline
        for record in judge_verify(document, bundle=jev_client.load_bundle(args.bundle), deadline=deadline, timeout=args.timeout):
            publish(VERIFY_EVENT, record)
            records.append(record)
    except Exception as error:  # noqa: BLE001 - a shadow must not fail its host
        record = error_record("verify", document, error)
        publish(VERIFY_EVENT, record)
        records.append(record)
    _emit(records)
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    bundle = jev_client.load_bundle(args.bundle or f"{args.gate}-v1")
    out = Path(args.out) if args.out else (
        ROOT / "_artifacts" / "agentops" / "jev-shadow" / f"replay-{args.gate}-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    counts = {"rows": 0, "records": 0, "errors": 0}
    with Path(args.corpus).open(encoding="utf-8") as corpus, out.open("a", encoding="utf-8") as sink:
        for line in corpus:
            if not line.strip():
                continue
            counts["rows"] += 1
            document = json.loads(line)
            try:
                if args.gate == "route":
                    records = [judge_route(document, bundle=bundle)]
                else:
                    records = list(judge_verify(document, bundle=bundle))
            except Exception as error:  # noqa: BLE001 - one bad row must not end a replay
                records = [error_record(args.gate, document, error)]
                counts["errors"] += 1
            for record in records:
                record["replay"] = True
                sink.write(json.dumps(record) + "\n")
                counts["records"] += 1
    print(json.dumps({**counts, "out": str(out)}))
    return 0


def cmd_corpus(args: argparse.Namespace) -> int:
    """One route-corpus row per sprintctl item; baselines are absent by construction.

    No historical record ties an item to the tier it was dispatched at (triage results
    were never persisted before ``dispatch.route.shadow``), so replay rows measure Jev's
    answer distribution only. Labelled rows come from the online shadow.
    """
    result = subprocess.run(
        ["sprintctl", "item", "list", "--json"],
        cwd=DEV_ROOT / args.repo,
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

    route = sub.add_parser("route", help="shadow one reasoning unit's routing decision")
    route.add_argument("--bundle", default="route-v1")
    route.set_defaults(func=cmd_route)

    verify = sub.add_parser("verify", help="shadow one verified unit's final verdicts")
    verify.add_argument("--bundle", default="verify-v1")
    verify.add_argument("--deadline", type=float, default=VERIFY_DEADLINE_SECONDS, help="overall seconds budget")
    verify.set_defaults(func=cmd_verify)

    for command in (route, verify):
        source = command.add_mutually_exclusive_group(required=True)
        source.add_argument("--input", help="JSON document path, or - for stdin")
        source.add_argument("--input-b64", help="base64 of the JSON document")
        command.add_argument("--timeout", type=float, default=30.0, help="per-request seconds")

    replay = sub.add_parser("replay", help="run a gate over a JSONL corpus into a JSONL file")
    replay.add_argument("--gate", choices=("route", "verify"), required=True)
    replay.add_argument("--corpus", required=True)
    replay.add_argument("--bundle")
    replay.add_argument("--out")
    replay.set_defaults(func=cmd_replay)

    corpus = sub.add_parser("corpus", help="build a route replay corpus from sprintctl items")
    corpus.add_argument("--repo", required=True)
    corpus.add_argument("--status", action="append", help="keep only these statuses (repeatable)")
    corpus.add_argument("--limit", type=int)
    corpus.add_argument("--out", required=True)
    corpus.set_defaults(func=cmd_corpus)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    shadow_command = bool(argv) and argv[0] in ("route", "verify")
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_:
        # A mangled relay must not fail the host either; argparse has said why on stderr.
        return 0 if shadow_command and exit_.code else int(exit_.code or 0)
    try:
        return args.func(args)
    except Exception:  # noqa: BLE001 - last line of defence for route/verify
        if args.command in ("route", "verify"):
            traceback.print_exc(file=sys.stderr)
            return 0
        raise


if __name__ == "__main__":
    raise SystemExit(main())
