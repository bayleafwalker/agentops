"""Every outcome closeout record (and the template) validates against its schema."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
RECORDS = ROOT / "docs" / "dispatch" / "closeouts"
SCHEMA = json.loads((ROOT / "schemas" / "outcome-closeout-record.v1.schema.json").read_text())

_spec = importlib.util.spec_from_file_location("schema_check_closeouts", ROOT / "scripts" / "schema_check.py")
schema_check = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(schema_check)


def test_records_validate():
    files = sorted(RECORDS.glob("*.json"))
    assert any(f.name == "TEMPLATE.json" for f in files)
    failures = {f.name: schema_check.validate(json.loads(f.read_text()), SCHEMA) for f in files}
    assert {k: v for k, v in failures.items() if v} == {}


def test_records_listed_in_readme():
    readme = (RECORDS / "README.md").read_text()
    for f in RECORDS.glob("*.json"):
        assert f"({f.name})" in readme, f.name


def test_measure_basis_required():
    doc = json.loads((RECORDS / "TEMPLATE.json").read_text())
    del doc["elapsed"]["basis"]
    assert schema_check.validate(doc, SCHEMA)


def test_estimate_is_not_measured():
    doc = json.loads((RECORDS / "TEMPLATE.json").read_text())
    doc["cost"]["basis"] = "guess"
    assert schema_check.validate(doc, SCHEMA)
