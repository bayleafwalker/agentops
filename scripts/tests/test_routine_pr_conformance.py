"""Oracle for routine_pr_conformance.py and vuoro_run_records.py (agentops#2521, M1-1).

The acceptance language: a Routine PR whose ``Vuoro-Run`` trailer resolves to a
run with a complete RunManifest and >= 1 evidence item passes; a PR without the
trailer fails. The other cases pin each failure the item names (run missing,
null manifest field, no evidence) and the input-error exit code.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


conf = _load("routine_pr_conformance_subject", SCRIPTS / "routine_pr_conformance.py")
import vuoro_run_records as vrr  # noqa: E402  (the module the script itself imports)

RUN = "run_01M3F0Z8Q4V7XK2D9R5T6Y8W1C"
OTHER = "run_01M3F0Z8Q4V7XK2D9R5T6Y8W2D"


def _run(run_id=RUN, **overrides):
    row = {
        "run_id": run_id,
        "repo_id": "kotona",
        "principal_id": "prn_1",
        "workspace_id": "01M3ABJS1QW0Q6BNDCHP0DDTYF",
        "client_id": "claude-connector",
        "grant_id": "grt_1",
        "idempotency_key": "routine.e1-review.20260927T11",
        "harness_id": "claude-code",
        "harness_build": "2.3.4",
        "model_id": "claude-opus-5-5",
        "recipe_id": "bayleafwalker/vuoro:docs/routines/e1-review.md@abc123",
        "observed_profile": {"instruction_digest": "sha256:" + "a" * 64, "skill_digests": []},
        "created_at": "2026-09-27T11:00:05Z",
        "evidence": [{"item_id": "ev1", "chain_seq": 0, "kind": "finding",
                      "ref": "docs/evidence/x.md#F1", "digest": "sha256:" + "b" * 64,
                      "collector": "e1-review", "created_at": "2026-09-27T11:01:00Z"}],
        "session_notes": [{"note_id": 1, "note": "done", "created_at": "2026-09-27T11:05:00Z"}],
    }
    row.update(overrides)
    return row


def _pr(body):
    return {"number": 140, "url": "https://github.com/bayleafwalker/vuoro/pull/140", "body": body}


def _runs(*rows):
    return vrr.parse_records({"runs": list(rows)})


def test_conformant_pr_passes():
    verdict = conf.check_pr(_pr(f"Verdict: yes\n\nVuoro-Run: {RUN}\n"), _runs(_run()))
    assert verdict["conformant"], verdict["failures"]
    assert verdict["runs"][0]["evidence"] == 1


def test_pr_without_trailer_fails():
    verdict = conf.check_pr(_pr("Verdict: yes, no trailer here"), _runs(_run()))
    assert not verdict["conformant"]
    assert verdict["failures"] == ["no Vuoro-Run trailer in the PR body"]


def test_run_missing_fails():
    verdict = conf.check_pr(_pr(f"Vuoro-Run: {OTHER}"), _runs(_run()))
    assert not verdict["conformant"]
    assert "run not found" in verdict["failures"][0]


@pytest.mark.parametrize(
    "field,value,gap",
    [
        ("harness_build", None, "harness_build"),
        ("model_id", "", "model_id"),
        ("recipe_id", "   ", "recipe_id"),
        ("observed_profile", None, "observed_profile.instruction_digest"),
        ("observed_profile", {"skill_digests": []}, "observed_profile.instruction_digest"),
    ],
)
def test_null_manifest_field_fails(field, value, gap):
    verdict = conf.check_pr(_pr(f"Vuoro-Run: {RUN}"), _runs(_run(**{field: value})))
    assert not verdict["conformant"]
    assert gap in verdict["failures"][0]


def test_no_evidence_fails():
    verdict = conf.check_pr(_pr(f"Vuoro-Run: {RUN}"), _runs(_run(evidence=[])))
    assert not verdict["conformant"]
    assert verdict["failures"] == [f"{RUN}: run has no evidence"]


def test_malformed_trailer_value_is_reported_not_ignored():
    verdict = conf.check_pr(_pr("Vuoro-Run: <run_id>"), _runs(_run()))
    assert not verdict["conformant"]
    assert "not a run_<ULID> handle" in verdict["failures"][0]


def test_every_trailer_must_pass():
    body = f"Vuoro-Run: {RUN}\nVuoro-Run: {OTHER}\n"
    verdict = conf.check_pr(_pr(body), _runs(_run()))
    assert not verdict["conformant"]
    assert len(verdict["runs"]) == 2


def test_trailer_tolerates_markdown_decoration():
    assert vrr.trailer_run_ids(f"> Vuoro-Run: `{RUN}`  ") == [RUN]
    assert vrr.trailer_run_ids(f"Vuoro-Run: {RUN}\nVuoro-Run: {RUN}") == [RUN]
    assert vrr.trailer_run_ids("mentions Vuoro-Run: inline only") == []


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_exit_codes(tmp_path, capsys):
    records = _write(tmp_path, "records.json", {"runs": [_run()]})
    good = _write(tmp_path, "good.json", _pr(f"Vuoro-Run: {RUN}"))
    bad = _write(tmp_path, "bad.json", _pr("no trailer"))
    assert conf.main(["140", "--pr-json", str(good), "--records", str(records)]) == 0
    assert "CONFORMANT" in capsys.readouterr().out
    assert conf.main(["140", "--pr-json", str(bad), "--records", str(records)]) == 1
    assert "no Vuoro-Run trailer" in capsys.readouterr().out
    broken = _write(tmp_path, "broken.json", {"not_runs": []})
    assert conf.main(["140", "--pr-json", str(good), "--records", str(broken)]) == 2


def test_records_cmd_receives_the_export_sql(tmp_path):
    export = tmp_path / "export.json"
    export.write_text(json.dumps({"runs": [_run()]}), encoding="utf-8")
    sink = tmp_path / "stdin.sql"
    cmd = f"sh -c 'cat > {sink}; cat {export}'"
    runs = vrr.load_records(records_cmd=cmd, since="2026-09-27")
    assert RUN in runs
    sql = sink.read_text(encoding="utf-8")
    assert "FROM run" in sql and "run.created_at >= '2026-09-27'::timestamptz" in sql


def test_export_sql_rejects_injection():
    with pytest.raises(ValueError):
        vrr.export_sql("2026-09-27'; drop table run; --")


def test_file_evidence_and_digest_helpers():
    record = _runs(_run(evidence=[
        {"item_id": "a", "ref": "docs/evidence/x.md", "digest": "SHA256:" + "C" * 64},
        {"item_id": "b", "ref": "docs/evidence/x.md#F1", "digest": "sha256:" + "d" * 64},
        {"item_id": "c", "ref": "https://example.com/x", "digest": "e" * 64},
        {"item_id": "d", "ref": "github:owner/repo/x", "digest": "e" * 64},
    ]))[RUN]
    assert [i["item_id"] for i in vrr.file_evidence(record)] == ["a"]
    assert vrr.normalize_digest("SHA256:" + "C" * 64) == "c" * 64
    assert vrr.normalize_digest("md5:abc") is None


def test_crlf_body_is_conformant():
    verdict = conf.check_pr(_pr(f"Verdict: yes\r\n\r\nVuoro-Run: {RUN}\r\n"), _runs(_run()))
    assert verdict["conformant"], verdict["failures"]


def test_unavailable_trailer_reports_its_reason():
    verdict = conf.check_pr(_pr("Vuoro-Run: unavailable (tools not listed)"), _runs(_run()))
    assert not verdict["conformant"]
    assert verdict["failures"] == [
        "unavailable (tools not listed): the Routine reported its run unavailable: tools not listed"
    ]
