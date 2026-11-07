"""Plan register: scope, vocabulary, derived-status justification, staleness."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("plan_register_subject", ROOT / "scripts" / "plan_register.py")
reg = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(reg)


def _repo(tmp_path: Path) -> Path:
    plans = tmp_path / "docs" / "plans"
    (plans / "agentops").mkdir(parents=True)
    (tmp_path / "docs" / "dispatch" / "programmes" / "2026-10-24").mkdir(parents=True)
    (plans / "a.md").write_text("# A\n\nStatus: accepted 2026-10-20.\n")
    (plans / "agentops" / "b.md").write_text("---\nstatus: superseded\nsuperseded_by: a.md\n---\n# B\n")
    (plans / "c.md").write_text("# C\n\nno status line here\n")
    (tmp_path / "docs" / "dispatch" / "programmes" / "2026-10-24" / "p.md").write_text("# P\n")
    return tmp_path


def _data(**overrides):
    rows = {
        "docs/plans/a.md": {"status": "accepted", "owner": "agentops", "last_verified": "2026-11-07"},
        "docs/plans/agentops/b.md": {"status": "superseded", "owner": "agentops", "successor": "a.md", "last_verified": "2026-11-07"},
        "docs/plans/c.md": {"status": "reference", "owner": "agentops", "last_verified": "2026-11-07", "justification": "notes"},
        "docs/dispatch/programmes/2026-10-24/p.md": {"status": "active", "owner": "coordinator", "last_verified": "2026-11-07", "justification": "programme"},
    }
    rows.update(overrides)
    return rows


def test_normalise_maps_ad_hoc_strings():
    cases = {
        "accepted 2026-10-20": "accepted", "ratified": "accepted", "RULED AND EXECUTED 2026-08-26": "accepted",
        "approved-experiment-plan": "accepted", "planning proposal; no implementation": "proposed",
        "draft": "proposed", "analysis and recommendation. NOT a ruling.": "proposed",
        "partially_superseded": "superseded", "source-material": "reference", "current-observation": "reference",
        "active-plan-packet-freeze": "active", "implementation started": "active", "rejected": "rejected",
        "proposal (nothing here is adopted)": "proposed",
    }
    for raw, expected in cases.items():
        assert reg.normalise(raw) == expected, raw


def test_clean_register_passes(tmp_path):
    root = _repo(tmp_path)
    (root / reg.DATA).write_text(json.dumps(_data()))
    (root / reg.OUTPUT).write_text(reg.render(root, reg.load(root)))
    assert reg.main(["--root", str(root)]) == 0


def test_missing_plan_file_fails(tmp_path, capsys):
    root = _repo(tmp_path)
    data = _data()
    del data["docs/plans/c.md"]
    (root / reg.DATA).write_text(json.dumps(data))
    (root / reg.OUTPUT).write_text(reg.render(root, data))
    assert reg.main(["--root", str(root)]) == 1
    assert "docs/plans/c.md: plan file missing" in capsys.readouterr().out


def test_derived_status_needs_justification(tmp_path):
    root = _repo(tmp_path)
    data = _data(**{"docs/plans/c.md": {"status": "reference", "owner": "x", "last_verified": "2026-11-07"}})
    assert any("justification is required" in e for e in reg.validate(root, data))
    data = _data(**{"docs/plans/a.md": {"status": "archived", "owner": "x", "last_verified": "2026-11-07"}})
    assert any("docs/plans/a.md" in e and "justification" in e for e in reg.validate(root, data))


def test_vocabulary_successor_and_placeholders(tmp_path):
    root = _repo(tmp_path)
    data = _data(**{"docs/plans/a.md": {"status": "adopted", "owner": "x", "last_verified": "2026-11-07"}})
    assert any("not in the vocabulary" in e for e in reg.validate(root, data))
    data = _data(**{"docs/plans/agentops/b.md": {"status": "superseded", "owner": "x", "last_verified": "2026-11-07"}})
    assert any("needs a successor" in e for e in reg.validate(root, data))
    data = _data(**{"docs/plans/c.md": {"status": "reference", "owner": "x", "last_verified": "2026-11-07", "justification": "TODO"}})
    assert any("placeholders" in e for e in reg.validate(root, data))


def test_stale_rendering_fails(tmp_path, capsys):
    root = _repo(tmp_path)
    (root / reg.DATA).write_text(json.dumps(_data()))
    (root / reg.OUTPUT).write_text("old\n")
    assert reg.main(["--root", str(root)]) == 1
    assert "stale" in capsys.readouterr().out


def test_vanished_file_fails(tmp_path):
    root = _repo(tmp_path)
    data = _data(**{"docs/plans/gone.md": {"status": "reference", "owner": "x", "last_verified": "2026-11-07", "justification": "j"}})
    assert any("does not exist" in e for e in reg.validate(root, data))


def test_committed_register_is_current():
    assert reg.validate(ROOT, reg.load(ROOT)) == []
    assert (ROOT / reg.OUTPUT).read_text() == reg.render(ROOT, reg.load(ROOT))


def test_status_line_is_anchored():
    assert reg.STATUS_LINE.search("the job status: running") is None
    assert reg.STATUS_LINE.search("- **Status:** accepted").group(1).startswith("accepted")
    assert reg.STATUS_LINE.search("Date: 2026-09-27. Status: decided").group(1) == "decided"
    assert reg.normalise("not implemented yet") is None
    assert reg.normalise("recurrent") is None


def test_add_missing_appends_derived_rows(tmp_path):
    root = _repo(tmp_path)
    (root / reg.DATA).write_text(json.dumps({}))
    assert reg.main(["--root", str(root), "--add-missing"]) == 0
    data = json.loads((root / reg.DATA).read_text())
    assert set(data) == set(reg.plan_files(root))
    assert data["docs/plans/c.md"]["justification"]
    assert data["docs/plans/agentops/b.md"]["status"] == "superseded"
    assert (root / reg.OUTPUT).read_text() == reg.render(root, data)
