#!/usr/bin/env python3
"""P0 retrospective replay for operator-projection/v1.

Replays the registry's git-readable vocabularies over appservice history, derives moves by
the mechanical rules of DOSSIER-front-page-design.md §6.3, and scores them against the
pre-registered ground-truth.yaml (§6.4 board falsifier 1, §12 P0).

Every evaluator is read-only: git reads at named commits, plus one unauthenticated HTTP GET
source (the image tag map), cached with the time it was evaluated.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from operator_projection.evaluators import (  # noqa: E402,F401  (re-exported for test_replay.py)
    Move,
    Row,
    audience_configured,
    authorized,
    broker_rows,
    classify,
    configured,
    durability_rows,
    lock_rows,
    record_classes,
    service_rows,
)
from operator_projection.replay import VOCABULARIES, Replay  # noqa: E402,F401
from operator_projection.sources import ImageTags, fetch_image_tags  # noqa: E402

DEV = HERE.parents[3]


# ── local git: a dev-only GitSource; the packaged generator never runs a subprocess ────


class Git:
    def __init__(self, repo: Path):
        self.repo = repo
        self._shown: dict[tuple[str, str], str | None] = {}

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.repo), *args], check=check, capture_output=True, text=True)

    def out(self, *args: str) -> str:
        return self.run(*args).stdout

    def show(self, commit: str, path: str) -> str | None:
        key = (commit, path)
        if key not in self._shown:
            result = self.run("show", f"{commit}:{path}", check=False)
            self._shown[key] = result.stdout if result.returncode == 0 else None
        return self._shown[key]


class LocalGit:
    """GitSource over local clones, reading each repository's origin/main for the branch `main`."""

    def __init__(self, repos: dict[str, Path]):
        self.repos = {name: Git(path) for name, path in repos.items()}

    @staticmethod
    def ref(ref: str) -> str:
        return "origin/main" if ref == "main" else ref

    def show(self, repo: str, commit: str, path: str) -> str | None:
        return self.repos[repo].show(self.ref(commit), path)

    def log(self, repo: str, ref: str, paths, since=None, until=None) -> list[tuple[str, datetime]]:
        log = self.repos[repo].out("log", "--format=%H %cI", self.ref(ref), "--", *paths)
        return [(sha, datetime.fromisoformat(when)) for sha, when in (line.split() for line in log.splitlines())]

    def resolve(self, repo: str, ref: str, before: datetime | None = None) -> str | None:
        window = [f"--before={before.isoformat()}"] if before else []
        return self.repos[repo].out("rev-list", "-1", *window, self.ref(ref)).strip() or None


# ── scoring ─────────────────────────────────────────────────────────────────────


