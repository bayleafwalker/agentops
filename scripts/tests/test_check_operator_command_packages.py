"""Operator command packages: schema plus the ready/blocked rules."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = _load("check_operator_command_packages_subject",
                SCRIPTS / "check_operator_command_packages.py")
SCHEMA = json.loads((ROOT / "schemas" / "operator-command-package.v1.schema.json").read_text())

READY = {
    "schema": "operator-command-package/v1",
    "package_id": "example-ready",
    "title": "Example",
    "gate_kind": "promotion",
    "programmes": ["docs/dispatch/programmes/2026-10-24/03-cloud-product.md"],
    "work_refs": ["vuoro-cloud#1"],
    "owner": "coordinator",
    "readiness": "ready",
    "why_operator": "hardware key",
    "directory": "/projects/dev/example",
    "preconditions": [{"check": "c", "command": "true", "expected": "exit 0",
                       "verified_at": "2026-11-07T09:00Z"}],
    "commands": [{"step": 1, "command": "true", "expected": "exit 0", "exact": True}],
    "expected_result": "done",
    "send_back": ["output"],
    "rollback": {"description": "nothing to undo", "commands": []},
    "created": "2026-11-07",
    "last_verified": "2026-11-07",
}


def test_committed_packages_pass():
    results = checker.check_directory(checker.DEFAULT_DIR)
    assert results, "expected committed packages"
    assert {k: v for k, v in results.items() if v} == {}


def test_ready_package_passes():
    assert checker.check_package(copy.deepcopy(READY), SCHEMA) == []


def test_ready_with_unverified_precondition_fails():
    doc = copy.deepcopy(READY)
    doc["preconditions"][0]["verified_at"] = None
    assert any("unverified" in e for e in checker.check_package(doc, SCHEMA))


def test_ready_with_template_command_fails():
    doc = copy.deepcopy(READY)
    doc["commands"][0]["exact"] = False
    assert any("not exact" in e for e in checker.check_package(doc, SCHEMA))


def test_blocked_needs_a_blocker():
    doc = copy.deepcopy(READY)
    doc["readiness"] = "blocked"
    assert any("no blocker" in e for e in checker.check_package(doc, SCHEMA))


def test_operator_is_not_a_resolver():
    doc = copy.deepcopy(READY)
    doc["readiness"] = "blocked"
    doc["blockers"] = [{"description": "x", "resolved_by": "the operator"}]
    assert any("only 'operator'" in e for e in checker.check_package(doc, SCHEMA))


def test_missing_required_field_fails_schema():
    doc = copy.deepcopy(READY)
    del doc["send_back"]
    assert checker.check_package(doc, SCHEMA)


def test_unlisted_package_fails(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(READY))
    (tmp_path / "README.md").write_text("no links here\n")
    results = checker.check_directory(tmp_path)
    assert results["a.json"] == ["not linked from README.md"]
    (tmp_path / "README.md").write_text("[a](a.json)\n")
    assert checker.check_directory(tmp_path)["a.json"] == []


def test_cli_exit_codes(tmp_path, capsys):
    assert checker.main([]) == 0
    bad = copy.deepcopy(READY)
    bad["readiness"] = "blocked"
    (tmp_path / "b.json").write_text(json.dumps(bad))
    (tmp_path / "README.md").write_text("[b](b.json)\n")
    assert checker.main(["--dir", str(tmp_path)]) == 1
