"""Synthetic schema fault cases; these are not vendor compatibility evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).parents[1] / "validate_client_compatibility.py"
spec = importlib.util.spec_from_file_location("client_compatibility", SCRIPT)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def matrix():
    return {"schema": "client-compatibility/v1", "as_of": "2026-10-10T06:30:00Z",
            "endpoint": "https://api.vuoro.cloud/mcp", "clients": [
                {"surface": surface, "mode": mode, "version": None,
                 "stages": {stage: {"status": "untested", "reason": "not-observed", "receipt": None}
                            for stage in sorted(lab.STAGES)}} for surface, modes in lab.SURFACES.items() for mode in sorted(modes)]}


def observed(tmp_path, **changes):
    value = matrix()
    client = value["clients"][4]
    row = {"schema": "client-observation/v1", "kind": "client_trace", "surface": client["surface"],
           "mode": client["mode"], "version": None, "stage": "call", "observed_at": "2026-10-10T06:29:00Z",
           "endpoint": value["endpoint"], "outcome": "refused", "tools": [], "tool": "describe_work",
           "request_sha256": "a" * 64, "response_sha256": "b" * 64, "error_code": "item-not-found",
           "auth_method": None, "workspace_id": None, "repo_id": None, "consent_scopes": []}
    row.update(changes)
    blob = json.dumps(row).encode()
    (tmp_path / "receipt.json").write_bytes(blob)
    client["stages"]["call"] = {"status": "refused", "reason": "item-not-found",
                                 "receipt": {"path": "receipt.json", "sha256": hashlib.sha256(blob).hexdigest()}}
    return value


def test_unknown_matrix_is_valid_but_qualifies_no_client_stage(tmp_path):
    report = lab.validate(matrix(), tmp_path)
    assert all(not c["observations"] and len(c["unknown_stages"]) == 5 for c in report["clients"])
    assert report["writes"] is False


def test_actual_refusal_preserved_without_claiming_success_or_known_version(tmp_path):
    report = lab.validate(observed(tmp_path), tmp_path)
    assert report["clients"][4]["observations"] == [{"stage": "call", "outcome": "refused", "version_known": False,
                                                    "unknown_bindings": ["auth_method", "workspace_id", "repo_id"]}]


@pytest.mark.parametrize("kind", ["configuration", "connection_health", "protocol_conformance"])
def test_nonclient_evidence_cannot_fill_product_gap(tmp_path, kind):
    with pytest.raises(ValueError, match="cannot qualify"):
        lab.validate(observed(tmp_path, kind=kind), tmp_path)


@pytest.mark.parametrize("changes", [
    {"surface": "chatgpt_ui", "mode": "ui_oauth"},
    {"mode": "local_cli"}, {"version": "0.162.1"},
    {"endpoint": "https://other.invalid/mcp"}, {"stage": "refresh"},
    {"outcome": "pass", "error_code": None},
    {"observed_at": "2026-10-11T00:00:00Z"}, {"observed_at": "2026-10-10T06:00:00"},
    {"request_sha256": None}, {"response_sha256": "invalid"},
    {"tool": None}, {"error_code": None}, {"tools": ["x", "x"]},
    {"Authorization": "Bearer synthetic-never-print"},
])
def test_binding_and_redaction_faults_refused(tmp_path, changes):
    with pytest.raises(ValueError):
        lab.validate(observed(tmp_path, **changes), tmp_path)


def test_changed_receipt_bytes_refused(tmp_path):
    value = observed(tmp_path)
    (tmp_path / "receipt.json").write_text("{}")
    with pytest.raises(ValueError, match="digest changed"):
        lab.validate(value, tmp_path)


def test_receipt_digest_and_parse_use_same_single_read(tmp_path, monkeypatch):
    value = observed(tmp_path)
    read = Path.read_bytes
    calls = []
    def changing_read(path):
        calls.append(path)
        return read(path) if len(calls) == 1 else b'{}'
    monkeypatch.setattr(Path, "read_bytes", changing_read)
    assert lab.validate(value, tmp_path)["valid"]
    assert len(calls) == 1


@pytest.mark.parametrize("path", ["../receipt.json", "/tmp/receipt.json"])
def test_external_path_refused(tmp_path, path):
    value = observed(tmp_path)
    value["clients"][4]["stages"]["call"]["receipt"]["path"] = path
    with pytest.raises(ValueError, match="relative"):
        lab.validate(value, tmp_path)


def test_symlink_escape_refused(tmp_path):
    value = observed(tmp_path)
    (tmp_path / "receipt.json").unlink()
    (tmp_path / "receipt.json").symlink_to(tmp_path.parent / "outside.json")
    with pytest.raises(ValueError, match="escapes"):
        lab.validate(value, tmp_path)


def test_missing_surface_refused(tmp_path):
    value = matrix()
    value["clients"].pop()
    with pytest.raises(ValueError, match="every product"):
        lab.validate(value, tmp_path)


def test_duplicate_surface_refused(tmp_path):
    value = matrix()
    value["clients"].append(copy.deepcopy(value["clients"][0]))
    with pytest.raises(ValueError, match="duplicate surface"):
        lab.validate(value, tmp_path)


def test_successful_discovery_needs_visible_tools(tmp_path):
    value = observed(tmp_path, stage="discover", outcome="pass", error_code=None, tool=None)
    client = value["clients"][4]
    client["stages"]["discover"] = client["stages"]["call"]
    client["stages"]["discover"]["status"] = "pass"
    client["stages"]["call"] = matrix()["clients"][4]["stages"]["call"]
    with pytest.raises(ValueError, match="visible tools"):
        lab.validate(value, tmp_path)


def test_cli_leaves_inputs_unchanged_and_never_echoes_rejected_secret(tmp_path):
    value = observed(tmp_path, Authorization="Bearer synthetic-never-print")
    p = tmp_path / "matrix.json"
    p.write_text(json.dumps(value))
    before = {x.name: x.read_bytes() for x in tmp_path.iterdir()}
    result = subprocess.run([sys.executable, str(SCRIPT), str(p), "--evidence-root", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 2 and result.stdout == ""
    assert result.stderr == "invalid client compatibility evidence\n"
    assert before == {x.name: x.read_bytes() for x in tmp_path.iterdir()}


def test_duplicate_json_fields_refused_without_output(tmp_path):
    p = tmp_path / "matrix.json"
    p.write_text('{"schema":"secret","schema":"client-compatibility/v1"}')
    result = subprocess.run([sys.executable, str(SCRIPT), str(p), "--evidence-root", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 2 and result.stdout == "" and "secret" not in result.stderr
