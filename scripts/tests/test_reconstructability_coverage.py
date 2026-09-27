"""Oracle for reconstructability_coverage.py (agentops#2523, M1-3).

The acceptance language: with one Routine deliberately skipping
``register_run``, that invocation appears under ``unknown`` (with its
scheduled time), not under ``observed``. The other cases pin retries counted
once, a wrong-grant run not observed, a digest mismatch dropped at the
resolvable stage, a session-note-only outcome, and cron expansion. Fixtures
are built by hand.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

# Imported by name, not spec_from_file_location: the script defines a dataclass,
# which needs its module registered in sys.modules.
import reconstructability_coverage as cov  # noqa: E402
import vuoro_run_records as vrr  # noqa: E402  (the module the script itself imports)

UTC = timezone.utc
SINCE = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
UNTIL = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
WINDOW = timedelta(hours=2)
REPO = "bayleafwalker/vuoro"
REPORT = "docs/evidence/2026-09-27-daily-review.md"
REPORT_TEXT = "# Daily review\n\nVerdict: nothing to fix.\n"
REPORT_DIGEST = "sha256:" + hashlib.sha256(REPORT_TEXT.encode()).hexdigest()

RUN_A = "run_01M3F0Z8Q4V7XK2D9R5T6Y8W1C"
RUN_A2 = "run_01M3F0Z8Q4V7XK2D9R5T6Y8W2D"
RUN_X = "run_01M3F0Z8Q4V7XK2D9R5T6Y8W3E"

COHORT = {
    "schema": "reconstructability-cohort/v1",
    "version": 1,
    "default_client_id": "claude-connector",
    "default_report_repo": REPO,
    "sessions_file": None,
    "routines": [
        # Fires at 06:00, registers its run, opens a PR: the good path.
        {"slug": "daily-review", "trigger_id": "trig_A", "schedule": "0 6 * * *",
         "client_id": "claude-connector", "grant_ids": ["grt_1"], "report_repo": REPO},
        # Fires at 09:00 and deliberately skips register_run: the acceptance case.
        {"slug": "skip-register", "trigger_id": None, "schedule": "0 9 * * *",
         "client_id": "claude-connector", "grant_ids": ["grt_1"], "report_repo": REPO},
    ],
}


def _run(run_id=RUN_A, key="routine.daily-review.20260927T060012Z",
         created="2026-09-27T06:00:14Z", grant="grt_1", evidence=None, notes=None, **extra):
    row = {
        "run_id": run_id, "repo_id": "kotona", "principal_id": "prn_1",
        "workspace_id": "01M3ABJS1QW0Q6BNDCHP0DDTYF", "client_id": "claude-connector",
        "grant_id": grant, "idempotency_key": key, "harness_id": "claude-code",
        "harness_build": "2.3.4", "model_id": "claude-opus-5-5",
        "recipe_id": f"{REPO}:docs/routines/daily-review.md@abc123",
        "observed_profile": {"instruction_digest": "sha256:" + "a" * 64},
        "created_at": created,
        "evidence": evidence if evidence is not None else [
            {"item_id": "ev1", "chain_seq": 0, "kind": "report", "ref": REPORT,
             "digest": REPORT_DIGEST, "collector": "daily-review"}],
        "session_notes": notes if notes is not None else [],
    }
    row.update(extra)
    return row


def _pr(run_id=RUN_A, text=REPORT_TEXT, number=140):
    return {"number": number, "url": f"https://github.com/{REPO}/pull/{number}",
            "body": f"Verdict: nothing to fix.\n\nVuoro-Run: {run_id}\n",
            "headRefOid": "deadbeef", "files": {REPORT: text}}


def _no_fetch(repo, path, ref):  # every fixture PR carries its files
    raise AssertionError("fixtures must not reach gh")


def _funnel(runs, prs=(), sessions=(), cohort=COHORT):
    invocations = cov.expected_invocations(cohort, list(sessions), SINCE, UNTIL)
    records = vrr.parse_records({"runs": list(runs)})
    return cov.funnel(invocations, records, {REPO: list(prs)}, _no_fetch, WINDOW, SINCE, UNTIL)


def _counts(result):
    return [stage["count"] for stage in result["stages"]]


def _row(result, inv_id):
    return next(r for r in result["invocations"] if r["id"] == inv_id)


# -- acceptance -------------------------------------------------------------

def test_skipped_register_run_is_unknown_not_observed():
    result = _funnel([_run()], [_pr()])
    assert _counts(result) == [2, 1, 1, 1]
    assert result["unknown"] == {
        "count": 1, "scheduled": ["2026-09-27T09:00Z skip-register@2026-09-27T09:00Z"]}
    observed_drops = result["stages"][1]["dropped"]
    assert [d["id"] for d in observed_drops] == ["skip-register@2026-09-27T09:00Z"]
    assert _row(result, "skip-register@2026-09-27T09:00Z")["reached"] == "expected"
    good = _row(result, "daily-review@2026-09-27T06:00Z")
    assert good["reached"] == "resolvable" and good["outcome"] == f"{REPO}#140"
    assert result["coverage"] == 0.5


def test_retries_count_once_per_invocation():
    retry = _run(RUN_A2, key="routine.daily-review.20260927T062500Z",
                 created="2026-09-27T06:25:02Z")
    result = _funnel([_run(), retry], [_pr()])
    assert _counts(result) == [2, 1, 1, 1]
    assert _row(result, "daily-review@2026-09-27T06:00Z")["runs"] == [RUN_A, RUN_A2]
    assert result["unexpected"] == []


def test_wrong_grant_run_is_not_observed():
    stray = _run(RUN_X, key="routine.skip-register.20260927T090005Z",
                 created="2026-09-27T09:00:07Z", grant="grt_other")
    result = _funnel([_run(), stray], [_pr()])
    assert _counts(result)[:2] == [2, 1]
    assert result["other_bindings"] == [RUN_X]
    assert result["unknown"]["count"] == 1


def test_digest_mismatch_is_dropped_at_resolvable():
    result = _funnel([_run()], [_pr(text=REPORT_TEXT + "edited after append_evidence\n")])
    assert _counts(result) == [2, 1, 1, 0]
    (drop,) = result["stages"][3]["dropped"]
    assert drop["id"] == "daily-review@2026-09-27T06:00Z"
    assert "digest mismatch" in drop["reason"]
    assert result["coverage"] == 0.0


def test_report_missing_at_pr_head_is_dropped():
    pr = _pr()
    pr["files"] = {}
    result = _funnel([_run()], [pr])
    assert "not present at the PR head" in result["stages"][3]["dropped"][0]["reason"]


def test_session_note_only_outcome_resolves_without_file_evidence():
    finding = [{"item_id": "f1", "chain_seq": 0, "kind": "finding",
                "ref": f"{REPORT}#F1", "digest": "sha256:" + "b" * 64}]
    note = [{"note_id": 7, "note": f"nothing found\nVuoro-Run: `{RUN_A}`\n"}]
    result = _funnel([_run(evidence=finding, notes=note)])
    assert _counts(result) == [2, 1, 1, 1]
    assert _row(result, "daily-review@2026-09-27T06:00Z")["outcome"] == "session-note:7"


def test_session_note_does_not_wave_through_uncheckable_file_evidence():
    note = [{"note_id": 7, "note": f"Vuoro-Run: {RUN_A}"}]
    result = _funnel([_run(notes=note)])  # report item present, but no PR to check it in
    assert _counts(result) == [2, 1, 1, 0]
    assert "no PR in" in result["stages"][3]["dropped"][0]["reason"]


def test_run_without_evidence_is_dropped_at_evidence_stage():
    result = _funnel([_run(evidence=[])], [_pr()])
    assert _counts(result) == [2, 1, 0, 0]
    assert result["stages"][2]["dropped"][0]["runs"] == [RUN_A]


def test_unavailable_trailer_does_not_resolve():
    pr = _pr()
    pr["body"] = "Vuoro-Run: unavailable (tools not listed)\n"
    result = _funnel([_run()], [pr])
    assert _counts(result)[3] == 0
    assert "no PR in" in result["stages"][3]["dropped"][0]["reason"]


# -- matching ---------------------------------------------------------------

def test_time_window_fallback_and_unexpected_runs():
    keyless = _run(key="", created="2026-09-27T06:40:00Z")
    off_schedule = _run(RUN_X, key="routine.daily-review.20260927T110000Z",
                        created="2026-09-27T11:00:01Z")
    result = _funnel([keyless, off_schedule], [_pr()])
    assert _row(result, "daily-review@2026-09-27T06:00Z")["runs"] == [RUN_A]
    (unexpected,) = result["unexpected"]
    assert unexpected["run_id"] == RUN_X and "names no expected invocation" in unexpected["reason"]


def test_overlapping_windows_without_key_are_ambiguous_not_guessed():
    cohort = dict(COHORT, routines=[dict(COHORT["routines"][0]),
                                    dict(COHORT["routines"][1], schedule="0 6 * * *")])
    result = _funnel([_run(key="")], [_pr()], cohort=cohort)
    assert result["stages"][1]["count"] == 0
    assert "ambiguous" in result["unexpected"][0]["reason"]


def test_unrelated_runs_near_a_skipped_fire_do_not_make_it_observed():
    # Review finding: runs bound to the cohort client at 09:01 whose keys are not
    # skip-register's must not be time-matched into observed.
    foreign = _run(RUN_X, key="probe.manual.0001", created="2026-09-27T09:01:00Z")
    other_slug = _run(RUN_A2, key="routine.not-in-cohort.20260927T090100Z",
                      created="2026-09-27T09:01:00Z")
    result = _funnel([_run(), foreign, other_slug], [_pr()])
    assert _counts(result) == [2, 1, 1, 1]
    assert result["unknown"]["count"] == 1
    reasons = {u["run_id"]: u["reason"] for u in result["unexpected"]}
    assert "follows no cohort convention" in reasons[RUN_X]
    assert "not in the cohort" in reasons[RUN_A2]


def test_session_id_must_be_a_whole_key_token():
    sessions = [{"session_id": "cse_01AB", "dispatched_at": "2026-09-27T10:00:00Z"}]
    run = _run(RUN_X, key="session.cse_01ABC", created="2026-09-27T10:03:00Z", grant="grt_9")
    result = _funnel([run], sessions=sessions)
    assert _row(result, "session:cse_01AB")["runs"] == []
    assert result["unexpected"][0]["run_id"] == RUN_X


def test_runs_before_since_are_ignored_and_after_until_only_count_when_matched():
    early = _run(RUN_X, key="", created="2026-09-26T23:00:00Z")
    late = _run(RUN_A2, key="probe.late.0001", created="2026-09-27T12:30:00Z")
    result = _funnel([_run(), early, late], [_pr()])
    assert result["unexpected"] == [] and result["other_bindings"] == []


def test_pr_without_head_commit_does_not_resolve():
    pr = _pr()
    del pr["files"]
    pr["headRefOid"] = ""
    result = _funnel([_run()], [pr])
    assert "no head commit" in result["stages"][3]["dropped"][0]["reason"]


def test_trailer_pr_listing_refuses_a_truncated_result(monkeypatch):
    calls = []

    def fake_gh(args, timeout=60.0):
        calls.append(args)
        return json.dumps([{"number": n} for n in range(3)])

    monkeypatch.setattr(vrr, "_gh", fake_gh)
    with pytest.raises(RuntimeError, match="hit the limit"):
        vrr.list_trailer_prs("o/r", "2026-09-27", limit=3)
    assert len(vrr.list_trailer_prs("o/r", "2026-09-27", limit=4)) == 3
    assert '"Vuoro-Run" in:body created:>=2026-09-27' in calls[-1]


def test_cohort_validation_of_once_and_unquoted_dates(tmp_path):
    bad = dict(COHORT, routines=[{"slug": "x", "once": "2026-09-27T04:30:00Z"}])
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="once must be a list"):
        cov.load_cohort(path)
    path.write_text("schema: reconstructability-cohort/v1\nroutines:\n"
                    "  - {slug: d, once: [2026-09-27], client_id: c}\n", encoding="utf-8")
    cohort = cov.load_cohort(path)
    ids = [i.inv_id for i in cov.expected_invocations(cohort, [], SINCE, UNTIL)]
    assert ids == ["d@2026-09-27T00:00Z"]


def test_dispatched_session_matches_by_session_id_in_key():
    sessions = [{"session_id": "cse_01ABC", "dispatched_at": "2026-09-27T10:00:00Z",
                 "client_id": "claude-connector"}]
    run = _run(RUN_X, key="session.cse_01ABC", created="2026-09-27T10:03:00Z",
               grant="grt_9", evidence=[], notes=[])
    result = _funnel([run], sessions=sessions)
    assert _counts(result) == [3, 1, 0, 0]
    assert _row(result, "session:cse_01ABC")["runs"] == [RUN_X]


def test_load_sessions_accepts_jsonl_and_array(tmp_path):
    rows = [{"session_id": "cse_1", "dispatched_at": "2026-09-27T01:00:00Z"}]
    jsonl = tmp_path / "s.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    array = tmp_path / "s.json"
    array.write_text(json.dumps(rows), encoding="utf-8")
    empty = tmp_path / "e.jsonl"
    empty.write_text("", encoding="utf-8")
    assert cov.load_sessions(jsonl) == rows == cov.load_sessions(array)
    assert cov.load_sessions(empty) == [] == cov.load_sessions(None)


# -- cron -------------------------------------------------------------------

def _cron(expr, start, end):
    return [cov.fmt_ts(t) for t in cov.cron_times(expr, cov.parse_ts(start), cov.parse_ts(end))]


def test_cron_expansion_steps_ranges_lists():
    assert _cron("*/20 9-10 * * *", "2026-09-27", "2026-09-28") == [
        "2026-09-27T09:00Z", "2026-09-27T09:20Z", "2026-09-27T09:40Z",
        "2026-09-27T10:00Z", "2026-09-27T10:20Z", "2026-09-27T10:40Z"]
    assert _cron("0 6,18 * * *", "2026-09-27T06:00Z", "2026-09-27T18:00Z") == [
        "2026-09-27T06:00Z"]  # [start, end)


def test_cron_day_rules():
    # 2026-09-27 is a Sunday; 0 and 7 both mean Sunday.
    assert _cron("0 6 * * 0", "2026-09-21", "2026-10-05") == [
        "2026-09-27T06:00Z", "2026-10-04T06:00Z"]
    assert _cron("0 6 * * 7", "2026-09-21", "2026-10-05") == _cron(
        "0 6 * * 0", "2026-09-21", "2026-10-05")
    assert _cron("0 6 * * 1-5", "2026-09-26", "2026-09-29") == ["2026-09-28T06:00Z"]
    # dom and dow both restricted: either matches (standard cron).
    assert _cron("0 6 1 * 0", "2026-09-27", "2026-10-05") == [
        "2026-09-27T06:00Z", "2026-10-01T06:00Z", "2026-10-04T06:00Z"]
    assert _cron("0 6 1 10 *", "2026-09-01", "2026-12-31") == ["2026-10-01T06:00Z"]
    # Vixie cron: a "*/n" day field is unrestricted, so dom and dow combine with AND.
    assert _cron("0 6 */2 * 0", "2026-09-21", "2026-10-12") == [
        "2026-09-27T06:00Z", "2026-10-11T06:00Z"]


@pytest.mark.parametrize("expr", ["0 6 * *", "60 6 * * *", "0 24 * * *", "*/0 * * * *",
                                  "a 6 * * *"])
def test_bad_cron_raises(expr):
    with pytest.raises(ValueError):
        cov.parse_cron(expr)


def test_active_bounds_and_one_off_times():
    cohort = dict(COHORT, routines=[
        dict(COHORT["routines"][0], schedule="0 * * * *",
             active_from="2026-09-27T03:00:00Z", active_until="2026-09-27T05:00:00Z"),
        {"slug": "once", "once": ["2026-09-27T04:30:00Z", "2026-09-28T04:30:00Z"]},
    ])
    ids = [inv.inv_id for inv in cov.expected_invocations(cohort, [], SINCE, UNTIL)]
    assert ids == ["daily-review@2026-09-27T03:00Z", "daily-review@2026-09-27T04:00Z",
                   "once@2026-09-27T04:30Z"]


# -- CLI --------------------------------------------------------------------

def _write(tmp_path, name, payload, as_yaml=False):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(payload) if as_yaml else json.dumps(payload), encoding="utf-8")
    return path


def test_cli_text_json_and_exit_codes(tmp_path, capsys):
    cohort = _write(tmp_path, "cohort.yaml", COHORT, as_yaml=True)
    records = _write(tmp_path, "records.json", {"runs": [_run()]})
    prs = _write(tmp_path, "prs.json", {REPO: [_pr()]})
    base = ["--since", "2026-09-27", "--until", "2026-09-27T12:00Z", "--cohort", str(cohort),
            "--records", str(records), "--prs", str(prs)]
    assert cov.main(base, fetch=_no_fetch) == 0
    out = capsys.readouterr().out
    assert "unknown: 1" in out and "2026-09-27T09:00Z skip-register" in out
    assert "coverage: 1/2 = 50.0%" in out
    assert cov.main(base + ["--json"], fetch=_no_fetch) == 0
    doc = json.loads(capsys.readouterr().out)
    assert [s["count"] for s in doc["stages"]] == [2, 1, 1, 1]
    empty = _write(tmp_path, "empty.json", {"runs": []})
    assert cov.main(base[:6] + ["--records", str(empty), "--prs", str(prs)],
                    fetch=_no_fetch) == 0
    assert "coverage: 0/2 = 0.0%" in capsys.readouterr().out
    broken = _write(tmp_path, "broken.yaml", {"schema": "something-else"}, as_yaml=True)
    assert cov.main(["--since", "2026-09-27", "--cohort", str(broken),
                     "--records", str(records), "--prs", str(prs)]) == 2
    assert cov.main(["--since", "not-a-date", "--records", str(records)]) == 2


def test_committed_cohort_loads():
    cohort = cov.load_cohort(cov.DEFAULT_COHORT)
    assert cohort["routines"], "the committed cohort lists the known Routines"
