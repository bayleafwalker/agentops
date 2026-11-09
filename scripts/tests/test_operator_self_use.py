import datetime
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import schema_check
import scripts.estate_status as estate
OUT_SCHEMA = json.loads((ROOT / "environment-record/estate-status-v1.schema.json").read_text())
REC_SCHEMA = json.loads((ROOT / "environment-record/vuoro-cloud-operator-self-use.schema.json").read_text())
PAIR = {"tenant_runtime_pin": "runtime", "sprintctl_version": "0.18.0"}


class ScriptModeTests(unittest.TestCase):
    def test_record_loads_when_estate_status_runs_as_a_plain_script(self):
        # `agentops estate status` runs the file as a script: `scripts` is not a package then.
        import subprocess
        code = (
            "import sys; sys.path.insert(0, %r); import estate_status as e; "
            "r = e._load_operator_self_use_record(); print(r.get('scope') is not None or bool(r))"
        ) % str(ROOT / "scripts")
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "True")


class NoQualificationYetTests(unittest.TestCase):
    def test_known_live_pair_without_recorded_qualification_is_not_void(self):
        record = estate._load_operator_self_use_record()
        record["profile_valid"] = True
        out = estate.evaluate_operator_self_use(
            record, desired_release_ready={"status": "known", "value": False},
            today=datetime.date(2026, 11, 8),
            pinned_pair={"tenant_runtime_pin": "runtime", "sprintctl_version": "0.18.0"})
        self.assertEqual(out["status"], "not_met")
        self.assertNotIn("changed after composition", out["label"])


class OperatorSelfUseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.root.joinpath("docs/plans").mkdir(parents=True)
        self.root.joinpath("receipts").mkdir()
        self.root.joinpath("evidence").mkdir()
        self.plan = "<!-- operator-self-use-open-rows:v1\n[]\n-->\n"
        (self.root / "docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md").write_text(self.plan)
        (self.root / "receipts/composition.json").write_text(json.dumps({"pinned_pair": PAIR}))
        (self.root / "evidence/observation.json").write_text(json.dumps({"status": "restored", "date": "2026-11-07"}))
        (self.root / "evidence/rehearsal.json").write_text(json.dumps({"date": "2026-11-06"}))
        self.patch_root = patch.object(estate, "ROOT", self.root)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)

    def tearDown(self): self.tmp.cleanup()

    def record(self):
        digest = lambda p: hashlib.sha256((self.root / p).read_bytes()).hexdigest()
        return {"schema_version": "vuoro-cloud-operator-self-use/v1",
            "scope": {"environment_id": "vuoro-cloud", "workspace_id": "01M3ABJS1QW0Q6BNDCHP0DDTYF", "workspaces": ["kotona"], "operator_owned": True, "host_owner": "operator"},
            "reviewer": "reviewer", "reviewed_on": "2026-11-08",
            "pat": {"id": "id", "expires_on": "2026-11-28", "workspace": "kotona", "authorities": ["work:read"]},
            "fallback_environment": "vuoro-shared", "vuoro_shared_fallback": True,
            "evidence_refs": {"profile": "environment-record/profiles/workstation-vuoro-cloud.json", "cutover_plan": "docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md", "cutover_plan_sha256": digest("docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md"),
                "composition_qualification": {"ref": "receipts/composition.json", "pinned_pair": PAIR, "sha256": digest("receipts/composition.json")},
                "restored_observation": "evidence/observation.json", "restored_observation_sha256": digest("evidence/observation.json"),
                "cutover_rehearsal": "evidence/rehearsal.json", "cutover_rehearsal_sha256": digest("evidence/rehearsal.json")},
            }

    def evaluate(self, rec=None, ready=False, day="2026-11-08", pins=PAIR):
        rec = rec or self.record()
        rec.setdefault("profile_valid", True)
        return estate.evaluate_operator_self_use(rec, desired_release_ready={"status": "known", "value": ready}, today=datetime.date.fromisoformat(day), pinned_pair=pins)

    def test_checked_in_record_schema(self):
        doc = json.loads((ROOT / "environment-record/vuoro-cloud.operator-self-use.json").read_text())
        self.assertEqual(schema_check.validate(doc, REC_SCHEMA), [])
        self.assertEqual(schema_check.validate(self.record(), REC_SCHEMA), [])

    def test_status_outputs_and_labels_validate(self):
        met = self.evaluate()
        self.assertEqual(met["status"], "met")
        self.assertIn("NOT release_ready", met["label"])
        bad = self.record(); bad["profile_valid"] = False
        not_met = self.evaluate(bad)
        self.assertEqual(not_met["status"], "not_met")
        self.assertIn("B1", not_met["label"])
        self.assertIn("NOT release_ready.", not_met["label"])
        void = self.evaluate(ready=True)
        self.assertEqual(void["status"], "void")
        self.assertIn("release_ready=true", void["label"])
        self.assertIn("void", void["label"])
        out_schema = OUT_SCHEMA["$defs"]["environment"]["properties"]["operator_self_use"]
        for out in (met, not_met, void):
            self.assertEqual(schema_check.validate(out, out_schema), [])
            self.assertEqual(out["scope"]["workspaces"], ["kotona"])
            self.assertEqual(len(out["record_sha256"]), 64)

    def test_checked_evidence_and_hand_edit_attempts(self):
        r = self.record(); self.assertEqual(self.evaluate(r)["status"], "met")
        # Editing an attestation alone cannot manufacture a clear plan or evidence.
        r["evidence_refs"]["composition_qualification"]["ref"] = "missing.json"
        self.assertIn(self.evaluate(r)["status"], ("not_met", "void"))
        r = self.record(); r["evidence_refs"]["cutover_plan"] = "wrong.md"
        self.assertIn(self.evaluate(r)["status"], ("not_met", "void"))
        r = self.record(); r["fallback_environment"] = "other"
        self.assertEqual(self.evaluate(r)["status"], "void")
        r = self.record(); r["evidence_refs"]["composition_qualification"]["pinned_pair"] = {**PAIR, "sprintctl_version": "wrong"}
        self.assertIn(self.evaluate(r)["status"], ("not_met", "void"))
        r = self.record(); r["evidence_refs"].pop("restored_observation")
        missing_evidence = self.evaluate(r)
        self.assertEqual(missing_evidence["status"], "not_met")
        self.assertIn("evidence reference is missing", missing_evidence["first_failing_check"])
        r = self.record(); r["scope"]["workspaces"] = ["other"]
        out = self.evaluate(r); self.assertEqual(out["status"], "void"); self.assertEqual(out["scope"], estate.OPERATOR_SCOPE)
        (self.root / "docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md").write_text(self.plan.replace("[]", '["open row"]'))
        self.assertEqual(self.evaluate()["status"], "not_met")

    def test_date_boundaries_and_malformed_dates(self):
        r = self.record()
        expiry_day = self.evaluate(r, day="2026-11-28")
        self.assertEqual(expiry_day["status"], "void")
        self.assertEqual(expiry_day["void_reason"], "PAT is past expiry")
        self.assertEqual(self.evaluate(r, day="2026-11-29")["status"], "void")
        r = self.record(); r["reviewed_on"] = "2026-08-10"; r["pat"]["expires_on"] = "2026-12-08"
        self.assertEqual(self.evaluate(r, day="2026-11-08")["status"], "void")
        r = self.record(); r["reviewed_on"] = "2026-08-11"; r["pat"]["expires_on"] = "2026-12-08"
        self.assertNotEqual(self.evaluate(r, day="2026-11-08")["status"], "void")
        r = self.record(); r["pat"]["expires_on"] = "2026-11-09"
        self.assertEqual(self.evaluate(r, day="2026-11-08")["status"], "met")
        r["reviewed_on"] = "2026-08-09"
        self.assertEqual(self.evaluate(r, day="2026-11-08")["status"], "void")
        r = self.record(); (self.root / "evidence/observation.json").write_text('{"status":"restored","date":"2026-10-10"}')
        (self.root / "evidence/rehearsal.json").write_text('{"date":"2026-10-09"}')
        self.assertNotEqual(self.evaluate(r, day="2026-11-08")["status"], "void")
        (self.root / "evidence/observation.json").write_text('{"status":"restored","date":"2026-10-09"}')
        self.assertEqual(self.evaluate(r, day="2026-11-08")["status"], "void")
        (self.root / "evidence/observation.json").write_text('{"status":"restored","date":"2026-10-08"}')
        (self.root / "evidence/rehearsal.json").write_text('{"date":"2026-10-07"}')
        self.assertEqual(self.evaluate(r, day="2026-11-08")["status"], "void")
        for value in ("", None, "bad"):
            r = self.record(); r["reviewed_on"] = value
            out = self.evaluate(r)
            self.assertIn(out["status"], ("not_met", "void"))
            self.assertIn("NOT release_ready", out["label"])
        r = self.record(); r.pop("reviewed_on")
        self.assertEqual(self.evaluate(r)["status"], "void")

    def test_missing_record_is_valid_not_met_and_file_digest_is_used(self):
        missing = {"_record_error": "record missing", "_record_sha256": hashlib.sha256(b"").hexdigest()}
        out = self.evaluate(missing)
        self.assertEqual(out["status"], "not_met")
        self.assertIn("record missing", out["label"])
        out_schema = OUT_SCHEMA["$defs"]["environment"]["properties"]["operator_self_use"]
        self.assertEqual(schema_check.validate(out, out_schema), [])

    def test_no_restored_age_uses_evidence_and_empty_pins_cannot_pass(self):
        r = self.record()
        r["evidence_refs"]["restored_observation"] = "evidence/no-restore.json"
        r["reviewed_on"] = "2026-11-07"
        (self.root / "evidence/no-restore.json").write_text('{"status":"unavailable","date":"2026-10-09"}')
        (self.root / "evidence/rehearsal.json").write_text('{"date":"2026-10-08"}')
        r["evidence_refs"]["restored_observation_sha256"] = hashlib.sha256((self.root / "evidence/no-restore.json").read_bytes()).hexdigest()
        r["evidence_refs"]["cutover_rehearsal_sha256"] = hashlib.sha256((self.root / "evidence/rehearsal.json").read_bytes()).hexdigest()
        self.assertEqual(self.evaluate(r, day="2026-11-07")["status"], "not_met")
        self.assertEqual(self.evaluate(r, day="2026-11-08")["status"], "void")
        r = self.record()
        (self.root / "receipts/composition.json").write_text('{"pinned_pair":{"tenant_runtime_pin":"","sprintctl_version":""}}')
        r["evidence_refs"]["composition_qualification"]["pinned_pair"] = {"tenant_runtime_pin": "", "sprintctl_version": ""}
        self.assertNotEqual(self.evaluate(r)["status"], "met")

    def test_digest_binding_malformed_json_future_dates_and_paths(self):
        for path in ("receipts/composition.json", "evidence/observation.json", "evidence/rehearsal.json"):
            rec = self.record()
            (self.root / path).write_text("[]")
            ref_hash = {"receipts/composition.json": ("composition_qualification", "sha256"), "evidence/observation.json": (None, "restored_observation_sha256"), "evidence/rehearsal.json": (None, "cutover_rehearsal_sha256")}[path]
            digest_value = hashlib.sha256((self.root / path).read_bytes()).hexdigest()
            if ref_hash[0]: rec["evidence_refs"][ref_hash[0]][ref_hash[1]] = digest_value
            else: rec["evidence_refs"][ref_hash[1]] = digest_value
            out = self.evaluate(rec)
            self.assertEqual(out["status"], "not_met")
            self.assertIn("malformed", out["first_failing_check"])
            # Fresh fixture file and matching binding for the next case.
            if path.endswith("composition.json"):
                (self.root / path).write_text(json.dumps({"pinned_pair": PAIR}))
            elif path.endswith("observation.json"):
                (self.root / path).write_text(json.dumps({"status": "restored", "date": "2026-11-07"}))
            else:
                (self.root / path).write_text(json.dumps({"date": "2026-11-06"}))
        rec = self.record()
        (self.root / "receipts/composition.json").write_text(json.dumps({"pinned_pair": PAIR, "extra": True}))
        self.assertIn("composition.json digest mismatch", self.evaluate(rec)["first_failing_check"])
        rec = self.record(); (self.root / "evidence/observation.json").write_text('{"status":"restored","date":"2026-11-09"}')
        rec["evidence_refs"]["restored_observation_sha256"] = hashlib.sha256((self.root / "evidence/observation.json").read_bytes()).hexdigest()
        self.assertIn("future", self.evaluate(rec)["first_failing_check"])
        rec = self.record(); (self.root / "evidence/rehearsal.json").write_text('{"date":"2026-11-09"}')
        rec["evidence_refs"]["cutover_rehearsal_sha256"] = hashlib.sha256((self.root / "evidence/rehearsal.json").read_bytes()).hexdigest()
        self.assertIn("future", self.evaluate(rec)["first_failing_check"])
        for ref in ("../outside.json",):
            rec = self.record(); rec["evidence_refs"]["restored_observation"] = ref
            self.assertEqual(self.evaluate(rec)["status"], "not_met")
        absolute_inside = self.root / "evidence/observation.json"
        rec = self.record(); rec["evidence_refs"]["restored_observation"] = str(absolute_inside)
        result = self.evaluate(rec)
        self.assertEqual(result["status"], "not_met")
        self.assertIn("evidence path is invalid", result["first_failing_check"])
        outside = self.root.parent / "outside-evidence.json"; outside.write_text('{"status":"restored","date":"2026-11-07"}')
        link = self.root / "evidence/escape.json"; link.symlink_to(outside)
        rec = self.record(); rec["evidence_refs"]["restored_observation"] = "evidence/escape.json"
        self.assertEqual(self.evaluate(rec)["status"], "not_met")

    def test_plan_marker_digest_and_unknown_release_label(self):
        rec = self.record()
        (self.root / "docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md").write_text(self.plan.replace("[]", '["row"]'))
        self.assertEqual(self.evaluate(rec)["first_failing_check"], "B2 cutover plan has open in-scope rows")
        result = self.evaluate(rec)
        self.assertIn("B2", result["label"])
        self.assertIn("B2", result["first_failing_check"])
        rec = self.record(); out = estate.evaluate_operator_self_use(rec, desired_release_ready={"status": "unknown", "value": None}, today=datetime.date(2026, 11, 8), pinned_pair=PAIR)
        self.assertIn("release_ready=unknown", out["label"])
        self.assertIn("NOT release_ready", out["label"])
        # Editing the reviewed empty marker without refreshing its bound digest
        # cannot create a met result.
        rec = self.record()
        plan = self.root / "docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md"
        plan.write_text(self.plan.replace("[]", '["open"]'))
        self.assertIn("B2", self.evaluate(rec)["first_failing_check"])
        plan.write_text(self.plan)
        self.assertIn("record-family-cutover.md digest mismatch", self.evaluate(rec)["first_failing_check"])

    def test_exactly_one_open_rows_marker_required(self):
        rec = self.record()
        plan = self.root / "docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md"
        plan.write_text(self.plan + '<!-- operator-self-use-open-rows:v1\n["open row"]\n-->\n')
        rec["evidence_refs"]["cutover_plan_sha256"] = hashlib.sha256(plan.read_bytes()).hexdigest()
        result = self.evaluate(rec)
        self.assertEqual(result["status"], "not_met")
        self.assertIn("exactly one", result["first_failing_check"])

    def test_open_rows_marker_counts_malformed_and_ignored_occurrences(self):
        path = self.root / "docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md"
        cases = [
            ("zero markers", "no marker\n", None),
            ("two empty markers", self.plan + self.plan, None),
            ("non-array body plus valid marker", '<!-- operator-self-use-open-rows:v1 {"rows":["x"]} -->\n<!-- operator-self-use-open-rows:v1 [] -->', None),
            ("string body plus valid marker", '<!-- operator-self-use-open-rows:v1 "x" -->\n<!-- operator-self-use-open-rows:v1 [] -->', None),
            ("fenced marker", '```md\n<!-- operator-self-use-open-rows:v1 [] -->\n```', None),
            ("quoted marker", '> <!-- operator-self-use-open-rows:v1 [] -->', None),
            ("real open row hidden in fence beside lone empty marker", '<!-- operator-self-use-open-rows:v1 [] -->\n```\n<!-- operator-self-use-open-rows:v1 ["B2 open"] -->\n```', None),
            ("indented fence is not a fence", '<!-- operator-self-use-open-rows:v1 [] -->\n    ```\n<!-- operator-self-use-open-rows:v1 ["B2 open"] -->', None),
            ("tilde fence hides open row", '<!-- operator-self-use-open-rows:v1 [] -->\n~~~\n<!-- operator-self-use-open-rows:v1 ["B2 open"] -->\n~~~', None),
            ("quoted open row beside lone empty marker", '<!-- operator-self-use-open-rows:v1 [] -->\n> <!-- operator-self-use-open-rows:v1 ["B2 open"] -->', None),
            ("fence lines inside the marker body", '<!-- operator-self-use-open-rows:v1 [\n```\n"B2 open"\n```\n] -->', None),
            ("tilde lines inside the marker body", '<!-- operator-self-use-open-rows:v1 [\n~~~\n"B2 open"\n~~~\n] -->', None),
            ("quote line inside the marker body", '<!-- operator-self-use-open-rows:v1 [\n> "B2 open"\n] -->', None),
            ("CRLF marker", '<!-- operator-self-use-open-rows:v1\r\n[]\r\n-->\r\n', []),
            ("unterminated marker", '<!-- operator-self-use-open-rows:v1 []', None),
        ]
        for name, content, expected in cases:
            with self.subTest(name=name):
                path.write_bytes(content.encode())
                self.assertEqual(estate._cutover_rows_path(path), expected)
        path.write_bytes(b"<!-- operator-self-use-open-rows:v1 [] -->\xff")
        self.assertIsNone(estate._cutover_rows_path(path))

    def test_partially_unknown_live_pair_is_not_a_pin_change(self):
        result = self.evaluate(pins={"tenant_runtime_pin": "runtime", "sprintctl_version": None})
        self.assertEqual(result["status"], "not_met")
        self.assertIn("live pair unknown", result["label"])

    def test_nul_evidence_ref_is_rejected_and_non_string_is_described(self):
        self.assertEqual(estate._bound_evidence_path("evidence/\x00bad", "x"), (None, "evidence path is invalid"))
        self.assertEqual(estate._bound_evidence_path(42, "x"), (None, "evidence reference is missing or not a string"))


if __name__ == "__main__": unittest.main()
