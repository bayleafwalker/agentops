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
        return {"schema_version": "vuoro-cloud-operator-self-use/v1",
            "scope": {"environment_id": "vuoro-cloud", "workspace_id": "01M3ABJS1QW0Q6BNDCHP0DDTYF", "workspaces": ["kotona"], "operator_owned": True, "host_owner": "operator"},
            "reviewer": "reviewer", "reviewed_on": "2026-11-08",
            "pat": {"id": "id", "expires_on": "2026-11-28", "workspace": "kotona", "authorities": ["work:read"]},
            "fallback_environment": "vuoro-shared", "vuoro_shared_fallback": True,
            "evidence_refs": {"profile": "environment-record/profiles/workstation-vuoro-cloud.json", "cutover_plan": "docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md",
                "composition_qualification": {"ref": "receipts/composition.json", "pinned_pair": PAIR},
                "restored_observation": "evidence/observation.json", "cutover_rehearsal": "evidence/rehearsal.json"},
            "cutover_open_rows": []}

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
        r["cutover_open_rows"] = []
        r["evidence_refs"]["composition_qualification"]["ref"] = "missing.json"
        self.assertIn(self.evaluate(r)["status"], ("not_met", "void"))
        r = self.record(); r["evidence_refs"]["cutover_plan"] = "wrong.md"
        self.assertIn(self.evaluate(r)["status"], ("not_met", "void"))
        r = self.record(); r["fallback_environment"] = "other"
        self.assertEqual(self.evaluate(r)["status"], "void")
        r = self.record(); r["evidence_refs"]["composition_qualification"]["pinned_pair"] = {**PAIR, "sprintctl_version": "wrong"}
        self.assertIn(self.evaluate(r)["status"], ("not_met", "void"))
        r = self.record(); r["evidence_refs"].pop("restored_observation")
        self.assertEqual(self.evaluate(r)["status"], "not_met")
        r = self.record(); r["scope"]["workspaces"] = ["other"]
        out = self.evaluate(r); self.assertEqual(out["status"], "void"); self.assertEqual(out["scope"], estate.OPERATOR_SCOPE)
        (self.root / "docs/plans/2026-11-08-vuoro-cloud-record-family-cutover.md").write_text(self.plan.replace("[]", '["open row"]'))
        self.assertEqual(self.evaluate()["status"], "not_met")

    def test_date_boundaries_and_malformed_dates(self):
        r = self.record()
        self.assertEqual(self.evaluate(r, day="2026-11-28")["status"], "met")
        self.assertEqual(self.evaluate(r, day="2026-11-29")["status"], "void")
        r = self.record(); r["reviewed_on"] = "2026-08-10"; r["pat"]["expires_on"] = "2026-12-08"
        self.assertEqual(self.evaluate(r, day="2026-11-08")["status"], "not_met")
        r["reviewed_on"] = "2026-08-09"
        self.assertEqual(self.evaluate(r, day="2026-11-08")["status"], "void")
        r = self.record(); (self.root / "evidence/observation.json").write_text('{"status":"restored","date":"2026-10-10"}')
        (self.root / "evidence/rehearsal.json").write_text('{"date":"2026-10-09"}')
        self.assertNotEqual(self.evaluate(r, day="2026-11-08")["status"], "void")
        (self.root / "evidence/observation.json").write_text('{"status":"restored","date":"2026-10-09"}')
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
        self.assertEqual(self.evaluate(r, day="2026-11-07")["status"], "not_met")
        self.assertEqual(self.evaluate(r, day="2026-11-08")["status"], "void")
        r = self.record()
        (self.root / "receipts/composition.json").write_text('{"pinned_pair":{"tenant_runtime_pin":"","sprintctl_version":""}}')
        r["evidence_refs"]["composition_qualification"]["pinned_pair"] = {"tenant_runtime_pin": "", "sprintctl_version": ""}
        self.assertNotEqual(self.evaluate(r)["status"], "met")


if __name__ == "__main__": unittest.main()
