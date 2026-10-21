"""kaos_trace must discriminate: each violation is paired with the clean fixture passing."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

try:
    import pytest
except ImportError as exc:  # pragma: no cover - depends on the host interpreter
    import unittest

    raise unittest.SkipTest(f"pytest-style module needs pytest: {exc}") from exc

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "kaos_trace.py"
_spec = importlib.util.spec_from_file_location("kaos_trace", SCRIPT)
kt = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["kaos_trace"] = kt  # dataclasses resolve string annotations through sys.modules
_spec.loader.exec_module(kt)


def _act(aid, goal, feature, ref, deps=(), existing=None, owner="agentops"):
    return {
        "id": aid, "owner": owner, "goal": goal, "feature": feature, "sourcing": "build",
        "baseline": "gap", "activities": "work", "acceptance": "observable predicate",
        "depends_on": list(deps), "existing_item": existing, "served_ref": ref,
    }


def _trace():
    return {
        "kind": kt.TRACE_KIND,
        "version": 1,
        "goals": ["G01", "G02"],
        "requirements": [["R01", "G01"], ["R02", "G02"]],
        "features": {"F01": ["Purpose", "Why?"], "F02": ["Estate", "What?"]},
        "obstacles": [["O01", "G01", "Busywork", "AA-K01"], ["O02", "G02", "Stale", "BB-K01"]],
        "activities": [
            _act("AA-K01", "G01", "F01", "agentops#10"),
            _act("BB-K01", "G02", "F02", "vuoro#11", deps=["AA-K01"]),
            _act("CC-K01", "G02", "F02", "vuoro#12", deps=["BB-K01"], existing="vuoro#12"),
        ],
        "refinements": [{
            "parent": "BB-K01", "parent_item": "vuoro#11", "document": "x.md",
            "activities": [
                {"id": "OA-01", "owner": "vuoro", "title": "t", "depends": [], "work": "w",
                 "acceptance": "a", "served_item": "vuoro#20"},
                {"id": "OA-02", "owner": "agentops", "title": "t", "depends": ["OA-01"], "work": "w",
                 "acceptance": "a", "served_item": "agentops#21"},
            ],
        }],
        "programmes": [{"id": "EC", "activities": {"EC-01": "agentops#30"}}],
    }


def test_clean_fixture_passes():
    rep = kt.check_trace(_trace())
    assert rep.errors == []
    assert rep.warnings == ["activity CC-K01: no obstacle names it directly (inherits goal G02 obstacles)"]


def test_committed_trace_passes_with_markdown():
    trace = kt.load_trace(kt.DEFAULT_TRACE)
    rep = kt.check_trace(trace, kt.DEFAULT_TRACE.with_suffix(".md").read_text(encoding="utf-8"))
    assert rep.errors == []
    assert len(trace["activities"]) == 46


def _mutated(fn):
    t = _trace()
    fn(t)
    return kt.check_trace(t).errors


@pytest.mark.parametrize("mutate, expected", [
    (lambda t: t["obstacles"].pop(), "requirement R02 (G02): no obstacle"),
    (lambda t: t["activities"][0].update(owner=""), "activity AA-K01: no owner"),
    (lambda t: t["activities"][0].update(acceptance=" "), "activity AA-K01: no acceptance path"),
    (lambda t: t["activities"][0].update(feature="F99"), "activity AA-K01: unknown feature 'F99'"),
    (lambda t: t["activities"].pop(0), "requirement R01 (G01): no activity"),
    (lambda t: t["requirements"].pop(), "goal G02: no leaf requirement"),
    (lambda t: t["activities"][0].update(depends_on=["CC-K01"]),
     "dependency cycle: AA-K01 -> CC-K01 -> BB-K01 -> AA-K01"),
    (lambda t: t["activities"][1].update(depends_on=["ZZ-K09"]), "activity BB-K01: depends on unknown activity ZZ-K09"),
    (lambda t: t["activities"][1].update(served_ref="agentops#10"),
     "activity BB-K01: tracker reference agentops#10 already bound to activity AA-K01"),
    (lambda t: t["activities"][1].update(served_ref="vuoro-11"), "activity BB-K01: malformed tracker reference 'vuoro-11'"),
    (lambda t: t["activities"][2].update(existing_item="vuoro#99"),
     "activity CC-K01: existing_item vuoro#99 differs from served_ref vuoro#12"),
    (lambda t: t["activities"][0].update(status="done"),
     "work-state field activities[0].status: status belongs to served sprintctl, not the trace"),
    (lambda t: t.update(kind="work-ledger"), "kind is 'work-ledger', expected 'requirements-trace-not-work-state'"),
    (lambda t: t["obstacles"][0].__setitem__(3, "AA-K01 QQ-K01"), "obstacle O01: unknown activity QQ-K01"),
    (lambda t: t["refinements"][0].update(parent_item="vuoro#99"),
     "refinement of BB-K01: parent_item vuoro#99 != vuoro#11"),
    (lambda t: t["refinements"][0]["activities"][0].update(depends=["OA-02"]),
     "refinement of BB-K01: dependency cycle: OA-01 -> OA-02 -> OA-01"),
    (lambda t: t["programmes"][0]["activities"].update({"EC-02": "vuoro#20"}),
     "programme EC/EC-02: tracker reference vuoro#20 already bound to refinement of BB-K01/OA-01"),
])
def test_violation_is_reported(mutate, expected):
    assert expected in _mutated(mutate)


def test_markdown_drift_is_reported():
    md = "| R01 | G01 | op | exp |\n| R02 | G02 | op | exp |\n" \
         "### AA-K01 — x\n- **Served item:** agentops#10.\n" \
         "### BB-K01 — y\n- **Served item:** vuoro#11.\n" \
         "### CC-K01 — z\n- **Served item:** vuoro#12.\n"
    assert kt.check_trace(_trace(), md).errors == []
    drifted = md.replace("vuoro#11", "vuoro#13").replace("| R02 | G02", "| R03 | G02")
    errors = kt.check_trace(_trace(), drifted).errors
    assert "activity BB-K01: markdown served item vuoro#13 != trace vuoro#11" in errors
    assert any(e.startswith("markdown requirements") for e in errors)


def test_impact_of_goal_change():
    result = kt.impact(_trace(), ["G02"])
    assert result["requirements"] == ["R02"]
    assert [f["id"] for f in result["features"]] == ["F02"]
    assert result["obstacles"] == ["O02"]
    assert [(a["id"], a["relation"]) for a in result["activities"]] == [("BB-K01", "goal"), ("CC-K01", "goal")]
    assert result["refinements"] == [{"parent": "BB-K01", "activities": ["OA-01", "OA-02"]}]
    assert {i["ref"] for i in result["items"]} == {"vuoro#11", "vuoro#12", "vuoro#20", "agentops#21"}


def test_impact_follows_dependents_transitively():
    result = kt.impact(_trace(), ["G01"])
    assert [(a["id"], a["relation"]) for a in result["activities"]] == [
        ("AA-K01", "goal"), ("BB-K01", "dependent"), ("CC-K01", "dependent")]
    assert [f["id"] for f in result["features"]] == ["F01"]
    direct = kt.impact(_trace(), ["G01"], dependents=False)
    assert [a["id"] for a in direct["activities"]] == ["AA-K01"]
    assert [i["ref"] for i in direct["items"]] == ["agentops#10"]


def test_impact_rejects_unknown_goal():
    with pytest.raises(ValueError):
        kt.impact(_trace(), ["G42"])


def _fake_served(items):
    calls = []

    def runner(argv, cwd):
        calls.append((argv, cwd))
        repo, num = argv[argv.index("--repo-id") + 1], int(argv[argv.index("--id") + 1])
        item = items.get(f"{repo}#{num}")
        if item is None:
            return subprocess.CompletedProcess(argv, 1, "", f"Error: served item show failed: item-not-found: Item #{num} not found")
        return subprocess.CompletedProcess(argv, 0, json.dumps({"item": item}), "")

    return runner, calls


def _item(repo, num, title, status="pending"):
    return {"repo_id": repo, "id": num, "title": title, "description": "", "status": status}


def test_reconcile_is_read_only_and_markerless():
    items = {
        "agentops#10": _item("agentops", 10, "[AA-K01] a"),
        "vuoro#11": _item("vuoro", 11, "[BB-K01] b"),
        "vuoro#12": _item("vuoro", 12, "legacy reused item, no activity id"),
        "vuoro#20": _item("vuoro", 20, "[OA-01] x", status="active"),
        "agentops#21": _item("agentops", 21, "[OA-02] y"),
        "agentops#30": _item("agentops", 30, "[EC-01] z"),
    }
    runner, calls = _fake_served(items)
    results = kt.reconcile(_trace(), runner=runner)
    assert all(r["result"] == "ok" for r in results), results
    assert {r["status"] for r in results} == {"pending", "active"}
    for argv, cwd in calls:
        assert argv[1:4] == ["--repo-id", argv[2], "--allow-markerless-nonlocal"]
        assert argv[4:6] == ["item", "show"]
        assert not (Path(cwd) / ".sprintctl").exists()


def test_reconcile_reports_missing_and_mismatched_items():
    items = {
        "agentops#10": _item("agentops", 10, "[AA-K02] wrong activity"),
        "vuoro#12": _item("vuoro", 12, "reused"),
        "vuoro#20": _item("sprintctl", 20, "[OA-01] wrong repo"),
        "agentops#21": _item("agentops", 21, "mentions OA-021 only"),
        "agentops#30": _item("agentops", 30, "[EC-01] z"),
    }
    runner, _ = _fake_served(items)
    by_ref = {r["ref"]: r for r in kt.reconcile(_trace(), runner=runner)}
    assert by_ref["agentops#10"]["result"] == "mismatch"
    assert by_ref["vuoro#11"]["result"] == "missing"
    assert by_ref["vuoro#12"]["result"] == "ok"
    assert by_ref["vuoro#20"]["result"] == "mismatch"
    assert by_ref["agentops#21"]["result"] == "mismatch"
    assert by_ref["agentops#30"]["result"] == "ok"


def test_cli_check_exit_status(tmp_path, capsys):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(_trace()))
    assert kt.main(["--trace", str(path), "check"]) == 0
    capsys.readouterr()
    bad = copy.deepcopy(_trace())
    bad["activities"][0]["owner"] = ""
    path.write_text(json.dumps(bad))
    assert kt.main(["--trace", str(path), "check", "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "activity AA-K01: no owner" in out["errors"]


def test_cli_impact_unknown_goal_is_usage_error(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(_trace()))
    assert kt.main(["--trace", str(path), "impact", "--goal", "G42"]) == 2
