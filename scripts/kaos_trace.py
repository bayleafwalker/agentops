#!/usr/bin/env python3
"""Check, query and reconcile the KAOS 2028 requirements trace (agentops#2666, AO-K01).

The trace (``docs/plans/agentops/2026-10-18-kaos-2028-roadmap.json``) is a
requirements map, not a work ledger: served sprintctl owns activity status. This
tool answers three questions about it and never writes anywhere.

``check``
    Every leaf requirement (Rxx -> Gxx) has at least one owner, obstacle,
    feature, activity and acceptance path; every reference resolves; the
    dependency graph is acyclic; the trace carries no work-state fields; and the
    roadmap Markdown agrees with the JSON on requirements and served items.
    Activities with no obstacle of their own are reported as warnings: the
    obstacle is then only inherited from their goal.

``impact --goal Gxx``
    A changed goal identifies the requirements, features, obstacles and
    activities it governs, the activities that transitively depend on those,
    the refinements under them, and every tracker item involved.

``reconcile``
    Read-only comparison of every tracker reference in the trace against live
    served sprintctl (``sprintctl --repo-id R --allow-markerless-nonlocal item
    show --id N --json``, run from an empty directory so no repository marker
    applies). A reference is ``ok`` when the item exists in the named repository
    and, for an item registered by the roadmap, names its activity ID.

Usage::

    kaos_trace.py check [--json]
    kaos_trace.py impact --goal G01 [--goal G02] [--json]
    kaos_trace.py reconcile [--sprintctl sprintctl] [--json]

Exit status: 0 clean, 1 findings (check errors, reconcile mismatches), 2 usage.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACE = REPO_ROOT / "docs/plans/agentops/2026-10-18-kaos-2028-roadmap.json"
TRACE_KIND = "requirements-trace-not-work-state"
REF_RE = re.compile(r"^(?P<repo>[a-z0-9][a-z0-9-]*)#(?P<id>[1-9][0-9]*)$")
# Status lives in served sprintctl; a trace that grows one of these is a second ledger.
WORK_STATE_KEYS = frozenset(
    {"status", "state", "done", "completed", "progress", "assignee", "claimed_by", "reservation"}
)
MD_REQUIREMENT_RE = re.compile(r"^\|\s*(R\d{2})\s*\|\s*(G\d{2})\s*\|")
MD_ACTIVITY_RE = re.compile(r"^###\s+([A-Z]+-K\d{2})\s+—")
MD_SERVED_RE = re.compile(r"^-\s+\*\*Served item:\*\*\s+([a-z0-9-]+#\d+)")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": not self.errors, "errors": self.errors, "warnings": self.warnings}


def load_trace(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _obstacles(trace: dict) -> list[dict]:
    out = []
    for row in trace.get("obstacles", []):
        oid, goals, title, acts = row
        out.append({"id": oid, "goals": goals.split(), "title": title, "activities": acts.split()})
    return out


def _activities(trace: dict) -> dict[str, dict]:
    return {a["id"]: a for a in trace.get("activities", [])}


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    white, grey, black = 0, 1, 2
    colour = {n: white for n in graph}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        colour[node] = grey
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt not in colour:
                continue
            if colour[nxt] == grey:
                return stack[stack.index(nxt):] + [nxt]
            if colour[nxt] == white:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        colour[node] = black
        return None

    for node in sorted(graph):
        if colour[node] == white:
            found = visit(node)
            if found:
                return found
    return None


def _walk_keys(obj, path: str = "") -> Iterable[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else k
            if k in WORK_STATE_KEYS:
                yield here
            yield from _walk_keys(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def check_trace(trace: dict, markdown: str | None = None) -> Report:
    rep = Report()
    err, warn = rep.errors.append, rep.warnings.append

    if trace.get("kind") != TRACE_KIND:
        err(f"kind is {trace.get('kind')!r}, expected {TRACE_KIND!r}")
    for key in _walk_keys(trace):
        err(f"work-state field {key}: status belongs to served sprintctl, not the trace")

    goals = trace.get("goals", [])
    if len(set(goals)) != len(goals):
        err("duplicate goal IDs")
    goal_set = set(goals)
    features = trace.get("features", {})
    acts = _activities(trace)
    if len(acts) != len(trace.get("activities", [])):
        err("duplicate activity IDs")
    obstacles = _obstacles(trace)

    for o in obstacles:
        for g in o["goals"]:
            if g not in goal_set:
                err(f"obstacle {o['id']}: unknown goal {g}")
        for a in o["activities"]:
            if a not in acts:
                err(f"obstacle {o['id']}: unknown activity {a}")

    seen_refs: dict[str, str] = {}

    def claim_ref(ref: str | None, holder: str) -> None:
        if not ref:
            err(f"{holder}: no tracker reference")
            return
        if not REF_RE.match(ref):
            err(f"{holder}: malformed tracker reference {ref!r}")
            return
        if ref in seen_refs and seen_refs[ref] != holder:
            err(f"{holder}: tracker reference {ref} already bound to {seen_refs[ref]}")
        seen_refs.setdefault(ref, holder)

    obstacle_acts = {a for o in obstacles for a in o["activities"]}
    for aid, a in acts.items():
        where = f"activity {aid}"
        if not a.get("owner"):
            err(f"{where}: no owner")
        if a.get("goal") not in goal_set:
            err(f"{where}: unknown goal {a.get('goal')!r}")
        if a.get("feature") not in features:
            err(f"{where}: unknown feature {a.get('feature')!r}")
        if not (a.get("acceptance") or "").strip():
            err(f"{where}: no acceptance path")
        for dep in a.get("depends_on", []):
            if dep not in acts:
                err(f"{where}: depends on unknown activity {dep}")
        claim_ref(a.get("served_ref"), where)
        existing = a.get("existing_item")
        if existing and existing != a.get("served_ref"):
            err(f"{where}: existing_item {existing} differs from served_ref {a.get('served_ref')}")
        if aid not in obstacle_acts:
            warn(f"{where}: no obstacle names it directly (inherits goal {a.get('goal')} obstacles)")

    cycle = _find_cycle({aid: list(a.get("depends_on", [])) for aid, a in acts.items()})
    if cycle:
        err("dependency cycle: " + " -> ".join(cycle))

    requirements = trace.get("requirements")
    if not requirements:
        err("no requirements: leaf requirements (Rxx -> Gxx) must be listed")
        requirements = []
    req_goals = set()
    for rid, gid in requirements:
        where = f"requirement {rid} ({gid})"
        req_goals.add(gid)
        if gid not in goal_set:
            err(f"{where}: unknown goal")
            continue
        mapped = [a for a in acts.values() if a.get("goal") == gid]
        if not mapped:
            err(f"{where}: no activity")
        if not any(a.get("owner") for a in mapped):
            err(f"{where}: no owner")
        if not any(a.get("feature") in features for a in mapped):
            err(f"{where}: no feature")
        if not any((a.get("acceptance") or "").strip() for a in mapped):
            err(f"{where}: no acceptance path")
        if not any(gid in o["goals"] for o in obstacles):
            err(f"{where}: no obstacle")
    for g in sorted(goal_set - req_goals):
        err(f"goal {g}: no leaf requirement")

    for ref_block in trace.get("refinements", []):
        parent = ref_block.get("parent")
        where = f"refinement of {parent}"
        if parent not in acts:
            err(f"{where}: unknown parent activity")
        elif ref_block.get("parent_item") != acts[parent].get("served_ref"):
            err(f"{where}: parent_item {ref_block.get('parent_item')} != {acts[parent].get('served_ref')}")
        local = {r["id"]: r for r in ref_block.get("activities", [])}
        for rid, r in local.items():
            if not r.get("owner"):
                err(f"{where}/{rid}: no owner")
            if not (r.get("acceptance") or "").strip():
                err(f"{where}/{rid}: no acceptance path")
            for dep in r.get("depends", []):
                if dep not in local:
                    err(f"{where}/{rid}: depends on unknown activity {dep}")
            claim_ref(r.get("served_item"), f"{where}/{rid}")
        cycle = _find_cycle({rid: list(r.get("depends", [])) for rid, r in local.items()})
        if cycle:
            err(f"{where}: dependency cycle: " + " -> ".join(cycle))

    for prog in trace.get("programmes", []):
        for pid, ref in prog.get("activities", {}).items():
            claim_ref(ref, f"programme {prog.get('id')}/{pid}")

    if markdown is not None:
        _check_markdown(markdown, requirements, acts, rep)
    return rep


def _check_markdown(markdown: str, requirements: list, acts: dict[str, dict], rep: Report) -> None:
    md_reqs: list[tuple[str, str]] = []
    md_served: dict[str, str] = {}
    current = None
    for line in markdown.splitlines():
        if m := MD_REQUIREMENT_RE.match(line):
            md_reqs.append((m.group(1), m.group(2)))
        elif m := MD_ACTIVITY_RE.match(line):
            current = m.group(1)
        elif current and (m := MD_SERVED_RE.match(line)):
            md_served[current] = m.group(1)
    if sorted(md_reqs) != sorted(tuple(r) for r in requirements):
        rep.errors.append(f"markdown requirements {sorted(md_reqs)} differ from trace")
    for aid in sorted(set(md_served) | set(acts)):
        md_ref, js_ref = md_served.get(aid), acts.get(aid, {}).get("served_ref")
        if md_ref != js_ref:
            rep.errors.append(f"activity {aid}: markdown served item {md_ref} != trace {js_ref}")


def impact(trace: dict, goals: list[str], dependents: bool = True) -> dict:
    unknown = [g for g in goals if g not in trace.get("goals", [])]
    if unknown:
        raise ValueError(f"unknown goal(s): {', '.join(unknown)}")
    acts = _activities(trace)
    wanted = set(goals)
    direct = sorted(a for a, v in acts.items() if v.get("goal") in wanted)

    dependants: dict[str, set[str]] = {a: set() for a in acts}
    for aid, a in acts.items():
        for dep in a.get("depends_on", []):
            dependants.setdefault(dep, set()).add(aid)
    downstream: set[str] = set()
    frontier = list(direct) if dependents else []
    while frontier:
        for nxt in dependants.get(frontier.pop(), ()):
            if nxt not in downstream and nxt not in direct:
                downstream.add(nxt)
                frontier.append(nxt)

    affected = set(direct) | downstream
    features = sorted({acts[a]["feature"] for a in direct})
    obstacles = sorted(
        o["id"] for o in _obstacles(trace)
        if wanted & set(o["goals"]) or set(direct) & set(o["activities"])
    )
    refinements = []
    items = {acts[a]["served_ref"]: a for a in sorted(affected)}
    for block in trace.get("refinements", []):
        if block.get("parent") in affected:
            subs = [r["id"] for r in block.get("activities", [])]
            refinements.append({"parent": block["parent"], "activities": subs})
            for r in block.get("activities", []):
                items[r["served_item"]] = r["id"]
    return {
        "goals": sorted(wanted),
        "requirements": sorted(r for r, g in trace.get("requirements", []) if g in wanted),
        "features": [{"id": f, "title": trace["features"][f][0]} for f in features],
        "obstacles": obstacles,
        "activities": [{"id": a, "owner": acts[a]["owner"], "relation": "goal"} for a in direct]
        + [{"id": a, "owner": acts[a]["owner"], "relation": "dependent"} for a in sorted(downstream)],
        "refinements": refinements,
        "items": [{"ref": ref, "activity": aid} for ref, aid in sorted(items.items())],
    }


def tracker_refs(trace: dict) -> list[dict]:
    """Every tracker reference in the trace, with the activity ID it should name."""
    refs = []
    for a in trace.get("activities", []):
        refs.append({"ref": a["served_ref"], "activity": a["id"], "reused": bool(a.get("existing_item"))})
    for block in trace.get("refinements", []):
        for r in block.get("activities", []):
            refs.append({"ref": r["served_item"], "activity": r["id"], "reused": False})
    for prog in trace.get("programmes", []):
        for pid, ref in prog.get("activities", {}).items():
            refs.append({"ref": ref, "activity": pid, "reused": False})
    return refs


Runner = Callable[[list[str], str], "subprocess.CompletedProcess[str]"]


def _default_runner(argv: list[str], cwd: str) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60)


def reconcile(trace: dict, sprintctl: str = "sprintctl", runner: Runner = _default_runner) -> list[dict]:
    results = []
    with tempfile.TemporaryDirectory(prefix="kaos-trace-") as cwd:
        for entry in tracker_refs(trace):
            m = REF_RE.match(entry["ref"] or "")
            row = dict(entry)
            if not m:
                results.append({**row, "result": "malformed"})
                continue
            repo, num = m.group("repo"), int(m.group("id"))
            argv = [sprintctl, "--repo-id", repo, "--allow-markerless-nonlocal",
                    "item", "show", "--id", str(num), "--json"]
            try:
                proc = runner(argv, cwd)
            except (OSError, subprocess.TimeoutExpired) as exc:
                results.append({**row, "result": "error", "detail": str(exc)})
                continue
            if proc.returncode != 0:
                text = (proc.stderr or proc.stdout or "").strip()
                kind = "missing" if "not-found" in text or "not found" in text else "error"
                results.append({**row, "result": kind, "detail": text.splitlines()[0] if text else ""})
                continue
            try:
                item = json.loads(proc.stdout)["item"]
            except (ValueError, KeyError, TypeError) as exc:
                results.append({**row, "result": "error", "detail": f"unparseable output: {exc}"})
                continue
            row.update(status=item.get("status"), title=item.get("title"))
            if item.get("repo_id") != repo or item.get("id") != num:
                row.update(result="mismatch", detail=f"served returned {item.get('repo_id')}#{item.get('id')}")
            elif not entry["reused"] and not _names(item, entry["activity"]):
                row.update(result="mismatch", detail=f"item does not name {entry['activity']}")
            else:
                row["result"] = "ok"
            results.append(row)
    return results


def _names(item: dict, activity: str) -> bool:
    pattern = re.compile(rf"(?<![A-Z0-9-]){re.escape(activity)}(?![0-9])")
    return bool(pattern.search(item.get("title") or "") or pattern.search(item.get("description") or ""))


def _emit(payload, as_json: bool, text: str) -> None:
    print(json.dumps(payload, indent=2) if as_json else text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--trace", type=Path, default=DEFAULT_TRACE, help="trace JSON (default: KAOS 2028 roadmap)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="completeness and consistency of the trace")
    c.add_argument("--markdown", type=Path, help="roadmap Markdown (default: trace path with .md)")
    c.add_argument("--json", action="store_true")
    i = sub.add_parser("impact", help="features, activities and items affected by a goal change")
    i.add_argument("--goal", action="append", required=True)
    i.add_argument("--no-dependents", action="store_true", help="omit activities that only depend on the goal's")
    i.add_argument("--json", action="store_true")
    r = sub.add_parser("reconcile", help="read-only comparison against live served sprintctl")
    r.add_argument("--sprintctl", default="sprintctl")
    r.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    trace = load_trace(args.trace)
    if args.cmd == "check":
        md_path = args.markdown or args.trace.with_suffix(".md")
        markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else None
        rep = check_trace(trace, markdown)
        lines = [f"error: {e}" for e in rep.errors] + [f"warning: {w}" for w in rep.warnings]
        lines.append(f"{'FAIL' if rep.errors else 'OK'}: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
        _emit(rep.as_dict(), args.json, "\n".join(lines))
        return 1 if rep.errors else 0
    if args.cmd == "impact":
        try:
            result = impact(trace, args.goal, dependents=not args.no_dependents)
        except ValueError as exc:
            print(f"kaos_trace: {exc}", file=sys.stderr)
            return 2
        text = "\n".join([
            "goals: " + " ".join(result["goals"]),
            "requirements: " + " ".join(result["requirements"]),
            "features: " + ", ".join(f"{f['id']} {f['title']}" for f in result["features"]),
            "obstacles: " + " ".join(result["obstacles"]),
            "activities:",
            *(f"  {a['id']} ({a['owner']}, {a['relation']})" for a in result["activities"]),
            "items:",
            *(f"  {it['ref']}  {it['activity']}" for it in result["items"]),
        ])
        _emit(result, args.json, text)
        return 0
    results = reconcile(trace, args.sprintctl)
    bad = [r for r in results if r["result"] != "ok"]
    text = "\n".join(
        [f"{r['result']:9} {r['ref']:24} {r['activity']:7} {r.get('status') or ''} {r.get('detail', '')}".rstrip()
         for r in results]
        + [f"{'FAIL' if bad else 'OK'}: {len(results) - len(bad)}/{len(results)} references reconcile"]
    )
    _emit({"ok": not bad, "results": results}, args.json, text)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