def score(truth: dict, moves: list[Move]) -> dict:
    expected: dict[tuple[str, str, str], dict] = {}
    for row in truth["moves"]:
        if not row.get("scored", True):
            continue
        key = (row["v"], str(row["at"])[:8], row["class"])
        if key in expected:
            raise ValueError(f"duplicate ground-truth group {key}")
        expected[key] = row
    produced: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for move in moves:
        produced[(move.vocabulary, move.boundary[:8], move.cls)].add(move.member)

    hits = expected.keys() & produced.keys()
    mismatched = []
    for key in sorted(hits):
        want, got = expected[key]["members"], produced[key]
        agree = len(got) == expected[key].get("count") if want == "*" else set(want) == got
        if not agree:
            mismatched.append({"group": key, "expected": want if want != "*" else f"{expected[key].get('count')} members", "produced": sorted(got)})

    def ratio(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 1.0

    per_vocabulary = {}
    for vocabulary in sorted({k[0] for k in expected} | {k[0] for k in produced}):
        e = {k for k in expected if k[0] == vocabulary}
        p = {k for k in produced if k[0] == vocabulary}
        per_vocabulary[vocabulary] = {
            "expected": len(e), "produced": len(p),
            "recall": ratio(len(e & p), len(e)), "precision": ratio(len(e & p), len(p)),
        }
    return {
        "expected": len(expected),
        "produced": len(produced),
        "recall": ratio(len(hits), len(expected)),
        "precision": ratio(len(hits), len(produced)),
        "misses": sorted(expected.keys() - produced.keys()),
        "false_positives": sorted(produced.keys() - expected.keys()),
        "member_mismatches": mismatched,
        "per_vocabulary": per_vocabulary,
    }


def pre_registration(agentops: Git, truth_path: Path, replay_path: Path) -> dict:
    """The ground truth must be committed, and committed strictly before the replay code."""

    def first_commit(path: Path) -> str | None:
        added = agentops.out("log", "--diff-filter=A", "--format=%H", "--", str(path.relative_to(agentops.repo))).split()
        return added[-1] if added else None

    truth, replay = first_commit(truth_path), first_commit(replay_path)
    if truth is None:
        raise SystemExit("refusing to score: ground-truth.yaml is not committed")
    if replay is not None:
        ordered = truth != replay and agentops.run("merge-base", "--is-ancestor", truth, replay, check=False).returncode == 0
        if not ordered:
            raise SystemExit(f"refusing to score: ground truth {truth[:8]} does not precede replay code {replay[:8]}")
    return {"ground_truth_commit": truth[:8], "replay_commit": replay[:8] if replay else "uncommitted"}


# ── report ──────────────────────────────────────────────────────────────────────


def render(meta: dict, result: dict, scored: dict, gate: dict, registry: dict) -> str:
    passed = scored["recall"] >= gate["recall"] and scored["precision"] >= gate["precision"]
    moves: list[Move] = result["moves"]
    lines = [
        "# P0 retrospective replay",
        "",
        f"- Window: {meta['window']['start']} → {meta['window']['end']} (appservice origin/main {meta['appservice_head']})",
        f"- Registry: `{registry['registry']}`; ground truth committed at `{meta['ground_truth_commit']}`, replay code at `{meta['replay_commit']}`",
        f"- Image tag map: {meta['image_tags_source']}, evaluated {meta['image_tags_evaluated_at']}",
        f"- Replayed at {meta['replayed_at']}; window base commit `{result['base'][:8]}`",
        "",
        f"## Gate: {'PASS' if passed else 'FAIL'}",
        "",
        f"Recall **{scored['recall']:.3f}** (gate {gate['recall']}), precision **{scored['precision']:.3f}** (gate {gate['precision']}) "
        f"over {scored['expected']} expected and {scored['produced']} produced move groups.",
        "",
        "| vocabulary | expected | produced | recall | precision |",
        "|---|---|---|---|---|",
    ]
    if meta.get("note"):
        lines.insert(6, f"- Run note: {meta['note']}")
    for vocabulary, s in scored["per_vocabulary"].items():
        lines.append(f"| {vocabulary} | {s['expected']} | {s['produced']} | {s['recall']:.2f} | {s['precision']:.2f} |")

    def groups(title: str, keys: list) -> None:
        lines.extend(["", f"### {title} ({len(keys)})", ""])
        lines.extend(f"- `{at}` {vocabulary} {cls}" for vocabulary, at, cls in keys)
        if not keys:
            lines.append("- none")

    groups("Misses: expected, not produced", scored["misses"])
    groups("False positives: produced, not expected", scored["false_positives"])
    lines.extend(["", f"### Member disagreements in matched groups ({len(scored['member_mismatches'])})", ""])
    lines.extend(f"- `{m['group'][1]}` {m['group'][0]} {m['group'][2]}: expected {m['expected']}, produced {len(m['produced'])}: {', '.join(m['produced'][:6])}" for m in scored["member_mismatches"])
    if not scored["member_mismatches"]:
        lines.append("- none")

    carried = next((m for m in moves if m.vocabulary == "composition.release_lock" and m.member == "work-adapter" and m.detail == "0.3.0"), None)
    lines.extend(["", "## Questions P0 was asked to resolve", ""])
    lines.append(
        f"- sprintctl 0.3.0 reached the deployed composition at `{carried.boundary[:8]}` ({carried.boundary_at[:10]})."
        if carried else "- sprintctl 0.3.0: no roll in the window carried it."
    )

    boundaries = len({m.boundary for m in moves}) + len(result["quiet"])
    final = result["final"]
    unreachable_classes = [c for c, row in final["audit.record_class"].items() if not row.passed]
    unusable_bindings = sorted(b for b, row in final["credbroker.binding"].items() if not row.passed)
    lines.extend([
        "",
        "## Substrate ledger",
        "",
        f"- {boundaries} boundary commits touched registry sources; {len(result['quiet'])} moved no enumerated member.",
        f"- Undetermined evaluations: {len(meta['undetermined'])}" + "".join(f"\n  - `{c[:8]}` {v}" for c, v in meta["undetermined"]),
        "",
        "## Hazards at window end (present state, not scored)",
        "",
    ])
    lines.extend(f"- DECLARED-UNREACHABLE audit.record_class `{c}`" for c in unreachable_classes)
    lines.extend(f"- DECLARED-UNREACHABLE credbroker.binding `{b}`" for b in unusable_bindings)
    lines.extend(f"- DIVERGED release label at `{d['boundary']}`: label {d['label']}, digest is {d['digest_release']}" for d in result["diverged"])
    lines.extend(["", "## Coverage gaps", ""])
    lines.extend(f"- `{g['id']}`: {g['reason']}" for g in registry["not_replayable"])

    lines.extend(["", f"## Move list ({len(moves)} member moves)", "", "| boundary | date | vocabulary | class | members |", "|---|---|---|---|---|"])
    grouped: dict[tuple[str, str, str, str], list[Move]] = defaultdict(list)
    for m in moves:
        grouped[(m.boundary[:8], m.boundary_at[:16], m.vocabulary, m.cls)].append(m)
    for (at, when, vocabulary, cls), members in grouped.items():
        names = [m.member + (f" ({m.detail})" if m.detail else "") for m in members]
        shown = ", ".join(names[:4]) + (f", +{len(names) - 4} more" if len(names) > 4 else "")
        lines.append(f"| `{at}` | {when} | {vocabulary} | {cls} | {shown} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--appservice", type=Path, default=DEV / "appservice")
    parser.add_argument("--vuoro", type=Path, default=DEV / "vuoro")
    parser.add_argument("--auditctl", type=Path, default=DEV / "auditctl")
    parser.add_argument("--out", type=Path, default=HERE / "out")
    parser.add_argument("--refresh-image-tags", action="store_true", help="re-fetch the ghcr tag map")
    parser.add_argument("--note", help="printed in the report header, e.g. why this run exists")
    args = parser.parse_args(argv)

    registry = yaml.safe_load((HERE / "registry.yaml").read_text())
    truth_path = HERE / "ground-truth.yaml"
    truth = yaml.safe_load(truth_path.read_text())
    agentops = Git(Path(Git(HERE).out("rev-parse", "--show-toplevel").strip()))
    registration = pre_registration(agentops, truth_path, Path(__file__).resolve())

    args.out.mkdir(parents=True, exist_ok=True)
    tags_path = args.out / "image-tags.json"
    if args.refresh_image_tags or not tags_path.exists():
        tags_path.write_text(json.dumps(fetch_image_tags(registry["external"]["image_tags"]["repository"]), indent=1) + "\n")
    tags = ImageTags(json.loads(tags_path.read_text()))

    git = LocalGit({"appservice": args.appservice, "vuoro": args.vuoro, "auditctl": args.auditctl})
    appservice = git.repos["appservice"]
    replay = Replay(registry, git, tags)
    start = datetime.fromisoformat(truth["window"]["start"])
    end = datetime.fromisoformat(truth["window"]["end"])
    result = replay.run(start, end)
    scored = score(truth, result["moves"])
    meta = {
        **registration,
        "note": args.note,
        "window": truth["window"],
        "appservice_head": appservice.out("rev-parse", "--short=8", "origin/main").strip(),
        "image_tags_source": tags.document["source"],
        "image_tags_evaluated_at": tags.document["evaluated_at"],
        "replayed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "undetermined": replay.undetermined,
    }
    (args.out / "moves.json").write_text(json.dumps(
        {"meta": meta, "score": scored, "moves": [asdict(m) for m in result["moves"]]}, indent=1, default=list
    ) + "\n")
    (args.out / "report.md").write_text(render(meta, result, scored, truth["gate"], registry))

    passed = scored["recall"] >= truth["gate"]["recall"] and scored["precision"] >= truth["gate"]["precision"]
    print(f"{'PASS' if passed else 'FAIL'} recall={scored['recall']:.3f} precision={scored['precision']:.3f} "
          f"misses={len(scored['misses'])} false_positives={len(scored['false_positives'])} -> {args.out / 'report.md'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
