#!/usr/bin/env python3
"""Score routing methods against hindsight labels in one evaluation directory.

Usage: python3 jev/eval/compare.py jev/eval/agentops-2026-09-28

Reads ``labels-*.jsonl`` (hindsight judges), ``haiku-triage.jsonl``,
``heuristic.jsonl``, ``jev-*.jsonl`` and ``split.json`` from the directory and prints,
per label set and split: exact agreement, Cohen's kappa, plan-vs-dispatch agreement,
and the two costly error directions. Not part of CI; the data is a frozen snapshot.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

TIERS = ("bounded", "standard", "hard", "needs_planning")
RANK = {"bounded": 0, "standard": 1, "hard": 2}


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_methods(directory: Path) -> dict[str, dict[str, str]]:
    methods = {
        "haiku": {r["item_id"]: "needs_planning" if r["dispatch_ready"] is False else r["tier"] for r in _rows(directory / "haiku-triage.jsonl")},
        "heuristic": {r["item_id"]: r["tier"] for r in _rows(directory / "heuristic.jsonl")},
    }
    for path in sorted(directory.glob("jev-*.jsonl")):
        methods[path.stem] = {r["item_ids"][0]: r["jev_label"] for r in _rows(path)}
    return methods


def kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    left = collections.Counter(a for a, _ in pairs)
    right = collections.Counter(b for _, b in pairs)
    expected = sum(left[x] * right[x] for x in set(left) | set(right)) / n / n
    return (observed - expected) / (1 - expected) if expected < 1 else 0.0


def score(gold: dict[str, str], predicted: dict[str, str], ids: list[str]) -> dict:
    pairs = [(gold[i], predicted[i]) for i in ids if i in gold and i in predicted and gold[i] in TIERS]
    plan = lambda label: label == "needs_planning"  # noqa: E731
    return {
        "n": len(pairs),
        "exact": round(sum(a == b for a, b in pairs) / len(pairs), 2),
        "kappa": round(kappa(pairs), 2),
        "plan_vs_dispatch": round(sum(plan(a) == plan(b) for a, b in pairs) / len(pairs), 2),
        "dispatched_needing_plan": sum(plan(a) and not plan(b) for a, b in pairs),
        "planned_ready_work": sum(not plan(a) and plan(b) for a, b in pairs),
        "under_tiered": sum(1 for a, b in pairs if a in RANK and b in RANK and RANK[b] < RANK[a]),
    }


def main(argv: list[str]) -> int:
    directory = Path(argv[1])
    split = json.loads((directory / "split.json").read_text(encoding="utf-8"))
    methods = load_methods(directory)
    judges = {path.stem.removeprefix("labels-"): {r["item_id"]: r["tier"] for r in _rows(path)} for path in sorted(directory.glob("labels-*.jsonl"))}
    if len(judges) >= 2:
        first, second = list(judges)[:2]
        shared = sorted(set(judges[first]) & set(judges[second]))
        print(f"judge agreement {first} vs {second}:", score(judges[first], judges[second], shared))
        consensus = [i for i in shared if judges[first][i] == judges[second][i]]
        judges["consensus"] = {i: judges[first][i] for i in consensus}
    for judge, gold in judges.items():
        for name, ids in (("all", split["item_ids"]), ("held_out", split["held_out"])):
            ids = [i for i in ids if i in gold]
            if not ids:
                continue
            print(f"\n== gold={judge} split={name} ==")
            for method, predicted in methods.items():
                print(f"  {method:14s}", score(gold, predicted, ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
